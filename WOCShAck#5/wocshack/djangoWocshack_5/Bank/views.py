import json
import logging
import time
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt

from .models import BankCard, Beneficiary, Transaction
from .Utils.external_calls import (
    backend_connection,
    create_backend_session,
    get_user,
)
from .Utils.expiry import is_session_expired
from .Utils.client import make_connection

logger = logging.getLogger('bank')


# ---------------------------------------------------------------------------
# Public landing page
# ---------------------------------------------------------------------------

def index(request):
    has_bank_account = True
    show_claim_banner = False

    if request.user.is_authenticated:
        check_resp = get_user(request.user.id)
        if isinstance(check_resp, dict) and check_resp.get("success"):
            has_bank_account = True
            # Check if the user has already claimed the bonus
            if not request.user.profile.has_claimed_bonus:
                show_claim_banner = True
        else:
            has_bank_account = False
            show_claim_banner = False
    else:
        show_claim_banner = False

    return render(request, "bank_index.html", {
        "show_claim_banner": show_claim_banner,
    })


# ---------------------------------------------------------------------------
# Payment initialization (used by Shopping module popup flow)
# ---------------------------------------------------------------------------

def payment_initialization(request):
    if request.method == 'POST':
        sid = create_backend_session()
        if sid:
            time.sleep(1)
            return JsonResponse({"success": True, "sid": sid})
        return JsonResponse({"success": False, "error": "Banking server unreachable. Please try again later."})
    return JsonResponse({"success": False, "error": "Invalid request"}, status=400)


def payment_initialization_screen(request):
    return render(request, "payments/initialization.html")


@xframe_options_exempt
def popup_action_view(request, sid):
    if request.method == 'POST':
        return JsonResponse({'success': True})
    return render(request, "payments/ask_pin.html")


# ---------------------------------------------------------------------------
# Main banking dashboard (requires PIN session)
# ---------------------------------------------------------------------------

@csrf_exempt
@login_required()
def account(request):
    # Bank session is verified before rendering any financial data.

    # Debug: Log request data
    if request.method == 'POST':
        print(f"POST data: {request.POST}")

    # Check if user has a bank account; if not, show claim page
    has_bank_account = True
    check_resp = get_user(request.user.id)
    if not (isinstance(check_resp, dict) and check_resp.get("success")):
        has_bank_account = False

    # Handle claim bonus for users with a bank account but haven't claimed the bonus
    if has_bank_account and request.method == 'POST' and request.POST.get("action") == "claim_bonus":
        if not request.user.profile.has_claimed_bonus:
            with backend_connection() as (cli, sid):
                if cli and sid:
                    # Get user details to retrieve the current balance
                    user_details = cli.get_user(sid, request.user.id)
                    if isinstance(user_details, dict) and user_details.get("success"):
                        current_balance = user_details.get("balance", 0)
                        new_balance = current_balance + 150
                        # Add 150 Neuros to the user's account
                        cli.add_amount(sid, request.user.id, 150)
                        time.sleep(0.3)
                    else:
                        messages.error(request, "Failed to get user details. Please try again later.")
                        return redirect('/banking/dashboard/')
                else:
                    messages.error(request, "Banking server unreachable. Please try again later.")
                    return redirect('/banking/dashboard/')
            # Mark the bonus as claimed
            request.user.profile.has_claimed_bonus = True
            request.user.profile.save()
            messages.success(request, "Your 150 Neuros bonus has been credited!")
            return redirect('/banking/dashboard/')
        else:
            messages.info(request, "You have already claimed your bonus.")

    if not has_bank_account:
        if request.method == 'POST' and request.POST.get("action") == "claim_bonus":
            with backend_connection() as (cli, sid):
                if cli and sid:
                    cli.add_user(sid, request.user.id, "0000")
                    time.sleep(0.5)
                    cli.set_balance(sid, request.user.id, 150)
                    time.sleep(0.3)
                else:
                    messages.error(request, "Banking server unreachable. Please try again later.")
                    return redirect('/banking/dashboard/')
            # Mark the bonus as claimed
            request.user.profile.has_claimed_bonus = True
            request.user.profile.save()
            messages.success(request, "Welcome! Your 150 Neuros bonus has been credited.")
            return redirect('/banking/verification/')
        return render(request, "account/dashboard.html", {
            "has_bank_account": False,
            "show_claim_banner": False,
        })

    if request.method == 'POST':
        form_type = request.POST.get("form_type")

        if form_type == "transfer_form":
            _handle_transfer(request)

        elif form_type == "freeze_card":
            card_id = request.POST.get("card_id")
            _handle_freeze_card(request, card_id)

        elif form_type == "unfreeze_card":
            card_id = request.POST.get("card_id")
            _handle_unfreeze_card(request, card_id)

        # After POST, redirect to prevent form re-submission (PRG pattern)
        return redirect('/banking/dashboard/')

    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return redirect("/banking/verification/")

    # Fetch live account data from backend
    user_id = request.user.id
    balance = None
    account_number = None
    payment_number = None
    history = []

    with backend_connection() as (cli, sid):
        if cli and sid:
            response = cli.get_user(sid, user_id)
            time.sleep(0.5)

            if isinstance(response, dict) and response.get("success"):
                user_data = response.get("user", {})
                balance = user_data.get("balance")
                account_number = user_data.get("account_number", user_data.get("payment_number"))
                payment_number = user_data.get("payment_number")
                raw_history = user_data.get("history", [])
                if isinstance(raw_history, str):
                    try:
                        raw_history = json.loads(raw_history)
                    except (json.JSONDecodeError, TypeError):
                        raw_history = []
                history = raw_history if isinstance(raw_history, list) else []

            # Ensure backend has a default card for this user (migration for existing accounts)
            default_card_number = payment_number or account_number
            if default_card_number:
                cli.ensure_default_card(sid, user_id, default_card_number)
                time.sleep(0.3)

    # Fetch local transaction records (Django DB) for richer display
    local_transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:50]

    # Sync cards: if no Django BankCards exist, create a default one from the backend card number
    all_cards = list(BankCard.objects.filter(user=request.user).order_by('created_at'))
    default_card_number = payment_number or account_number
    if not all_cards and default_card_number:
        default_card, _ = BankCard.objects.get_or_create(
            payment_number=str(default_card_number),
            defaults={
                'user': request.user,
                'card_type': 'virtual',
                'status': 'active',
            },
        )
        all_cards = [default_card]

    # Beneficiaries for transfer tab
    beneficiaries = Beneficiary.objects.filter(user=request.user)

    return render(request, "account/dashboard.html", {
        "balance": balance,
        "account_number": account_number,
        "all_cards": all_cards,
        "history": history,
        "local_transactions": local_transactions,
        "beneficiaries": beneficiaries,
    })


