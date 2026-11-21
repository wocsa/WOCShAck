import json
from decimal import Decimal
from django.contrib.auth.models import User
from django.db import transaction as db_transaction
from django.db.models import Q
from django.views.decorators.http import require_http_methods
from Account.models import UserProfile, UserSession, LoginHistory, BackupCode, PurchasedFeature
from Bank.Utils import client
from .views import api_success, api_error, api_auth_required, paginate_queryset

@require_http_methods(["GET", "PATCH"])
@api_auth_required
def profile_view(request):
    """
    Get or update authenticated user's profile.
    GET: Returns extended profile information including badges and role.
    PATCH: Updates allowed profile fields.
    """
    user = request.user
    
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        # Create profile if it doesn't exist
        profile = UserProfile.objects.create(user=user)

    if request.method == "GET":
        return api_success({
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'bio': profile.biography,
            'picture_path': profile.picture_path,
            'is_activated': profile.is_activated,
            'completion': profile.get_profile_completion(),
            'role': profile.get_user_role(),
            'badges': profile.get_all_badges()
        })

    elif request.method == "PATCH":
        try:
            data = json.loads(request.body)
            
            # Update User fields
            if 'email' in data:
                user.email = data['email']
            if 'first_name' in data:
                user.first_name = data['first_name']
            if 'last_name' in data:
                user.last_name = data['last_name']
            user.save()
            
            # Update Profile fields
            if 'bio' in data:
                profile.biography = data['bio']
            if 'picture_path' in data:
                profile.picture_path = data['picture_path']
            profile.save()
            
            return api_success({
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'bio': profile.biography,
                'picture_path': profile.picture_path
            }, message="Profile updated successfully.")
            
        except json.JSONDecodeError:
            return api_error("Invalid JSON format.", status=400)
        except Exception as e:
            return api_error(str(e), status=500)


@require_http_methods(["GET"])
@api_auth_required
def public_profile_view(request, username):
    """
    Get public profile information for any user.
    """
    try:
        target_user = User.objects.get(username=username)
        
        try:
            profile = target_user.profile
        except UserProfile.DoesNotExist:
            return api_error("User profile not found.", status=404)
            
        return api_success({
            'username': target_user.username,
            'bio': profile.biography,
            'picture_path': profile.picture_path,
            'role': profile.get_user_role(),
            'badges': profile.get_all_badges(),
            'date_joined': target_user.date_joined.isoformat() if target_user.date_joined else None
        })
    except User.DoesNotExist:
        return api_error("User not found.", status=404)


@require_http_methods(["GET"])
@api_auth_required
def sessions_view(request):
    """
    List active sessions for the current user.
    """
    sessions = UserSession.objects.filter(user=request.user, is_active=True).order_by('-last_activity')
    
    sessions_data = []
    for s in sessions:
        sessions_data.append({
            'id': s.id,
            'ip_address': s.ip_address,
            'device_type': s.device_type,
            'browser_info': s.get_browser_info(),
            'is_current': s.is_current,
            'created_at': s.created_at.isoformat() if s.created_at else None,
            'last_activity': s.last_activity.isoformat() if s.last_activity else None
        })
        
    return api_success({'sessions': sessions_data})


@require_http_methods(["DELETE"])
@api_auth_required
def revoke_session_view(request, session_id):
    """
    Revoke a specific session for the current user.
    """
    try:
        session = UserSession.objects.get(id=session_id, user=request.user)
        session.revoke()
        return api_success({}, message="Session revoked successfully.")
    except UserSession.DoesNotExist:
        return api_error("Session not found.", status=404)


@require_http_methods(["GET"])
@api_auth_required
def login_history_view(request):
    """
    Paginated login history for the current user.
    """
    history = LoginHistory.objects.filter(user=request.user).order_by('-timestamp')
    
    paginated = paginate_queryset(history, request, default_per_page=20)
    
    history_data = []
    for entry in paginated['items']:
        history_data.append({
            'id': entry.id,
            'status': entry.status,
            'ip_address': entry.ip_address,
            'device_type': entry.device_type,
            'timestamp': entry.timestamp.isoformat() if entry.timestamp else None,
            'location': entry.location
        })
        
    return api_success({
        'history': history_data,
        'pagination': paginated['pagination']
    })


@require_http_methods(["GET"])
@api_auth_required
def two_factor_status_view(request):
    """
    Return 2FA status for the current user.
    """
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    backup_codes_remaining = BackupCode.get_remaining_count(request.user)

    return api_success({
        'totp_enabled': bool(profile.totp_key),
        'email_2fa_enabled': profile.email_2fa_enabled,
        'backup_codes_remaining': backup_codes_remaining
    })


@require_http_methods(["GET", "POST"])
@api_auth_required
def backup_codes_view(request):
    """
    Manage backup codes.
    GET: Return remaining backup code count (codes are never re-shown after generation).
    POST {"action": "regenerate"}: Regenerate all backup codes. Returns plaintexts once.
    """
    if request.method == "GET":
        remaining = BackupCode.get_remaining_count(request.user)
        return api_success({'backup_codes_remaining': remaining})

    # POST — regenerate
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    if data.get('action') != 'regenerate':
        return api_error("Unknown action. Use action='regenerate'.", status=400)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return api_error("Profile not found.", status=404)

    if not profile.totp_key and not profile.email_2fa_enabled:
        return api_error("2FA must be enabled before generating backup codes.", status=400)

    codes = BackupCode.generate_codes_for_user(request.user)
    return api_success({
        'codes': codes,
        'count': len(codes),
    }, message="Store these codes securely — they will not be shown again.", status=201)


