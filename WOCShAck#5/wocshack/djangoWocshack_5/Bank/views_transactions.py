import csv
import io
import json
import xml.etree.ElementTree as ET

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import BankCard, Transaction
from .Utils.expiry import is_session_expired


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------

@login_required()
def transaction_history(request):
    """Full transaction history page with filter and search."""
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return redirect("/banking/verification/")

    # Filtering
    tx_filter = request.GET.get('type', '')
    search_q = request.GET.get('q', '').strip()
    card_filter = request.GET.get('card', '').strip()

    qs = Transaction.objects.filter(user=request.user)

    if tx_filter in ('transfer_out', 'transfer_in', 'payment', 'refund', 'deposit'):
        qs = qs.filter(transaction_type=tx_filter)

    if card_filter:
        try:
            card_filter_id = int(card_filter)
            qs = qs.filter(card_id=card_filter_id)
        except ValueError:
            card_filter = ''

    if search_q:
        from django.db.models import Q
        qs = qs.filter(
            Q(counterpart_payment_number__icontains=search_q) |
            Q(note__icontains=search_q) |
            Q(counterpart_label__icontains=search_q)
        )

    transactions = qs.order_by('-created_at')[:200]
    user_cards = BankCard.objects.filter(user=request.user).exclude(status='cancelled')

    return render(request, "account/transaction_history.html", {
        "transactions": transactions,
        "tx_filter": tx_filter,
        "search_q": search_q,
        "card_filter": card_filter,
        "user_cards": user_cards,
    })


# ---------------------------------------------------------------------------
# Transaction receipt (PDF download)
# ---------------------------------------------------------------------------

@login_required()
def download_transaction_receipt(request, transaction_id):
    """
    Generate and stream a PDF receipt for a transaction.

    Guards:
      - Requires active PIN session
      - Transaction must belong to the authenticated user (no IDOR)
    """
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return redirect("/banking/verification/")

    from django.shortcuts import get_object_or_404
    tx = get_object_or_404(Transaction, pk=transaction_id, user=request.user)

    from .Utils.pdf_utils import generate_transaction_receipt
    pdf_bytes = generate_transaction_receipt(tx, request.user)

    if pdf_bytes is None:
        messages.error(request, "PDF generation is currently unavailable. Please try exporting as CSV.")
        return redirect('/banking/transactions/')

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="vrc_receipt_{tx.id}.pdf"'
    return response


# ---------------------------------------------------------------------------
# Card statement (PDF download)
# ---------------------------------------------------------------------------

@login_required()
def download_card_statement(request, card_id):
    """
    Generate and stream a PDF statement for a card.

    Supports ?period=monthly (default), quarterly, annual, or custom date range
    via ?from=YYYY-MM-DD&to=YYYY-MM-DD.

    Guards:
      - Requires active PIN session
      - Card must belong to the authenticated user (no IDOR)
    """
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return redirect("/banking/verification/")

    from django.shortcuts import get_object_or_404
    card = get_object_or_404(BankCard, pk=card_id, user=request.user)

    period = request.GET.get('period', 'monthly')
    now = timezone.now()

    if period == 'quarterly':
        # Current quarter
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        from datetime import datetime
        date_from = timezone.make_aware(
            datetime(now.year, quarter_start_month, 1)
        )
        q_num = (quarter_start_month - 1) // 3 + 1
        period_label = f"Q{q_num} {now.year}"
    elif period == 'annual':
        from datetime import datetime
        date_from = timezone.make_aware(datetime(now.year, 1, 1))
        period_label = f"Annual {now.year}"
    elif period == 'custom':
        try:
            from datetime import datetime
            from_str = request.GET.get('from', '')
            to_str = request.GET.get('to', '')
            date_from = timezone.make_aware(datetime.strptime(from_str, '%Y-%m-%d'))
            date_to = timezone.make_aware(datetime.strptime(to_str, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59
            ))
            period_label = f"{from_str} to {to_str}"
        except (ValueError, TypeError):
            messages.error(request, "Invalid date range. Please use YYYY-MM-DD format.")
            return redirect('/banking/dashboard/')
    else:
        # Monthly (default): current calendar month
        from datetime import datetime
        date_from = timezone.make_aware(datetime(now.year, now.month, 1))
        period_label = now.strftime('%B %Y')

    # Build queryset: transactions for this card in the period
    qs = Transaction.objects.filter(
        user=request.user,
        card=card,
    )
    if period == 'custom':
        qs = qs.filter(created_at__gte=date_from, created_at__lte=date_to)
    else:
        qs = qs.filter(created_at__gte=date_from)

    qs = qs.order_by('created_at')

    from .Utils.pdf_utils import generate_card_statement
    pdf_bytes = generate_card_statement(request.user, qs, period_label, card=card)

    if pdf_bytes is None:
        messages.error(request, "PDF generation is currently unavailable. Please try exporting as CSV.")
        return redirect('/banking/dashboard/')

    filename = f"vrc_statement_card{card.id}_{period_label.replace(' ', '_')}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required()
