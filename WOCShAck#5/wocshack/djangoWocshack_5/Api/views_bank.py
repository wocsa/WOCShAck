import json
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_http_methods
from Bank.models import BankCard, Transaction, Beneficiary
from Bank.Utils import client
from .views import api_success, api_error, api_auth_required, paginate_queryset

@require_http_methods(["GET"])
@api_auth_required
def balance_view(request):
    """
    Get auth user's bank balance and main account details.
    """
    cli, sid = client.make_connection()
    if not cli or not sid:
        return api_error("Banking server unreachable. Please try again later.", status=503)

    try:
        response = cli.get_user(sid, request.user.id)
        if isinstance(response, dict) and response.get("success"):
            user_data = response.get("user", {})
            return api_success({
                "balance": user_data.get("balance"),
                "account_number": user_data.get("account_number", user_data.get("payment_number")),
                "payment_number": user_data.get("payment_number"),
            })
        return api_error("Bank account not found. Please activate via dashboard.", status=404)
    finally:
        try:
            cli.close_session(sid)
            cli.close()
        except:
            pass


@require_http_methods(["GET"])
@api_auth_required
def transactions_view(request, transaction_id=None):
    """
    List or retrieve specific transactions for the current user.
    """
    if transaction_id:
        try:
            tx = Transaction.objects.get(id=transaction_id, user=request.user)
            tx_data = {
                "id": tx.id,
                "type": tx.transaction_type,
                "amount": float(tx.amount),
                "counterpart_number": tx.counterpart_payment_number,
                "note": tx.note,
                "status": tx.status,
                "balance_after": float(tx.balance_after) if tx.balance_after else None,
                "created_at": tx.created_at.isoformat(),
            }
            return api_success({"transaction": tx_data})
        except Transaction.DoesNotExist:
            return api_error("Transaction not found.", status=404)

    # List all transactions
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    paginated = paginate_queryset(transactions, request, default_per_page=20)
    
    data = []
    for tx in paginated['items']:
        data.append({
            "id": tx.id,
            "type": tx.transaction_type,
            "amount": float(tx.amount),
            "counterpart_number": tx.counterpart_payment_number,
            "status": tx.status,
            "created_at": tx.created_at.isoformat(),
        })

    return api_success({
        "transactions": data,
        "pagination": paginated['pagination']
    })


@require_http_methods(["GET"])
@api_auth_required
def cards_view(request):
    """
    Fetch all bank cards associated with the user account.
    """
    cards = BankCard.objects.filter(user=request.user).order_by('-created_at')
    
    data = []
    for card in cards:
        data.append({
            "id": card.id,
            "card_type": card.card_type,
            "status": card.status,
            "masked_number": card.masked_number(),
            "created_at": card.created_at.isoformat(),
        })
        
    return api_success({"cards": data})