@require_http_methods(["GET", "POST"])
@api_auth_required
def store_view(request):
    """
    List or purchase premium features.
    GET: Returns available features with ownership status and prices.
    POST {"feature_type": "..."}: Purchases a feature, deducting cost from bank balance.
    """
    _FEATURES = [
        {
            'type': 'verified_badge',
            'name': 'Verified Badge',
            'description': 'Official verified badge shown on your profile.',
            'price': PurchasedFeature.get_price('verified_badge'),
        },
        {
            'type': 'developer_role',
            'name': 'Developer Role',
            'description': 'Unlock the developer tools, CSS editor, and marketplace selling.',
            'price': PurchasedFeature.get_price('developer_role'),
        },
        {
            'type': 'custom_theme',
            'name': 'Custom Profile Theme',
            'description': 'Customise your profile colours (background, text, border).',
            'price': PurchasedFeature.get_price('custom_theme'),
        },
    ]

    if request.method == "GET":
        features = []
        for f in _FEATURES:
            features.append({**f, 'owned': PurchasedFeature.has_feature(request.user, f['type'])})
        return api_success({'features': features})

    # POST — purchase
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    feature_type = data.get('feature_type', '').strip()
    valid_types = [f['type'] for f in _FEATURES]
    if feature_type not in valid_types:
        return api_error(f"Invalid feature_type. Valid values: {', '.join(valid_types)}", status=400)

    # Quick pre-check before touching the bank (avoids unnecessary network call)
    if PurchasedFeature.has_feature(request.user, feature_type):
        return api_error("You already own this feature.", status=400)

    price = PurchasedFeature.get_price(feature_type)

    cli, sid = client.make_connection()
    if not cli or not sid:
        return api_error("Banking server unreachable. Please try again later.", status=503)

    payment_ok = False
    try:
        user_resp = cli.get_user(sid, request.user.id)
        if not isinstance(user_resp, dict) or not user_resp.get('success'):
            return api_error("Bank account not found. Activate your account via the dashboard.", status=404)

        balance = Decimal(str(user_resp.get('user', {}).get('balance', 0)))
        if balance < price:
            return api_error(f"Insufficient balance. Required: {price} NE, available: {balance} NE.", status=400)

        sender_id = user_resp.get('user', {}).get('id')
        result = cli.transaction(sid=sid, from_user=sender_id, to_user=1, amount=float(price))

        if not (isinstance(result, dict) and result.get('status') == 'success'):
            error_msg = result.get('message', 'Payment failed.') if isinstance(result, dict) else 'Payment failed.'
            return api_error(f"Payment failed: {error_msg}", status=400)

        payment_ok = True
    finally:
        try:
            cli.close_session(sid)
            cli.close()
        except Exception:
            pass

    if not payment_ok:
        return api_error("Payment could not be processed.", status=400)

    # Re-check ownership atomically to prevent TOCTOU double-purchase.
    # If a concurrent request also completed payment, get_or_create ensures only
    # one PurchasedFeature row is created (the second caller keeps their item).
    _, created = PurchasedFeature.objects.get_or_create(
        user=request.user,
        feature_type=feature_type,
        defaults={'price_paid': price},
    )

    feature_name = next(f['name'] for f in _FEATURES if f['type'] == feature_type)
    return api_success({
        'feature_type': feature_type,
        'price_paid': price,
    }, message=f"Successfully purchased {feature_name}.", status=201)


@require_http_methods(["GET"])
@api_auth_required
def user_search_view(request):
    """
    Search users by username or display name.
    GET /api/account/users/search/?q=<query>
    Useful for friend requests, messaging, and forum mentions.
    """
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return api_error("Query 'q' must be at least 2 characters.", status=400)

    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).exclude(id=request.user.id).select_related('profile')[:25]

    data = []
    for u in users:
        try:
            role = u.profile.get_user_role()
            badges = u.profile.get_all_badges()
        except UserProfile.DoesNotExist:
            role = 'user'
            badges = []
        data.append({
            'id': u.id,
            'username': u.username,
            'display_name': u.get_full_name() or u.username,
            'role': role,
            'badges': badges,
        })

    return api_success({'users': data, 'count': len(data)})


@require_http_methods(["POST"])
@api_auth_required
def password_change_view(request):
    """
    Change password via API.
    POST /api/account/password/change/
    Body: {"current_password": "...", "new_password": "..."}
    Requires session authentication only (API key auth not accepted for this endpoint).
    """
    # Require session auth — API key holders must not be able to change passwords
    # without knowing the current one via an interactive session.
    if not request.session.session_key:
        return api_error("Password change requires an active session.", status=403)

    try:
        data = json.loads(request.body)
        current_password = str(data.get('current_password', ''))
        new_password = str(data.get('new_password', ''))
    except (json.JSONDecodeError, ValueError):
        return api_error("Invalid JSON format.", status=400)

    if not current_password or not new_password:
        return api_error("Both 'current_password' and 'new_password' are required.", status=400)

    if not request.user.check_password(current_password):
        return api_error("Current password is incorrect.", status=400)

    if len(new_password) < 8:
        return api_error("New password must be at least 8 characters.", status=400)

    request.user.set_password(new_password)
    request.user.save(update_fields=['password'])

    return api_success({}, message="Password changed successfully. Please log in again.")
