import time
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import BankCard
from .Utils.external_calls import add_card
from .Utils.expiry import is_session_expired


# ---------------------------------------------------------------------------
# Card management AJAX endpoints
# ---------------------------------------------------------------------------

@require_POST
@login_required()
def toggle_card_freeze(request):
    """AJAX endpoint to freeze or unfreeze the user's first (default) card."""
    card = BankCard.objects.filter(user=request.user).first()
    if not card:
        return JsonResponse({'success': False, 'message': 'No card found.'}, status=404)

    if card.status == 'active':
        card.status = 'frozen'
        card.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'success': True, 'status': 'frozen', 'message': 'Card frozen successfully.'})
    elif card.status == 'frozen':
        card.status = 'active'
        card.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'success': True, 'status': 'active', 'message': 'Card unfrozen successfully.'})
    else:
        return JsonResponse({'success': False, 'message': 'Card cannot be modified in its current state.'}, status=400)


@require_POST
@login_required()
def toggle_card_status(request, card_id):
    """AJAX endpoint to freeze or unfreeze a specific card by Django BankCard id."""
    card = BankCard.objects.filter(user=request.user, pk=card_id).first()
    if not card:
        return JsonResponse({'success': False, 'message': 'Card not found.'}, status=404)

    if card.status == 'cancelled':
        return JsonResponse({'success': False, 'message': 'Cancelled cards cannot be modified.'}, status=400)

    if card.status == 'active':
        card.status = 'frozen'
        card.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'success': True, 'new_status': 'frozen', 'message': f'Card ending {card.payment_number[-4:]} frozen.'})
    elif card.status == 'frozen':
        card.status = 'active'
        card.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'success': True, 'new_status': 'active', 'message': f'Card ending {card.payment_number[-4:]} unfrozen.'})
    else:
        return JsonResponse({'success': False, 'message': 'Card cannot be modified.'}, status=400)


@require_POST
@login_required()
def generate_card(request):
    """AJAX endpoint to generate a new card for the authenticated user."""
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return JsonResponse({'success': False, 'message': 'Banking session expired. Please verify your PIN.'}, status=403)

    card_type = request.POST.get('card_type', 'virtual')
    if card_type not in ('virtual', 'physical'):
        card_type = 'virtual'

    result = add_card(request.user.id, card_type)
    time.sleep(0.3)

    if not isinstance(result, dict) or not result.get('success'):
        error_msg = result.get('error', 'Card generation failed.') if isinstance(result, dict) else 'Card generation failed.'
        return JsonResponse({'success': False, 'message': error_msg}, status=400)

    card_data = result.get('card', {})
    card_number = str(card_data.get('card_number', ''))

    if not card_number:
        return JsonResponse({'success': False, 'message': 'Invalid card number returned from backend.'}, status=500)

    new_card, _ = BankCard.objects.get_or_create(
        payment_number=card_number,
        defaults={
            'user': request.user,
            'card_type': card_type,
            'status': 'active',
        },
    )

    return JsonResponse({
        'success': True,
        'message': f'New {card_type} card generated successfully.',
        'card': {
            'id': new_card.id,
            'card_type': new_card.card_type,
            'status': new_card.status,
            'masked_number': new_card.masked_number(),
            'created_at': new_card.created_at.strftime('%b %d, %Y'),
        }
    })


@require_POST
@login_required()
def replace_card(request, card_id):
    """
    Request a card replacement for lost/stolen/damaged cards.

    Marks the old card as 'pending_replacement' (not yet cancelled until new
    card is confirmed), creates a new card from the backend, and links them.

    Requires active PIN session for security.
    """
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return JsonResponse({'success': False, 'message': 'Banking session expired. Please verify your PIN.'}, status=403)

    card = get_object_or_404(BankCard, pk=card_id, user=request.user)

    if card.status == 'cancelled':
        return JsonResponse({'success': False, 'message': 'This card has already been cancelled.'}, status=400)
    if card.status == 'pending_replacement':
        return JsonResponse({'success': False, 'message': 'A replacement for this card is already in progress.'}, status=400)

    reason = request.POST.get('reason', 'lost')
    allowed_reasons = ('lost', 'stolen', 'damaged', 'expired', 'other')
    if reason not in allowed_reasons:
        reason = 'other'

    result = add_card(request.user.id, card.card_type)
    time.sleep(0.3)

    if not isinstance(result, dict) or not result.get('success'):
        error_msg = result.get('error', 'Card replacement failed.') if isinstance(result, dict) else 'Card replacement failed.'
        return JsonResponse({'success': False, 'message': error_msg}, status=400)

    card_data = result.get('card', {})
    new_card_number = str(card_data.get('card_number', ''))

    if not new_card_number:
        return JsonResponse({'success': False, 'message': 'Invalid card number returned from backend.'}, status=500)

    # Create replacement card record (get_or_create to prevent duplicates from retries)
    new_card, _ = BankCard.objects.get_or_create(
        payment_number=new_card_number,
        defaults={
            'user': request.user,
            'card_type': card.card_type,
            'status': 'active',
        },
    )

    # Mark old card as pending_replacement (will be cancelled once user acknowledges)
    card.status = 'pending_replacement'
    card.replacement_reason = reason
    card.replaced_at = timezone.now()
    card.replaced_by = new_card
    card.save(update_fields=['status', 'replacement_reason', 'replaced_at', 'replaced_by', 'updated_at'])

    return JsonResponse({
        'success': True,
        'message': (
            f'Card ending {card.payment_number[-4:]} is being replaced. '
            f'Your new card ending {new_card.payment_number[-4:]} is now active.'
        ),
        'new_card': {
            'id': new_card.id,
            'masked_number': new_card.masked_number(),
            'card_type': new_card.card_type,
            'status': new_card.status,
        },
    })


@require_POST
@login_required()
def cancel_card(request, card_id):
    """
    Permanently cancel a card.

    Requires active PIN session. Does not remove the record (audit trail).
    """
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return JsonResponse({'success': False, 'message': 'Banking session expired. Please verify your PIN.'}, status=403)

    card = get_object_or_404(BankCard, pk=card_id, user=request.user)

    if card.status == 'cancelled':
        return JsonResponse({'success': False, 'message': 'Card is already cancelled.'}, status=400)

    card.status = 'cancelled'
    card.save(update_fields=['status', 'updated_at'])

    return JsonResponse({
        'success': True,
        'message': f'Card ending {card.payment_number[-4:]} has been permanently cancelled.',
    })