def download_account_statement(request):
    """
    Generate and stream a PDF statement for all of the user's transactions.
    """
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return redirect("/banking/verification/")

    period = request.GET.get('period', 'monthly')
    now = timezone.now()

    if period == 'quarterly':
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        from datetime import datetime
        date_from = timezone.make_aware(datetime(now.year, quarter_start_month, 1))
        q_num = (quarter_start_month - 1) // 3 + 1
        period_label = f"Q{q_num} {now.year}"
    elif period == 'annual':
        from datetime import datetime
        date_from = timezone.make_aware(datetime(now.year, 1, 1))
        period_label = f"Annual {now.year}"
    else:
        from datetime import datetime
        date_from = timezone.make_aware(datetime(now.year, now.month, 1))
        period_label = now.strftime('%B %Y')

    qs = Transaction.objects.filter(
        user=request.user,
        created_at__gte=date_from,
    ).order_by('created_at')

    from .Utils.pdf_utils import generate_card_statement
    pdf_bytes = generate_card_statement(request.user, qs, period_label, card=None)

    if pdf_bytes is None:
        messages.error(request, "PDF generation is currently unavailable. Please try exporting as CSV.")
        return redirect('/banking/dashboard/')

    filename = f"vrc_statement_{period_label.replace(' ', '_')}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ---------------------------------------------------------------------------
# Bank statement export (CSV, JSON, XML)
# ---------------------------------------------------------------------------

@login_required()
def export_statement_csv(request):
    """Export user's transaction history as CSV."""
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return redirect("/banking/verification/")

    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="vrc_bank_statement.csv"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Type', 'Amount (NE)', 'Counterpart', 'Note', 'Status', 'Balance After'])

    for tx in transactions:
        writer.writerow([
            tx.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            tx.get_transaction_type_display(),
            str(tx.amount),
            tx.counterpart_payment_number or tx.counterpart_label or '-',
            tx.note or '-',
            tx.get_status_display(),
            str(tx.balance_after) if tx.balance_after is not None else '-',
        ])

    return response


@login_required()
def export_statement_json(request):
    """Export user's transaction history as JSON."""
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return redirect("/banking/verification/")

    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')

    data = {
        "exported_at": timezone.now().isoformat(),
        "account_owner": request.user.username,
        "account_email": request.user.email,
        "account_name": request.user.get_full_name(),
        "transactions": [
            {
                "date": tx.created_at.isoformat(),
                "type": tx.transaction_type,
                "amount": str(tx.amount),
                "counterpart": tx.counterpart_payment_number or tx.counterpart_label or '',
                "note": tx.note or '',
                "status": tx.status,
                "balance_after": str(tx.balance_after) if tx.balance_after is not None else None,
            }
            for tx in transactions
        ],
    }

    response = HttpResponse(
        json.dumps(data, indent=2),
        content_type='application/json'
    )
    response['Content-Disposition'] = 'attachment; filename="vrc_bank_statement.json"'
    return response


@login_required()
def export_statement_xml(request):
    """Export user's transaction history as XML."""
    # Guard: require active PIN session before exposing financial data.
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return redirect("/banking/verification/")

    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')

    # Build the XML tree with xml.etree.ElementTree (stdlib, no third-party deps).
    root = ET.Element('statement')
    root.set('version', '1.0')

    # Metadata header
    meta = ET.SubElement(root, 'meta')
    ET.SubElement(meta, 'exported_at').text = timezone.now().strftime('%Y-%m-%dT%H:%M:%S')
    ET.SubElement(meta, 'account_owner').text = request.user.username
    ET.SubElement(meta, 'account_name').text = request.user.get_full_name() or ''
    ET.SubElement(meta, 'account_email').text = request.user.email or ''
    ET.SubElement(meta, 'total_records').text = str(transactions.count())

    # One <transaction> element per row
    tx_list = ET.SubElement(root, 'transactions')
    for tx in transactions:
        tx_el = ET.SubElement(tx_list, 'transaction')
        ET.SubElement(tx_el, 'date').text = tx.created_at.strftime('%Y-%m-%dT%H:%M:%S')
        ET.SubElement(tx_el, 'type').text = tx.transaction_type
        ET.SubElement(tx_el, 'type_label').text = tx.get_transaction_type_display()
        ET.SubElement(tx_el, 'amount').text = str(tx.amount)
        ET.SubElement(tx_el, 'recipient').text = (
            tx.counterpart_payment_number or tx.counterpart_label or ''
        )
        ET.SubElement(tx_el, 'note').text = tx.note or ''
        ET.SubElement(tx_el, 'status').text = tx.status
        ET.SubElement(tx_el, 'balance_after').text = (
            str(tx.balance_after) if tx.balance_after is not None else ''
        )

    # Serialise to a UTF-8 byte string via minidom for pretty-printing with
    # a proper XML declaration, then decode back to str for HttpResponse.
    from xml.dom.minidom import parseString
    raw_xml = ET.tostring(root, encoding='unicode')
    pretty_xml = parseString(raw_xml).toprettyxml(indent='  ', encoding='UTF-8')

    response = HttpResponse(pretty_xml, content_type='application/xml; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="vrc_bank_statement.xml"'
    return response