def _handle_transfer(request):
    """Process a money transfer POST. Called from account() view."""
    recipient = request.POST.get('recipient', '').strip()
    amount_str = request.POST.get('amount', '').strip()
    note = request.POST.get('note', '').strip()

    if not recipient or not amount_str:
        messages.error(request, "Please fill in all required fields.")
        return

    try:
        amount = Decimal(amount_str)
    except (ValueError, InvalidOperation):
        messages.error(request, "Invalid amount entered.")
        return

    if amount <= 0:
        messages.error(request, "Amount must be greater than zero.")
        return

    with backend_connection() as (cli, sid):
        if not cli or not sid:
            messages.error(request, "Banking server unreachable. Please try again later.")
            return

        try:
            # Lookup sender
            user_response = cli.get_user(sid, request.user.id)
            time.sleep(0.3)

            if not isinstance(user_response, dict) or not user_response.get("success"):
                messages.error(request, "Could not verify your account. Please try again.")
                return

            user_data = user_response.get("user", {})
            current_balance = Decimal(str(user_data.get("balance", 0)))
            sender_id = user_data.get("id")

            if amount > current_balance:
                messages.error(request, "Insufficient balance for this transfer.")
                return

            # Lookup recipient by payment number
            recipient_response = cli.get_user_by_payment_number(sid, recipient)
            time.sleep(0.3)

            if not isinstance(recipient_response, dict) or not recipient_response.get("success"):
                messages.error(request, "Recipient account not found. Please check the account number.")
                return

            recipient_id = recipient_response.get("user", {}).get("id")

            if not recipient_id:
                messages.error(request, "Recipient account not found. Please check the account number.")
                return

            if str(sender_id) == str(recipient_id):
                messages.error(request, "You cannot transfer money to yourself.")
                return

            # Perform transfer
            result = cli.transaction(
                sid=sid,
                from_user=sender_id,
                to_user=recipient_id,
                amount=float(amount),
            )
            time.sleep(0.3)

            if isinstance(result, dict) and result.get('status') == 'success':
                # The tr command returns only {'status': 'success'} - fetch updated balance separately
                new_balance = result.get('from_balance')
                if new_balance is None:
                    balance_resp = cli.get_user(sid, request.user.id)
                    time.sleep(0.3)
                    if isinstance(balance_resp, dict) and balance_resp.get('success'):
                        new_balance = balance_resp.get('user', {}).get('balance')

                balance_after_decimal = Decimal(str(new_balance)) if new_balance is not None else None

                Transaction.objects.create(
                    user=request.user,
                    transaction_type='transfer_out',
                    amount=amount,
                    counterpart_payment_number=recipient,
                    note=note[:500] if note else '',
                    status='completed',
                    balance_after=balance_after_decimal,
                )
                messages.success(request, f"Successfully transferred {amount:.2f} NE to account {recipient}.")

                try:
                    from .Utils.email_utils import send_transfer_notification
                    send_transfer_notification(
                        user=request.user,
                        amount=amount,
                        recipient_number=recipient,
                        note=note,
                        balance_after=balance_after_decimal,
                        direction='out',
                    )
                except Exception:
                    pass  # Email failure must never break the transfer flow
            else:
                error_msg = result.get('message', 'Transfer failed.') if isinstance(result, dict) else 'Transfer failed.'
                messages.error(request, f"Transfer failed: {error_msg}")
                # Record failed transaction attempt
                Transaction.objects.create(
                    user=request.user,
                    transaction_type='transfer_out',
                    amount=amount,
                    counterpart_payment_number=recipient,
                    note=note[:500] if note else '',
                    status='failed',
                )
        except Exception as e:
            messages.error(request, "An unexpected error occurred. Please try again.")
            # Log the exception server-side without exposing details to user
            logger.error(f"Transfer error for user {request.user.id}: {e}")


