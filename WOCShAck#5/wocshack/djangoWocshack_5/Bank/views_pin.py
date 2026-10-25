import json
import time

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .Utils.external_calls import backend_connection, get_user_attempts
from .Utils.expiry import is_session_expired


# ---------------------------------------------------------------------------
# PIN verification
# ---------------------------------------------------------------------------

@login_required()
def bank_pin(request):
    is_locked = False
    attempts = get_user_attempts(request.user.id)
    if attempts is not None and int(attempts) >= 3:
        is_locked = True
    return render(request, "account/pin.html", {'is_locked': is_locked})


@require_POST
@login_required()
def verify_pin(request):
    # PIN verification uses constant-time comparison on the backend.
    # Failed attempts are tracked in the VRC backend (max 3 before lockout).
    try:
        data = json.loads(request.body)
        pin = data.get('pin')

        if not pin:
            return JsonResponse({'success': False, 'message': 'PIN is required.'}, status=400)

        with backend_connection() as (cli, sid):
            if not cli or not sid:
                return JsonResponse({'success': False, 'message': 'Banking server unreachable. Please try again later.'}, status=503)

            # Verify user account exists
            user_data = cli.get_user(sid, request.user.id)
            if not isinstance(user_data, dict) or not user_data.get("success"):
                return JsonResponse({
                    'success': False,
                    'message': 'Bank account not found. Please contact support or run setup_database.py'
                }, status=400)

            # Check current attempts before proceeding
            attempts_response = cli.get_attempts(sid, request.user.id)
            time.sleep(0.3)
            attempts_count = attempts_response.get('attempts', 0) if isinstance(attempts_response, dict) else 0

            if attempts_count is not None and int(attempts_count) >= 3:
                return JsonResponse({
                    'success': False,
                    'message': 'Account locked due to too many failed attempts. Please contact support.'
                }, status=403)

            # Verify PIN
            verify_result = cli.verify(sid, request.user.id, pin)
            time.sleep(0.3)

            if verify_result == {'status': 'success'}:
                # PIN correct - set session expiry (10 minutes)
                request.session['pin_expiry'] = int(time.time()) + 10 * 60
                cli.reset_attempts(sid, request.user.id)
                time.sleep(0.3)
                return JsonResponse({
                    'success': True,
                    'message': 'PIN Verified Successfully!',
                    'redirect_url': '/banking/dashboard/'
                })
            else:
                # PIN wrong - increment attempts
                cli.increment_attempts(sid, request.user.id)
                time.sleep(0.3)
                attempts_response = cli.get_attempts(sid, request.user.id)
                time.sleep(0.3)
                new_attempts = attempts_response.get('attempts', 0) if isinstance(attempts_response, dict) else 0

                if new_attempts is not None and int(new_attempts) >= 3:
                    return JsonResponse({
                        'success': False,
                        'message': 'Account locked due to too many failed attempts. Please contact support.'
                    }, status=403)

                remaining = max(0, 3 - int(new_attempts))
                return JsonResponse({
                    'success': False,
                    'message': f'Invalid PIN. {remaining} attempt(s) remaining.'
                }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid request format.'}, status=400)


# ---------------------------------------------------------------------------
# PIN change (requires active PIN session)
# ---------------------------------------------------------------------------

@require_POST
@login_required()
def change_pin(request):
    """
    Change the user's bank PIN.

    Requires:
      - Current PIN (verified against backend)
      - New PIN (6 digits)
      - Account password (Django auth check)

    All three must be correct before the new PIN is set.
    """
    # Guard: require active PIN session
    if is_session_expired(request.session) is False or request.session.get('pin_expiry') is None:
        return JsonResponse({'success': False, 'message': 'Banking session expired. Please verify your PIN.'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid request format.'}, status=400)

    current_pin = str(data.get('current_pin', '')).strip()
    new_pin = str(data.get('new_pin', '')).strip()
    password = str(data.get('password', '')).strip()

    if not current_pin or not new_pin or not password:
        return JsonResponse({'success': False, 'message': 'All fields are required.'}, status=400)

    if not new_pin.isdigit() or len(new_pin) != 6:
        return JsonResponse({'success': False, 'message': 'New PIN must be exactly 6 digits.'}, status=400)

    if not request.user.check_password(password):
        return JsonResponse({'success': False, 'message': 'Incorrect account password.'}, status=400)

    with backend_connection() as (cli, sid):
        if not cli or not sid:
            return JsonResponse({'success': False, 'message': 'Banking server unreachable. Please try again later.'}, status=503)

        # Verify current PIN against backend
        verify_result = cli.verify(sid, request.user.id, current_pin)
        time.sleep(0.3)

        if verify_result != {'status': 'success'}:
            # Increment failed attempts
            cli.increment_attempts(sid, request.user.id)
            time.sleep(0.3)
            return JsonResponse({'success': False, 'message': 'Current PIN is incorrect.'}, status=400)

        # Set new PIN
        set_result = cli.set_pin(sid, request.user.id, new_pin)
        time.sleep(0.3)

        if isinstance(set_result, dict) and set_result.get('status') == 'success':
            # Reset attempts after successful PIN change
            cli.reset_attempts(sid, request.user.id)
            time.sleep(0.3)
            # Invalidate current banking session so user must re-verify with new PIN
            request.session.pop('pin_expiry', None)
            return JsonResponse({
                'success': True,
                'message': 'PIN changed successfully. Please re-verify with your new PIN.',
            })
        else:
            error_msg = set_result.get('message', 'Failed to update PIN.') if isinstance(set_result, dict) else 'Failed to update PIN.'
            return JsonResponse({'success': False, 'message': error_msg}, status=500)


# ---------------------------------------------------------------------------
# PIN reset (self-service unlock for locked accounts)
# ---------------------------------------------------------------------------

@login_required()
def reset_pin(request):
    """
    Self-service PIN reset for locked accounts.

    GET: Render the reset PIN form.
    POST (JSON): Validate account password, then set a new 6-digit PIN and
                 unlock the account (reset failed attempts counter).
    No PIN session required -- the whole point is that the user is locked out.
    """
    if request.method == 'GET':
        return render(request, "account/reset_pin.html")

    # POST path -- expect JSON body
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid request format.'}, status=400)

    new_pin = str(data.get('new_pin', '')).strip()
    confirm_pin = str(data.get('confirm_pin', '')).strip()
    password = str(data.get('password', '')).strip()

    if not new_pin or not confirm_pin or not password:
        return JsonResponse({'success': False, 'message': 'All fields are required.'}, status=400)

    if not request.user.check_password(password):
        return JsonResponse({'success': False, 'message': 'Incorrect account password.'}, status=400)

    if not new_pin.isdigit() or len(new_pin) != 6:
        return JsonResponse({'success': False, 'message': 'PIN must be exactly 6 digits.'}, status=400)

    if new_pin != confirm_pin:
        return JsonResponse({'success': False, 'message': 'PINs do not match.'}, status=400)

    with backend_connection() as (cli, sid):
        if not cli or not sid:
            return JsonResponse({'success': False, 'message': 'Banking server unreachable. Please try again later.'}, status=503)

        cli.reset_attempts(sid, request.user.id)
        time.sleep(0.3)
        set_result = cli.set_pin(sid, request.user.id, new_pin)
        time.sleep(0.3)

        if isinstance(set_result, dict) and set_result.get('status') == 'success':
            return JsonResponse({
                'success': True,
                'redirect_url': '/banking/verification/',
            })
        else:
            error_msg = set_result.get('message', 'Failed to update PIN.') if isinstance(set_result, dict) else 'Failed to update PIN.'
            return JsonResponse({'success': False, 'message': error_msg}, status=500)