@require_http_methods(["POST"])
@api_auth_required
def transfer_view(request):
    """
    Initiate a money transfer.
    Expects JSON: {"recipient": "16_digit_account_number_or_card_number", "amount": 10.50, "pin": "1234", "note": "optional"}
    Requires bank PIN verification before executing the transfer.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)
        
    recipient = str(data.get('recipient', '')).strip()
    amount_str = str(data.get('amount', '')).strip()
    note = str(data.get('note', '')).strip()
    pin = str(data.get('pin', '')).strip()

    if not recipient or not amount_str:
        return api_error("Recipient and amount are required.", status=400)

    if not pin:
        return api_error("Bank PIN is required for transfers.", status=400)

    from Bank.Utils.external_calls import verify_user_pin
    if not verify_user_pin(request.user.id, pin):
        return api_error("Incorrect bank PIN.", status=403)

    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            return api_error("Amount must be greater than zero.", status=400)
    except (ValueError, InvalidOperation):
        return api_error("Invalid amount entered.", status=400)

    cli, sid = client.make_connection()
    if not cli or not sid:
        return api_error("Banking server unreachable. Please try again later.", status=503)

    try:
        # Sender Look Up
        user_response = cli.get_user(sid, request.user.id)
        if not isinstance(user_response, dict) or not user_response.get("success"):
            return api_error("Sender bank account not found.", status=400)

        sender_id = user_response.get("user", {}).get("id")
        current_balance = Decimal(str(user_response.get("user", {}).get("balance", 0)))
        
        if amount > current_balance:
            return api_error("Insufficient balance.", status=400)

        # Recipient Look Up
        recipient_response = cli.get_user_by_payment_number(sid, recipient)
        if not isinstance(recipient_response, dict) or not recipient_response.get("success"):
            return api_error("Recipient account not found.", status=400)

        recipient_id = recipient_response.get("user", {}).get("id")
        
        if str(sender_id) == str(recipient_id):
            return api_error("You cannot transfer money to yourself.", status=400)

        # Perform Transfer
        result = cli.transaction(sid=sid, from_user=sender_id, to_user=recipient_id, amount=float(amount))
        
        if isinstance(result, dict) and result.get('status') == 'success':
            Transaction.objects.create(
                user=request.user,
                transaction_type='transfer_out',
                amount=amount,
                counterpart_payment_number=recipient,
                note=note[:500],
                status='completed',
            )
            return api_success({}, message=f"Successfully transferred {amount} NS to {recipient}.")
        else:
            error_msg = result.get('message', 'Transfer failed.') if isinstance(result, dict) else 'Transfer failed.'
            Transaction.objects.create(
                user=request.user,
                transaction_type='transfer_out',
                amount=amount,
                counterpart_payment_number=recipient,
                note=note[:500],
                status='failed',
            )
            return api_error(f"Transfer failed: {error_msg}", status=400)
    finally:
        try:
            cli.close_session(sid)
            cli.close()
        except:
            pass


@require_http_methods(["GET", "POST", "DELETE"])
@api_auth_required
def beneficiaries_view(request, beneficiary_id=None):
    """
    Manage beneficiaries.
    """
    if request.method == "GET":
        beneficiaries = Beneficiary.objects.filter(user=request.user).order_by('label')
        data = []
        for b in beneficiaries:
            data.append({
                "id": b.id,
                "label": b.label,
                "account_number": b.account_number,
                "masked_number": b.masked_number(),
                "display_name": b.display_name,
                "created_at": b.created_at.isoformat()
            })
        return api_success({"beneficiaries": data})

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return api_error("Invalid JSON format.", status=400)
            
        label = data.get("label", "").strip()
        account_number = data.get("account_number", "").strip()
        
        if len(account_number) != 16 or not account_number.isdigit():
            return api_error("Account number must be 16 numeric digits.", status=400)
            
        if not label:
            return api_error("Label is required.", status=400)

        # Verify recipient account
        cli, sid = client.make_connection()
        if cli and sid:
            recipient_resp = cli.get_user_by_payment_number(sid, account_number)
            cli.close_session(sid)
            cli.close()
            
            if not (isinstance(recipient_resp, dict) and recipient_resp.get("success")):
                return api_error("Beneficiary account number not found in banking system.", status=400)
        
        # Check if already exists
        if Beneficiary.objects.filter(user=request.user, account_number=account_number).exists():
            return api_error("Beneficiary with this account number already exists.", status=400)
            
        beneficiary = Beneficiary.objects.create(
            user=request.user,
            label=label,
            account_number=account_number,
        )
        
        return api_success({
            "id": beneficiary.id,
            "label": beneficiary.label,
            "account_number": beneficiary.account_number,
            "masked_number": beneficiary.masked_number()
        }, message="Beneficiary added successfully.", status=201)

    elif request.method == "DELETE":
        if not beneficiary_id:
            return api_error("Beneficiary ID required.", status=400)
            
        try:
            beneficiary = Beneficiary.objects.get(id=beneficiary_id, user=request.user)
            beneficiary.delete()
            return api_success({}, message="Beneficiary removed successfully.")
        except Beneficiary.DoesNotExist:
            return api_error("Beneficiary not found.", status=404)


@require_http_methods(["DELETE"])
@api_auth_required
def beneficiary_delete_view(request, beneficiary_id):
    """DELETE-only beneficiary alias for the detail route."""
    try:
        beneficiary = Beneficiary.objects.get(id=beneficiary_id, user=request.user)
        beneficiary.delete()
        return api_success({}, message="Beneficiary removed successfully.")
    except Beneficiary.DoesNotExist:
        return api_error("Beneficiary not found.", status=404)


@require_http_methods(["POST"])
@api_auth_required
def card_generate_view(request):
    """
    Generate a new bank card (virtual or physical).
    Expects JSON: {"card_type": "virtual"|"physical"}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    card_type = data.get('card_type', 'virtual').lower()
    if card_type not in ('virtual', 'physical'):
        return api_error("card_type must be 'virtual' or 'physical'.", status=400)

    cli, sid = client.make_connection()
    if not cli or not sid:
        return api_error("Banking server unreachable. Please try again later.", status=503)

    try:
        result = cli.add_card(sid, request.user.id, card_type)
        if not (isinstance(result, dict) and result.get('success')):
            error_msg = result.get('message', 'Card generation failed.') if isinstance(result, dict) else 'Card generation failed.'
            return api_error(f"Card generation failed: {error_msg}", status=400)

        card_data = result.get('card', {})
        card_number = str(card_data.get('card_number', '') or card_data.get('payment_number', ''))

        card, _ = BankCard.objects.get_or_create(
            payment_number=card_number,
            defaults={
                'user': request.user,
                'card_type': card_type,
                'status': 'active',
            },
        )
        return api_success({
            'id': card.id,
            'card_type': card.card_type,
            'status': card.status,
            'masked_number': card.masked_number(),
            'created_at': card.created_at.isoformat(),
        }, message="Card generated successfully.", status=201)
    finally:
        try:
            cli.close_session(sid)
            cli.close()
        except Exception:
            pass