def _handle_freeze_card(request, card_id=None):
    """Freeze a specific card (by Django BankCard id)."""
    qs = BankCard.objects.filter(user=request.user)
    if card_id:
        qs = qs.filter(pk=card_id)
    card = qs.first()
    if card:
        if card.status == 'cancelled':
            messages.error(request, "This card has been cancelled and cannot be modified.")
            return
        card.status = 'frozen'
        card.save(update_fields=['status', 'updated_at'])
        messages.success(request, f"Card ending {card.payment_number[-4:]} has been frozen.")
    else:
        messages.error(request, "No card found to freeze.")


def _handle_unfreeze_card(request, card_id=None):
    """Unfreeze a specific card (by Django BankCard id)."""
    qs = BankCard.objects.filter(user=request.user)
    if card_id:
        qs = qs.filter(pk=card_id)
    card = qs.first()
    if card:
        if card.status == 'cancelled':
            messages.error(request, "This card has been cancelled and cannot be reactivated.")
            return
        card.status = 'active'
        card.save(update_fields=['status', 'updated_at'])
        messages.success(request, f"Card ending {card.payment_number[-4:]} has been unfrozen and is now active.")
    else:
        messages.error(request, "No card found to unfreeze.")


# ---------------------------------------------------------------------------
# Banking logout
# ---------------------------------------------------------------------------

@login_required()
def logout(request):
    """Clear the banking PIN session (does not log out of Django)."""
    request.session.pop('pin_expiry', None)
    return redirect("/banking/")


@login_required()
def user_profile(request, user_id):
    cli, sid = make_connection()
    if cli is not False and cli is not None:
        response = cli.get_user(sid, user_id)
        cli.close_session(sid)
        cli.close()
        return JsonResponse(response)
    return JsonResponse({"error": "unavailable"})


@login_required()
def pin_skip(request):
    request.session['pin_expiry'] = int(time.time()) + 3600
    return redirect('/banking/dashboard/')


@login_required()
def set_webhook(request):
    import requests as _requests
    if request.method == 'POST':
        url = request.POST.get('webhook_url')
        try:
            r = _requests.get(url, timeout=5)
            return JsonResponse({"status": "tested", "code": r.status_code, "body": r.text[:500]})
        except Exception as e:
            return JsonResponse({"status": "failed", "error": str(e)})
    return render(request, "account/webhook.html")


@csrf_exempt
@login_required()
def quick_transfer(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"error": "invalid JSON"}, status=400)
    cli, sid = make_connection()
    if cli is not False and cli is not None:
        payload = {"command": data.get("action", "tr"), "sid": sid}
        payload.update(data)
        cli.send(payload)
        response = cli.receive()
        try:
            cli.close_session(sid)
            cli.close()
        except Exception:
            pass
        return JsonResponse(response or {"error": "no response"})
    return JsonResponse({"error": "unavailable"})
