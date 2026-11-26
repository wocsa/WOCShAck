import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Beneficiary
from .Utils.external_calls import get_user_by_payment_number
from .Utils.expiry import is_session_expired


# ---------------------------------------------------------------------------
# Beneficiary management
# ---------------------------------------------------------------------------

@login_required()
def beneficiary_list(request):
    """
    Display and manage saved beneficiaries.

    GET: List all beneficiaries.
    POST (add): Save a new beneficiary.
    POST (delete): Remove a beneficiary.
    """
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return redirect("/banking/verification/")

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            label = request.POST.get('label', '').strip()[:100]
            account_number = request.POST.get('account_number', '').strip()

            if not label:
                messages.error(request, "Label is required.")
            elif not account_number.isdigit() or len(account_number) != 16:
                messages.error(request, "Account number must be exactly 16 digits.")
            else:
                # Validate account exists on backend
                resp = get_user_by_payment_number(account_number)
                account_valid = isinstance(resp, dict) and resp.get('success')
                display_name = ''

                if not account_valid:
                    messages.error(request, "Account number not found. Please verify the number.")
                else:
                    try:
                        Beneficiary.objects.create(
                            user=request.user,
                            label=label,
                            account_number=account_number,
                            display_name=display_name,
                        )
                        messages.success(request, f"Beneficiary '{label}' added successfully.")
                    except Exception:
                        messages.error(request, "This account number is already saved as a beneficiary.")

        elif action == 'delete':
            beneficiary_id = request.POST.get('beneficiary_id')
            deleted_count, _ = Beneficiary.objects.filter(
                pk=beneficiary_id, user=request.user
            ).delete()
            if deleted_count:
                messages.success(request, "Beneficiary removed.")
            else:
                messages.error(request, "Beneficiary not found.")

        return redirect('/banking/beneficiaries/')

    beneficiaries = Beneficiary.objects.filter(user=request.user)
    return render(request, "account/beneficiaries.html", {
        "beneficiaries": beneficiaries,
    })


@require_POST
@login_required()
def add_beneficiary_ajax(request):
    """
    AJAX endpoint to add a beneficiary.
    Returns JSON. Used from the transfer form quick-save.
    """
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return JsonResponse({'success': False, 'message': 'Banking session expired.'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid request format.'}, status=400)

    label = str(data.get('label', '')).strip()[:100]
    account_number = str(data.get('account_number', '')).strip()

    if not label:
        return JsonResponse({'success': False, 'message': 'Label is required.'}, status=400)
    if not account_number.isdigit() or len(account_number) != 16:
        return JsonResponse({'success': False, 'message': 'Account number must be exactly 16 digits.'}, status=400)

    if Beneficiary.objects.filter(user=request.user, account_number=account_number).exists():
        return JsonResponse({'success': False, 'message': 'This account is already saved.'}, status=400)

    # Cap at 50 beneficiaries
    if Beneficiary.objects.filter(user=request.user).count() >= 50:
        return JsonResponse({'success': False, 'message': 'Maximum of 50 beneficiaries reached.'}, status=400)

    b = Beneficiary.objects.create(
        user=request.user,
        label=label,
        account_number=account_number,
    )
    return JsonResponse({
        'success': True,
        'message': f"'{label}' saved as beneficiary.",
        'beneficiary': {
            'id': b.id,
            'label': b.label,
            'masked_number': b.masked_number(),
        },
    })


@require_POST
@login_required()
def delete_beneficiary_ajax(request, beneficiary_id):
    """
    AJAX endpoint to delete a beneficiary.
    Ownership enforced by filtering on request.user.
    """
    deleted, _ = Beneficiary.objects.filter(
        pk=beneficiary_id, user=request.user
    ).delete()
    if deleted:
        return JsonResponse({'success': True, 'message': 'Beneficiary removed.'})
    return JsonResponse({'success': False, 'message': 'Beneficiary not found.'}, status=404)