@require_http_methods(["POST"])
@api_auth_required
def card_freeze_view(request, card_id):
    """
    Freeze or unfreeze a bank card.
    Toggles between 'active' and 'frozen'. Cannot act on cancelled cards.
    """
    try:
        card = BankCard.objects.get(id=card_id, user=request.user)
    except BankCard.DoesNotExist:
        return api_error("Card not found.", status=404)

    if card.status in ('cancelled', 'pending_replacement'):
        return api_error(f"Cannot freeze a {card.status} card.", status=400)

    new_status = 'active' if card.status == 'frozen' else 'frozen'

    # Sync with VRC backend when available
    cli, sid = client.make_connection()
    if cli and sid:
        try:
            cli.set_card_status(sid, card.payment_number, new_status)
        except Exception:
            pass
        finally:
            try:
                cli.close_session(sid)
                cli.close()
            except Exception:
                pass

    card.status = new_status
    card.save()
    action = "unfrozen" if new_status == 'active' else "frozen"
    return api_success({'id': card.id, 'status': card.status}, message=f"Card {action} successfully.")


@require_http_methods(["POST"])
@api_auth_required
def card_toggle_view(request, card_id):
    """
    Toggle card between active and frozen.
    Alias of freeze for clients that prefer a toggle semantic.
    """
    try:
        card = BankCard.objects.get(id=card_id, user=request.user)
    except BankCard.DoesNotExist:
        return api_error("Card not found.", status=404)

    if card.status in ('cancelled', 'pending_replacement'):
        return api_error(f"Cannot toggle a {card.status} card.", status=400)

    new_status = 'active' if card.status == 'frozen' else 'frozen'

    cli, sid = client.make_connection()
    if cli and sid:
        try:
            cli.set_card_status(sid, card.payment_number, new_status)
        except Exception:
            pass
        finally:
            try:
                cli.close_session(sid)
                cli.close()
            except Exception:
                pass

    card.status = new_status
    card.save()
    action = "activated" if new_status == 'active' else "deactivated"
    return api_success({'id': card.id, 'status': card.status}, message=f"Card {action} successfully.")


@require_http_methods(["PATCH"])
@api_auth_required
def card_spending_limit_view(request, card_id):
    """
    Update spending limits on a card.
    Expects JSON with any subset of: daily_limit, weekly_limit, monthly_limit.
    Pass null to remove a limit.
    """
    try:
        card = BankCard.objects.get(id=card_id, user=request.user)
    except BankCard.DoesNotExist:
        return api_error("Card not found.", status=404)

    if card.status == 'cancelled':
        return api_error("Cannot set limits on a cancelled card.", status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    updated = {}
    for field in ('daily_limit', 'weekly_limit', 'monthly_limit'):
        if field in data:
            value = data[field]
            if value is None:
                setattr(card, field, None)
                updated[field] = None
            else:
                try:
                    amount = Decimal(str(value))
                    if amount < 0:
                        return api_error(f"{field} must be non-negative.", status=400)
                    setattr(card, field, amount)
                    updated[field] = float(amount)
                except (ValueError, Exception):
                    return api_error(f"Invalid value for {field}.", status=400)

    if not updated:
        return api_error("Provide at least one of: daily_limit, weekly_limit, monthly_limit.", status=400)

    card.save()
    return api_success({
        'id': card.id,
        'daily_limit': float(card.daily_limit) if card.daily_limit is not None else None,
        'weekly_limit': float(card.weekly_limit) if card.weekly_limit is not None else None,
        'monthly_limit': float(card.monthly_limit) if card.monthly_limit is not None else None,
    }, message="Spending limits updated successfully.")


@require_http_methods(["GET"])
@api_auth_required
def statement_view(request):
    """
    Download PDF account statement.
    Proxies to the Bank module's PDF statement generator (requires active session).
    """
    from django.shortcuts import redirect
    return redirect('/banking/statement/')


@require_http_methods(["GET"])
@api_auth_required
def export_view(request):
    """
    Return transaction history in requested format (JSON, CSV, XML).
    """
    format_type = request.GET.get('format', 'json').lower()
    
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    
    if format_type == 'json':
        data = []
        for tx in transactions:
            data.append({
                "id": tx.id,
                "type": tx.transaction_type,
                "amount": float(tx.amount),
                "counterpart_number": tx.counterpart_payment_number,
                "status": tx.status,
                "created_at": tx.created_at.isoformat(),
            })
        return api_success({"transactions": data})
        
    elif format_type == 'csv':
        from django.http import HttpResponse
        import csv
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="statement.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Type', 'Amount', 'Counterpart', 'Status', 'Note'])
        
        for tx in transactions:
            writer.writerow([
                tx.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                tx.transaction_type,
                f"{tx.amount:.2f}",
                tx.counterpart_payment_number,
                tx.status,
                tx.note
            ])
        return response
        
    elif format_type == 'xml':
        from django.http import HttpResponse
        import xml.etree.ElementTree as ET
        
        root = ET.Element('Statement')
        for tx in transactions:
            tx_elem = ET.SubElement(root, 'Transaction')
            ET.SubElement(tx_elem, 'Date').text = tx.created_at.strftime("%Y-%m-%d %H:%M:%S")
            ET.SubElement(tx_elem, 'Type').text = tx.transaction_type
            ET.SubElement(tx_elem, 'Amount').text = f"{tx.amount:.2f}"
            ET.SubElement(tx_elem, 'Counterpart').text = tx.counterpart_payment_number
            ET.SubElement(tx_elem, 'Status').text = tx.status
            
        xml_str = ET.tostring(root, encoding='utf-8', method='xml').decode('utf-8')
        response = HttpResponse(xml_str, content_type='application/xml')
        response['Content-Disposition'] = 'attachment; filename="statement.xml"'
        return response
        
    return api_error("Invalid format type. Supported formats: json, csv, xml", status=400)
