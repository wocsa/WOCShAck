"""
Account module views.
Handles user authentication, registration, 2FA, profile management,
login history, backup codes, and session management.
"""
# --- Imports ---
import re
import secrets
import logging
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
import os
import urllib.parse
import urllib.request
import hashlib
import json

logger = logging.getLogger(__name__)
from django.conf import settings as django_settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import logout, update_session_auth_hash, authenticate, login as django_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.paginator import Paginator
from .Utils.totp import generate_qr, verify_code
from .Utils.Register import (
    ALLOWED_EMAIL_DOMAIN,
    EMAIL_INVALID_DOMAIN,
    EMAIL_INVALID_FORMAT,
    check_password_strength,
    get_email_validation_result,
)
from Bank.Utils import external_calls
from Bank.models import Transaction as BankTransaction
from .models import UserProfile, LoginHistory, BackupCode, UserSession, PasswordResetToken, PasswordResetRateLimit, PurchasedFeature, ProfileTheme

# --- Utility Functions ---
def _build_email_link(request, path):
    """Build an absolute link for emails using settings.SITE_URL when set.

    Falls back to ``request.build_absolute_uri`` so dev environments without
    SITE_URL keep working, but production deployments behind reverse proxies
    or accessed from internal hostnames get the canonical public URL.
    """
    if django_settings.SITE_URL:
        return f"{django_settings.SITE_URL}{path}"
    return request.build_absolute_uri(path)


def build_send_email_url(destination, subject, content, source='Very Real Company', timeout=5):
    query_data = {
        'source': source,
        'destination': destination,
        'subject': subject,
        'content': content
    }
    url = f'http://{django_settings.WEBMAIL_HOST}/send?' + urllib.parse.urlencode(query_data)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'wocshack-email-sender/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read().decode('utf-8', errors='replace')
            return {'url': url, 'status': status, 'body': body}
    except Exception as e:
        return {'url': url, 'error': str(e)}


def _webmail_user_exists(email):
    """Return True if the email address has an account in the Webmail system."""
    try:
        req = urllib.request.Request(
            f'http://{django_settings.WEBMAIL_HOST}/api/users',
            headers={'User-Agent': 'wocshack-email-sender/1.0'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            users = {u['username'] for u in data.get('users', [])}
            local = email.split('@')[0]
            full = f"{local}@tbox.traced"
            return full in users
    except Exception:
        return False

# --- Views ---


def _get_client_ip(request):
    """
    Extract client IP from request, handling proxy headers.
    """
    ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
    if ip_address:
        ip_address = ip_address.split(',')[0].strip()
    else:
        ip_address = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip_address


# --- Password Reset Request View ---
def password_reset_request(request):
    """
    Password reset request with database-backed tokens and rate limiting.
    Rate limited to prevent abuse (5 per IP, 3 per email within 30 minutes).
    """
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        ip_address = _get_client_ip(request)

        if PasswordResetRateLimit.is_rate_limited(ip_address, email):
            return render(request, "registration/password_reset_request.html", {
                "error": "Too many reset requests. Please try again later."
            })

        # Log the request for rate limiting regardless of whether user exists
        PasswordResetRateLimit.log_request(ip_address, email)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return render(request, "registration/password_reset_request.html", {
                "message": "If an account with that email exists, a reset link has been sent."
            })

        token_obj = PasswordResetToken.create_token(user, request)

        # Build reset link from the public site URL when configured, else
        # fall back to the request host.
        reset_link = _build_email_link(request, f"/account/password_reset/?token={token_obj.token}")

        # Send email
        build_send_email_url(
            destination=user.email,
            subject="Password Reset Request",
            content=f"Click the link to reset your password: <a href='{reset_link}' target='_blank'>{reset_link}</a><br><br>This link expires in 1 hour. If you didn't request this, please ignore this email."
        )
        return render(request, "registration/password_reset_request.html", {
            "message": "If an account with that email exists, a reset link has been sent."
        })
    return render(request, "registration/password_reset_request.html")


# --- Password Reset Form View ---
def password_reset_form(request):
    """
    Password reset form using database-backed tokens.
    Tokens are single-use and expire after 1 hour.
    """
    token_value = request.GET.get("token") if request.method == "GET" else request.POST.get("token")

    if not token_value:
        return render(request, "registration/password_reset.html", {"error": "Invalid or expired token."})

    token_obj = PasswordResetToken.get_valid_token(token_value)
    if not token_obj:
        return render(request, "registration/password_reset.html", {"error": "Invalid or expired token."})

    user = token_obj.user

    if request.method == "POST":
        pw1 = request.POST.get("password1")
        pw2 = request.POST.get("password2")
        if pw1 != pw2:
            return render(request, "registration/password_reset.html", {
                "error": "Passwords do not match.", "token": token_value
            })
        if check_password_strength(pw1) is not True:
            return render(request, "registration/password_reset.html", {
                "error": "Password not strong enough.", "token": token_value
            })
        user.set_password(pw1)
        user.save()

        token_obj.consume()

        # Send notification email
        build_send_email_url(
            destination=user.email,
            subject="Your password was reset",
            content="Your password has been changed. If you did not do this, contact support immediately."
        )
        return redirect("login")
    return render(request, "registration/password_reset.html", {"token": token_value})

def register(request):
    REGISTER_TEMPLATE = "registration/register.html"
    ctx = {"allowed_email_domain": ALLOWED_EMAIL_DOMAIN}
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        password = request.POST.get("password")
        password_confirmation = request.POST.get("password_confirmation")

        if password_confirmation != password:
            return render(request, REGISTER_TEMPLATE, {**ctx, "error": "Passwords do not match."})

        email_validation_result = get_email_validation_result(email)
        if email_validation_result == EMAIL_INVALID_FORMAT:
            return render(
                request,
                REGISTER_TEMPLATE,
                {**ctx, "error": "Invalid email format"},
            )

        if email_validation_result == EMAIL_INVALID_DOMAIN:
            return render(
                request,
                REGISTER_TEMPLATE,
                {**ctx, "error": f"Only @{ALLOWED_EMAIL_DOMAIN} email addresses are allowed."},
            )

        if not _webmail_user_exists(email):
            return render(request, REGISTER_TEMPLATE, {**ctx, "error": "This email address does not exist in our mail system."})

        if check_password_strength(password) is not True:
            return render(request, REGISTER_TEMPLATE, {**ctx, "error": "Password is not strong enough."})

        if User.objects.filter(username=username).exists():
            return render(request, REGISTER_TEMPLATE, {**ctx, "error": "Username is already taken."})

        if User.objects.filter(email=email).exists():
            return render(request, REGISTER_TEMPLATE, {**ctx, "error": "Email is already registered."})

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.totp_key = None
        profile.cart = json.dumps([])
        profile.is_activated = False
        profile.save()

        # Build activation link from the public site URL when configured.
        token = hashlib.md5(email.encode('utf-8')).hexdigest()
        activation_link = _build_email_link(request, f"/account/activate/?username={username}&token={token}")
        # Send email
        send_result = build_send_email_url(
            destination=user.email,
            subject="Activate your account",
            content=f"Click the link to activate your account: <a href='{activation_link}' target='_blank'>{activation_link}</a>"
        )

        return render(request, "registration/activation_sent.html", {"activation_link": activation_link, "send_email_result": send_result})
    return render(request, REGISTER_TEMPLATE, ctx)

def activate_account(request):
    """
    Activate account via email link.
    CSRF exempt decorator removed - this endpoint only handles GET requests
    which are not subject to CSRF protection by Django default.
    """
    username = request.GET.get('username')
    token = request.GET.get('token')

    if not username or not token:
        return render(request, "registration/activation_failed.html", {"reason": "Invalid activation link."})

    try:
        user = User.objects.get(username=username)
        profile = user.profile
        expected_hash = hashlib.md5(user.email.encode('utf-8')).hexdigest()
        if secrets.compare_digest(token, expected_hash):
            profile.is_activated = True
            profile.save()
            return render(request, "registration/activation_success.html", {"username": username})
        else:
            return render(request, "registration/activation_failed.html", {"reason": "Invalid activation link."})
    except User.DoesNotExist:
        return render(request, "registration/activation_failed.html", {"reason": "User does not exist."})
    except Exception:
        return render(request, "registration/activation_failed.html", {"reason": "Activation failed. Please try again."})


@login_required()
def account(request):
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")
    return render(request, "account.html")


@login_required()
def process(request):
    """
    Process authentication flow.
    Handles TOTP 2FA, email 2FA, or initial 2FA setup.
    """
    try:
        profile = request.user.profile  # Access the OneToOne related profile

        # Check if user has TOTP 2FA enabled
        if profile.totp_key:
            request.session['2FA'] = 0
            return redirect("/account/verification")

        # Check if user has email 2FA enabled
        if getattr(profile, 'email_2fa_enabled', False):
            request.session['2FA'] = 0
            return redirect("/account/2fa/email/verify/")

        # No 2FA enabled - offer setup during registration flow
        request.session['2FA'] = 0
        return redirect("/account/ask-2fa")
    except Exception as e:
        logout(request)
        return HttpResponse("Something went wrong!", status=500)


@login_required()
def ask_2fa(request):
    if request.method == "POST":
        profile = request.user.profile
        if verify_code(request.POST.get("code"), request.session.get('totp_key')) is True:
            request.session['2FA'] = 1
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            profile.totp_key = request.session.get('totp_key')
            profile.save()
            return redirect("/account/process/bank/")
        else:
            return render(request, "2fa/2fa_errors/bad_code_error_ask_2fa.html", {"img_str": request.session.get('qr')})
    else:
        uri, qr, key = generate_qr(request.user.username)
        request.session['qr'] = qr
        request.session['totp_key'] = key
        return render(request, "registration/ask_2fa.html", {"img_str": qr})


@login_required()
def ask_2fa_no(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    profile.totp_key = None
    profile.save()
    request.session['2FA'] = 1
    return redirect("/account/process/bank/")


@login_required()
def verification(request):
    """
    Verify 2FA code with backup code support.
    Accepts both TOTP codes and backup codes for authentication.
    """
    if request.method == "POST":
        profile = request.user.profile
        code = request.POST.get("code", "").strip()

        # Try TOTP verification first
        if verify_code(code, profile.totp_key) is True:
            request.session['2FA'] = 1
            # Update login history to success after 2FA
            LoginHistory.log_attempt(request.user, request, LoginHistory.LOGIN_SUCCESS)
            # Update session record
            UserSession.create_or_update_session(request.user, request)
            return redirect("/account/process/bank/")

        # Try backup code verification
        if BackupCode.verify_code(request.user, code):
            request.session['2FA'] = 1
            # Log successful 2FA with backup code
            LoginHistory.log_attempt(request.user, request, LoginHistory.LOGIN_SUCCESS)
            UserSession.create_or_update_session(request.user, request)
            messages.info(request, f"Backup code used. You have {BackupCode.get_remaining_count(request.user)} codes remaining.")
            return redirect("/account/process/bank/")

        # Both failed
        return render(request, "2fa/2fa_errors/bad_code_error.html", {"img_str": request.session.get('qr')})

    # Show backup code count if available
    backup_count = BackupCode.get_remaining_count(request.user)
    return render(request, "2fa/2fa.html", {"backup_count": backup_count})


@login_required()
def process_bank(request):
    """
    Process bank account setup for the user.
    Redirects to account page if bank account exists, otherwise to PIN setup.
    """
    user_id = request.user.id
    if external_calls.is_user_existing(user_id) is True:
        return redirect("/account")
    else:
        return redirect("/account/ask-pin/")


@login_required()
def ask_pin(request):
    """
    Handle PIN setup for the user's bank account.
    Validates PIN confirmation and creates the bank account.
    """
    if request.method == "POST":
        if request.POST.get("pin") == request.POST.get("confirm_pin"):
            user_id = request.user.id
            external_calls.add_user(user_id, request.POST.get("pin"))
            return redirect("/account/")
        else:
            return render(request, "bank/pin_errors/not_matching_pins.html")
    return render(request, "registration/ask_pin.html")


@login_required()
def settings(request):
    if request.method == "POST":
        # Handle account deletion
        if request.POST.get('action') == 'delete_account':
            password = request.POST.get('password_for_delete')
            if not request.user.check_password(password):
                messages.error(request, "Incorrect password. Account not deleted.")
                return redirect('settings')
            # Call external delete_user
            external_calls.delete_user(request.user.id)
            # Delete Django user
            request.user.delete()
            return redirect('login')

        if 'old_password' in request.POST:
            old = request.POST['old_password']
            new = request.POST['new_password']
            confirm = request.POST['confirm_password']

            user_id = request.POST.get('user_id', request.user.id)
            try:
                target_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                target_user = request.user

            if new != confirm:
                messages.error(request, "New passwords do not match.")
            elif not request.user.check_password(old):
                messages.error(request, "Old password is incorrect.")
            else:
                target_user.set_password(new)
                target_user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Password updated successfully.")

        elif 'new_username' in request.POST:
            new_username = request.POST['new_username']
            if User.objects.filter(username=new_username).exclude(pk=request.user.pk).exists():
                messages.error(request, "Username already taken.")
            else:
                profile = request.user.profile
                for key, value in request.POST.items():
                    if hasattr(profile, key) and key != 'csrfmiddlewaretoken':
                        try:
                            setattr(profile, key, value)
                        except Exception:
                            pass
                profile.save()
                request.user.username = new_username
                request.user.save()
                messages.success(request, "Username updated successfully.")

        elif 'new_email' in request.POST:
            new_email = request.POST['new_email']
            confirm_email = request.POST['confirm_email']
            password = request.POST['password_for_email']
            email_validation_result = get_email_validation_result(new_email)

            if not request.user.check_password(password):
                messages.error(request, "Incorrect password.")
            elif new_email != confirm_email:
                messages.error(request, "Emails do not match.")
            elif email_validation_result == EMAIL_INVALID_FORMAT:
                messages.error(request, "Invalid email format")
            elif email_validation_result == EMAIL_INVALID_DOMAIN:
                messages.error(request, f"Only @{ALLOWED_EMAIL_DOMAIN} email addresses are allowed.")
            elif User.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
                messages.error(request, "Email already taken.")
            else:
                user = request.user
                user.email = new_email
                user.save()

                profile = user.profile
                profile.is_activated = False
                profile.save()

                # Build activation link from the public site URL when configured.
                token = hashlib.md5(new_email.encode('utf-8')).hexdigest()
                activation_link = _build_email_link(request, f"/account/activate/?username={user.username}&token={token}")

                # Send email
                build_send_email_url(
                    destination=user.email,
                    subject="Activate your new email address",
                    content=f"Click the link to activate your account with your new email: <a href='{activation_link}' target='_blank'>{activation_link}</a>"
                )

                logout(request)

                return render(request, "registration/email_changed.html")

        elif 'first_name' in request.POST:
            first_name = request.POST['first_name']
            last_name = request.POST['last_name']

            user = request.user
            user.first_name = first_name
            user.last_name = last_name
            user.save()
            messages.success(request, "Profile updated successfully.")

        elif 'biography' in request.POST:
            biography = request.POST['biography']
            profile = request.user.profile
            profile.biography = biography
            profile.save()
            messages.success(request, "Biography updated successfully.")
        elif 'picture' in request.FILES:
            picture = request.FILES['picture']
            profile = request.user.profile
            
            # Define the path to save the uploaded picture
            upload_path = os.path.join('Account', 'static', 'uploads')
            if not os.path.exists(upload_path):
                os.makedirs(upload_path)
            
            # Save the picture with a unique name
            picture_name = f"{request.user.username}_{picture.name}"
            picture_path = os.path.join(upload_path, picture_name)
            
            with open(picture_path, 'wb+') as destination:
                for chunk in picture.chunks():
                    destination.write(chunk)
            
            # Update the user's profile with the new picture path
            profile.picture_path = picture_name
            profile.save()
            messages.success(request, "Profile picture updated successfully.")

        return redirect('settings')  # reload the settings page

    # Fetch purchased CSS for display
    from Api.models import Purchase
    purchased_css = Purchase.objects.filter(
        user=request.user
    ).select_related('css_file').order_by('-purchased_at')

    return render(request, "settings.html", {
        "purchased_css": purchased_css,
    })


@login_required()
def purchased_articles(request):
    """
    Display purchased articles for the logged-in user.
    """
    # Fetch purchased articles for the user
    from Api.models import Purchase
    purchased_articles = Purchase.objects.filter(
        user=request.user
    ).select_related('css_file').order_by('-purchased_at')

    return render(request, "purchased_articles.html", {
        "purchased_articles": purchased_articles,
    })


def login_view(request):
    """
    Handle user login with login history tracking.
    Logs all login attempts (success, failure, 2FA required) for security monitoring.
    """
    LOGIN_TEMPLATE = 'registration/login.html'
    if request.method == 'POST':
        login_input = request.POST.get('username')
        password = request.POST.get('password')
        try:
            # Try email first, then fall back to username
            try:
                user_obj = User.objects.get(email=login_input)
            except User.DoesNotExist:
                user_obj = User.objects.get(username=login_input)
            user = authenticate(request, username=user_obj.username, password=password)
            if user is not None:
                if user.profile.is_activated:
                    if user.profile.totp_key:
                        # User has 2FA enabled, log as 2FA required
                        LoginHistory.log_attempt(user, request, LoginHistory.LOGIN_2FA_REQUIRED)
                    else:
                        LoginHistory.log_attempt(user, request, LoginHistory.LOGIN_SUCCESS)

                    django_login(request, user)

                    UserSession.create_or_update_session(user, request)

                    return redirect('/account/process/')
                else:
                    # Log failed attempt due to unactivated account
                    LoginHistory.log_attempt(user_obj, request, LoginHistory.LOGIN_FAILED)
                    return render(request, LOGIN_TEMPLATE, {'error': 'Account not activated'})
            else:
                LoginHistory.log_attempt(user_obj, request, LoginHistory.LOGIN_FAILED)
                return render(request, LOGIN_TEMPLATE, {'error': 'Invalid credentials'})
        except User.DoesNotExist:
            # Don't reveal that the user doesn't exist for security
            return render(request, LOGIN_TEMPLATE, {'error': 'Invalid credentials'})
    return render(request, LOGIN_TEMPLATE)

def public_profile(request, username=None):
    """
    Display public profile with seller statistics.
    Supports both URL path parameter and query parameter for backwards compatibility.
    """
    # Support both URL path parameter and query parameter for backwards compatibility
    if username is None:
        username = request.GET.get('username')

    if not username:
        return HttpResponse("Please specify a username.", status=400)

    profile_user = get_object_or_404(User, username=username)

    # Import here to avoid circular imports
    from Api.models import Css
    from Shopping.models import Review
    from django.db.models import Avg, Count

    # Get seller statistics - CSS files created by this user
    css_files = Css.objects.filter(creator=profile_user)
    css_count = css_files.count()

    # Get review statistics for seller's products
    review_stats = Review.objects.filter(
        css_file__creator=profile_user,
        is_approved=True
    ).aggregate(
        avg_rating=Avg('rating'),
        total_reviews=Count('id')
    )

    # Get recent CSS files by this seller (limit to 6)
    recent_css = css_files.order_by('-created_at')[:6]

    # Get custom profile theme if user has one
    profile_theme = None
    has_custom_theme = PurchasedFeature.has_feature(profile_user, PurchasedFeature.FEATURE_CUSTOM_THEME)
    if has_custom_theme:
        try:
            profile_theme = ProfileTheme.objects.get(user=profile_user)
        except ProfileTheme.DoesNotExist:
            pass

    developer_profile = None
    is_developer = PurchasedFeature.has_feature(profile_user, PurchasedFeature.FEATURE_DEVELOPER_ROLE)
    if is_developer:
        from Developer.models import DeveloperProfile
        try:
            developer_profile = DeveloperProfile.objects.get(user=profile_user)
        except DeveloperProfile.DoesNotExist:
            pass

    context = {
        "profile_user": profile_user,
        "is_seller": css_count > 0,
        "css_count": css_count,
        "seller_avg_rating": review_stats['avg_rating'] or 0,
        "seller_total_reviews": review_stats['total_reviews'] or 0,
        "recent_css": recent_css,
        "profile_theme": profile_theme,
        "has_custom_theme": has_custom_theme,
        "is_developer": is_developer,
        "developer_profile": developer_profile,
    }

    return render(request, "public_profile.html", context)


# --- Login History View ---
@login_required()
def login_history(request):
    """
    Display login history/activity log for the user.
    Shows recent login attempts with IP, device, and status information.
    """
    # Check 2FA if enabled
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    # Get login history with pagination
    history_list = LoginHistory.objects.filter(user=request.user).order_by('-timestamp')
    paginator = Paginator(history_list, 20)  # 20 items per page

    page_number = request.GET.get('page', 1)
    history = paginator.get_page(page_number)

    # Get statistics
    total_logins = history_list.count()
    successful_logins = history_list.filter(status=LoginHistory.LOGIN_SUCCESS).count()
    failed_logins = history_list.filter(status=LoginHistory.LOGIN_FAILED).count()

    context = {
        'history': history,
        'total_logins': total_logins,
        'successful_logins': successful_logins,
        'failed_logins': failed_logins,
    }
    return render(request, "login_history.html", context)


# --- Backup Codes Views ---
@login_required()
def backup_codes(request):
    """
    Display backup codes management page.
    Shows remaining codes count and allows generating new codes.
    """
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    # Only show backup codes if 2FA is enabled
    if not request.user.profile.totp_key:
        messages.info(request, "You need to enable 2FA before generating backup codes.")
        return redirect('settings')

    remaining_codes = BackupCode.get_remaining_count(request.user)

    context = {
        'remaining_codes': remaining_codes,
        'has_codes': remaining_codes > 0,
    }
    return render(request, "backup_codes.html", context)


@login_required()
@require_POST
def generate_backup_codes(request):
    """
    Generate new backup codes for the user.
    Requires password confirmation for security.
    """
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    # Only allow if 2FA is enabled
    if not request.user.profile.totp_key:
        messages.error(request, "You need to enable 2FA before generating backup codes.")
        return redirect('settings')

    # Require password confirmation
    password = request.POST.get('password')
    if not request.user.check_password(password):
        messages.error(request, "Incorrect password. Backup codes not generated.")
        return redirect('backup_codes')

    # Generate new codes
    codes = BackupCode.generate_codes_for_user(request.user)

    # Store codes in session temporarily for display (they won't be shown again)
    request.session['new_backup_codes'] = codes

    messages.success(request, "New backup codes have been generated. Save them securely!")
    return redirect('backup_codes_display')


@login_required()
def backup_codes_display(request):
    """
    Display newly generated backup codes once.
    Codes are only shown once and should be saved by the user.
    """
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    codes = request.session.pop('new_backup_codes', None)
    if not codes:
        return redirect('backup_codes')

    context = {
        'codes': codes,
    }
    return render(request, "backup_codes_display.html", context)


# --- Session Management Views ---
@login_required()
def sessions(request):
    """
    Display active sessions for session management.
    Allows users to view and revoke their active sessions.
    """
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    # Get current session key
    current_session_key = request.session.session_key

    # Get all active sessions for this user
    active_sessions = UserSession.objects.filter(
        user=request.user,
        is_active=True
    ).order_by('-last_activity')

    # Mark the current session
    for session in active_sessions:
        session.is_current_session = (session.session_key == current_session_key)

    context = {
        'sessions': active_sessions,
        'current_session_key': current_session_key,
    }
    return render(request, "sessions.html", context)


@login_required()
@require_POST
def revoke_session(request, session_id):
    """
    Revoke a specific session.
    Users cannot revoke their current session from this view.
    """
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return JsonResponse({'error': 'Authentication required'}, status=403)

    session = get_object_or_404(UserSession, id=session_id, user=request.user, is_active=True)

    # Prevent revoking current session
    if session.session_key == request.session.session_key:
        messages.error(request, "You cannot revoke your current session. Use logout instead.")
        return redirect('sessions')

    session.revoke()
    messages.success(request, "Session revoked successfully.")

    return redirect('sessions')


@login_required()
@require_POST
def revoke_all_sessions(request):
    """
    Revoke all sessions except the current one.
    Requires password confirmation for security.
    """
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    password = request.POST.get('password')
    if not request.user.check_password(password):
        messages.error(request, "Incorrect password. Sessions not revoked.")
        return redirect('sessions')

    current_session_key = request.session.session_key

    # Revoke all other sessions
    other_sessions = UserSession.objects.filter(
        user=request.user,
        is_active=True
    ).exclude(session_key=current_session_key)

    revoked_count = 0
    for session in other_sessions:
        session.revoke()
        revoked_count += 1

    if revoked_count > 0:
        messages.success(request, f"Successfully revoked {revoked_count} other session(s).")
    else:
        messages.info(request, "No other sessions to revoke.")

    return redirect('sessions')


# --- Profile Completion Helper ---
def get_profile_completion_context(user):
    """
    Helper to get profile completion data for templates.
    """
    try:
        profile = user.profile
        return profile.get_profile_completion()
    except UserProfile.DoesNotExist:
        return {
            'percentage': 0,
            'completed': 0,
            'total': 7,
            'missing': ['all fields']
        }


# --- 2FA Management Views ---
@login_required()
def setup_2fa(request):
    """
    Setup 2FA from settings page.
    Shows QR code and manual entry key for authenticator app setup.
    """
    # Check if user is authenticated with existing 2FA
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    # If user already has 2FA enabled, redirect to manage page
    if request.user.profile.totp_key:
        messages.info(request, "2FA is already enabled. You can manage it from the settings page.")
        return redirect('manage_2fa')

    if request.method == "POST":
        profile = request.user.profile
        code = request.POST.get("code", "").strip()
        totp_key = request.session.get('setup_totp_key')

        if not totp_key:
            messages.error(request, "Session expired. Please try again.")
            return redirect('setup_2fa')

        if verify_code(code, totp_key) is True:
            profile.totp_key = totp_key
            profile.save()

            # Clear temporary session data
            request.session.pop('setup_totp_key', None)
            request.session.pop('setup_qr', None)
            request.session['2FA'] = 1

            # Log the security event
            LoginHistory.log_attempt(request.user, request, LoginHistory.LOGIN_SUCCESS)

            messages.success(request, "Two-factor authentication has been enabled successfully!")
            return redirect('settings')
        else:
            messages.error(request, "Invalid verification code. Please try again.")
            # Keep the QR code displayed
            return render(request, "2fa/setup_2fa.html", {
                "img_str": request.session.get('setup_qr'),
                "manual_key": totp_key
            })
    else:
        # Generate new QR code and key
        uri, qr, key = generate_qr(request.user.username)
        request.session['setup_qr'] = qr
        request.session['setup_totp_key'] = key

        return render(request, "2fa/setup_2fa.html", {
            "img_str": qr,
            "manual_key": key
        })


@login_required()
def manage_2fa(request):
    """
    Manage existing 2FA settings.
    Shows current 2FA status and options to disable or generate backup codes.
    """
    # Check if user is authenticated with existing 2FA
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    profile = request.user.profile

    # Check if 2FA is enabled
    has_totp = bool(profile.totp_key)
    has_email_2fa = getattr(profile, 'email_2fa_enabled', False)
    backup_count = BackupCode.get_remaining_count(request.user) if has_totp else 0

    context = {
        'has_totp': has_totp,
        'has_email_2fa': has_email_2fa,
        'backup_count': backup_count,
    }
    return render(request, "2fa/manage_2fa.html", context)


@login_required()
@require_POST
def disable_2fa(request):
    """
    Disable 2FA with password confirmation.
    Requires current password to prevent unauthorized 2FA removal.
    """
    # Check if user is authenticated with existing 2FA
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    password = request.POST.get('password')

    if not request.user.check_password(password):
        messages.error(request, "Incorrect password. 2FA has not been disabled.")
        return redirect('manage_2fa')

    profile = request.user.profile

    if not profile.totp_key:
        messages.info(request, "2FA is not currently enabled.")
        return redirect('settings')

    profile.totp_key = None
    profile.save()

    # Delete all backup codes
    BackupCode.objects.filter(user=request.user).delete()

    # Reset 2FA session flag (still authenticated but no 2FA required)
    request.session['2FA'] = 1

    messages.success(request, "Two-factor authentication has been disabled.")
    return redirect('settings')


# --- Email 2FA Views ---
@login_required()
def setup_email_2fa(request):
    """
    Setup email-based 2FA as an alternative method.
    Sends a verification code to the user's email address.
    """
    # Check if user is authenticated with existing 2FA
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    profile = request.user.profile

    # Check if user has a verified email
    if not profile.is_activated:
        messages.error(request, "Please verify your email address before setting up email-based 2FA.")
        return redirect('settings')

    if request.method == "POST":
        action = request.POST.get('action')

        if action == 'send_code':
            code = secrets.token_hex(3).upper()[:6]  # 6 character code
            code_hash = hashlib.sha256(code.encode('utf-8')).hexdigest()

            # Store hashed code with expiry (10 minutes)
            request.session['email_2fa_code_hash'] = code_hash
            request.session['email_2fa_code_expiry'] = (timezone.now() + timedelta(minutes=10)).isoformat()

            # Send email with code
            send_result = build_send_email_url(
                destination=request.user.email,
                subject="Your 2FA Setup Verification Code",
                content=f"Your verification code is: <strong>{code}</strong><br><br>This code expires in 10 minutes. If you didn't request this, please ignore this email."
            )

            messages.success(request, "A verification code has been sent to your email address.")
            return render(request, "2fa/setup_email_2fa.html", {
                "code_sent": True,
                "email": request.user.email
            })

        elif action == 'verify_code':
            code = request.POST.get('code', '').strip().upper()
            stored_hash = request.session.get('email_2fa_code_hash')
            expiry_str = request.session.get('email_2fa_code_expiry')

            if not stored_hash or not expiry_str:
                messages.error(request, "No verification code was sent. Please request a new code.")
                return redirect('setup_email_2fa')

            # Check expiry
            try:
                expiry = timezone.datetime.fromisoformat(expiry_str)
                if timezone.now() > expiry:
                    # Clear expired code
                    request.session.pop('email_2fa_code_hash', None)
                    request.session.pop('email_2fa_code_expiry', None)
                    messages.error(request, "Verification code has expired. Please request a new code.")
                    return redirect('setup_email_2fa')
            except (ValueError, TypeError):
                messages.error(request, "Session error. Please try again.")
                return redirect('setup_email_2fa')

            code_hash = hashlib.sha256(code.encode('utf-8')).hexdigest()
            if secrets.compare_digest(code_hash, stored_hash):
                # Enable email 2FA
                profile.email_2fa_enabled = True
                profile.save()

                # Clear session data
                request.session.pop('email_2fa_code_hash', None)
                request.session.pop('email_2fa_code_expiry', None)

                messages.success(request, "Email-based two-factor authentication has been enabled!")
                return redirect('settings')
            else:
                messages.error(request, "Invalid verification code. Please try again.")
                return render(request, "2fa/setup_email_2fa.html", {
                    "code_sent": True,
                    "email": request.user.email
                })

    return render(request, "2fa/setup_email_2fa.html", {
        "code_sent": False,
        "email": request.user.email
    })


@login_required()
@require_POST
def disable_email_2fa(request):
    """
    Disable email-based 2FA with password confirmation.
    """
    # Check if user is authenticated with existing 2FA
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    password = request.POST.get('password')

    if not request.user.check_password(password):
        messages.error(request, "Incorrect password. Email 2FA has not been disabled.")
        return redirect('manage_2fa')

    profile = request.user.profile

    if not getattr(profile, 'email_2fa_enabled', False):
        messages.info(request, "Email 2FA is not currently enabled.")
        return redirect('settings')

    # Disable email 2FA
    profile.email_2fa_enabled = False
    profile.save()

    messages.success(request, "Email-based two-factor authentication has been disabled.")
    return redirect('settings')


@login_required()
@require_POST
def logout_view(request):
    """
    Handle user logout with session cleanup.
    Marks the current UserSession as inactive before logging out.
    Requires POST to prevent CSRF logout attacks.
    """
    session_key = request.session.session_key
    if session_key:
        try:
            user_session = UserSession.objects.get(
                session_key=session_key,
                user=request.user,
                is_active=True
            )
            user_session.is_active = False
            user_session.save()
        except UserSession.DoesNotExist:
            pass

    logout(request)
    return redirect('login')


def email_2fa_verification(request):
    """
    Verify email 2FA code during login.
    This is called when a user with email 2FA enabled tries to log in.
    """
    if not request.user.is_authenticated:
        return redirect('login')

    profile = request.user.profile

    if not getattr(profile, 'email_2fa_enabled', False):
        return redirect('/account/process')

    if request.method == "POST":
        action = request.POST.get('action')

        if action == 'send_code':
            code = secrets.token_hex(3).upper()[:6]
            code_hash = hashlib.sha256(code.encode('utf-8')).hexdigest()

            # Store hashed code with expiry (10 minutes)
            request.session['login_email_2fa_code_hash'] = code_hash
            request.session['login_email_2fa_code_expiry'] = (timezone.now() + timedelta(minutes=10)).isoformat()

            # Send email with code
            build_send_email_url(
                destination=request.user.email,
                subject="Your Login Verification Code",
                content=f"Your login verification code is: <strong>{code}</strong><br><br>This code expires in 10 minutes. If you didn't try to log in, please secure your account immediately."
            )

            messages.success(request, "A verification code has been sent to your email address.")
            return render(request, "2fa/email_2fa_verify.html", {
                "code_sent": True,
                "email": request.user.email
            })

        elif action == 'verify_code':
            code = request.POST.get('code', '').strip().upper()
            stored_hash = request.session.get('login_email_2fa_code_hash')
            expiry_str = request.session.get('login_email_2fa_code_expiry')

            if not stored_hash or not expiry_str:
                messages.error(request, "No verification code was sent. Please request a new code.")
                return render(request, "2fa/email_2fa_verify.html", {
                    "code_sent": False,
                    "email": request.user.email
                })

            # Check expiry
            try:
                expiry = timezone.datetime.fromisoformat(expiry_str)
                if timezone.now() > expiry:
                    request.session.pop('login_email_2fa_code_hash', None)
                    request.session.pop('login_email_2fa_code_expiry', None)
                    messages.error(request, "Verification code has expired. Please request a new code.")
                    return render(request, "2fa/email_2fa_verify.html", {
                        "code_sent": False,
                        "email": request.user.email
                    })
            except (ValueError, TypeError):
                messages.error(request, "Session error. Please try again.")
                return redirect('login')

            code_hash = hashlib.sha256(code.encode('utf-8')).hexdigest()
            if secrets.compare_digest(code_hash, stored_hash):
                # Clear session data
                request.session.pop('login_email_2fa_code_hash', None)
                request.session.pop('login_email_2fa_code_expiry', None)

                # Mark 2FA as completed
                request.session['2FA'] = 1

                # Log successful login
                LoginHistory.log_attempt(request.user, request, LoginHistory.LOGIN_SUCCESS)
                UserSession.create_or_update_session(request.user, request)

                return redirect('/account/process/bank/')
            else:
                messages.error(request, "Invalid verification code. Please try again.")
                return render(request, "2fa/email_2fa_verify.html", {
                    "code_sent": True,
                    "email": request.user.email
                })

    # Initial page load - prompt to send code
    return render(request, "2fa/email_2fa_verify.html", {
        "code_sent": False,
        "email": request.user.email
    })


# --- Premium Store Views ---

STORE_ADMIN_USER_ID = 1

STORE_FEATURES = {
    PurchasedFeature.FEATURE_VERIFIED_BADGE: {
        'name': 'Verified Badge',
        'description': 'Display a blue verified badge on your profile, showing other users you are a trusted member of the community.',
        'price': PurchasedFeature.FEATURE_PRICES[PurchasedFeature.FEATURE_VERIFIED_BADGE],
        'icon': 'check-badge',
        'color': '#3b82f6',
    },
    PurchasedFeature.FEATURE_DEVELOPER_ROLE: {
        'name': 'Developer Role',
        'description': 'Upgrade your profile role to Developer. This replaces your default User badge with a purple Developer badge.',
        'price': PurchasedFeature.FEATURE_PRICES[PurchasedFeature.FEATURE_DEVELOPER_ROLE],
        'icon': 'code-bracket',
        'color': '#8b5cf6',
    },
    PurchasedFeature.FEATURE_CUSTOM_THEME: {
        'name': 'Custom Profile Theme',
        'description': 'Customize your public profile with your own color scheme. Choose primary, secondary, and background colors.',
        'price': PurchasedFeature.FEATURE_PRICES[PurchasedFeature.FEATURE_CUSTOM_THEME],
        'icon': 'paint-brush',
        'color': '#f59e0b',
    },
}


@login_required()
def store(request):
    """
    Display the premium features store.
    Shows available features with prices and purchase status.
    """
    # Check 2FA if enabled
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    # Build feature list with ownership status
    features = []
    for feature_type, info in STORE_FEATURES.items():
        owned = PurchasedFeature.has_feature(request.user, feature_type)
        features.append({
            'type': feature_type,
            'name': info['name'],
            'description': info['description'],
            'price': info['price'],
            'icon': info['icon'],
            'color': info['color'],
            'owned': owned,
        })

    # Get user balance for display
    balance = external_calls.get_user_balance(request.user.id)

    context = {
        'features': features,
        'balance': balance,
    }
    return render(request, "store/store.html", context)


@login_required()
def store_purchase(request, feature_type):
    """
    Purchase a premium feature.
    Updated to match Shopping module payment approach with enhanced security and order tracking.
    Requires dual authentication: bank PIN and account password.
    Processes payment via bank transfer to admin account.
    """
    # Check 2FA if enabled
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    if feature_type not in STORE_FEATURES:
        messages.error(request, "Invalid feature type.")
        return redirect('store')

    feature_info = STORE_FEATURES[feature_type]
    price = PurchasedFeature.get_price(feature_type)

    if PurchasedFeature.has_feature(request.user, feature_type):
        messages.info(request, f"You already own {feature_info['name']}.")
        return redirect('store')

    # Check if user has a bank account
    if not external_calls.is_user_existing(request.user.id):
        messages.error(request, "You need a bank account to make purchases. Please set up your banking PIN first.")
        return redirect('store')

    if request.method == 'POST':
        pin = request.POST.get('pin', '').strip()
        password = request.POST.get('password', '').strip()
        card_number = request.POST.get("card_number", "").strip()[:16]
        first_name = request.POST.get("first_name", "").strip()[:100]
        last_name = request.POST.get("last_name", "").strip()[:100]
        email = request.POST.get("email", "").strip()[:254]
        phone = request.POST.get("phone", "").strip()[:20]

        # Helper: build the context dict for re-rendering the form on error
        from Bank.models import BankCard as _BankCard
        _user_cards = _BankCard.objects.filter(user=request.user).exclude(status='cancelled')

        def _form_ctx():
            return {
                'feature': feature_info,
                'feature_type': feature_type,
                'price': price,
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': phone,
                'card_number': card_number,
                'user_cards': _user_cards,
            }

        if not pin or not password or not card_number:
            messages.error(request, "Account password, bank PIN, and card number are all required for secure payment.")
            return render(request, "store/purchase.html", _form_ctx())

        if not first_name or not last_name or not email:
            messages.error(request, "Please fill in all billing information fields.")
            return render(request, "store/purchase.html", _form_ctx())

        if not request.user.check_password(password):
            messages.error(request, "Incorrect account password. Payment authorization failed.")
            return render(request, "store/purchase.html", _form_ctx())

        if not external_calls.verify_user_pin(request.user.id, pin):
            messages.error(request, "Incorrect bank PIN. Payment authorization failed.")
            return render(request, "store/purchase.html", _form_ctx())

        try:
            from Bank.models import BankCard
            card = BankCard.objects.get(
                user=request.user,
                payment_number=card_number,
            )
        except BankCard.DoesNotExist:
            messages.error(request, "Invalid card number. Please enter the 16-digit number shown on your V.R.C card.")
            return render(request, "store/purchase.html", _form_ctx())

        if card.status == 'frozen':
            messages.error(request, "Your card is frozen and cannot be used for payments. Unfreeze your card in the banking dashboard first.")
            return render(request, "store/purchase.html", _form_ctx())

        # Cancelled cards are also ineligible
        if card.status == 'cancelled':
            messages.error(request, "This card has been cancelled and cannot be used for payments.")
            return render(request, "store/purchase.html", _form_ctx())

        balance = external_calls.get_user_balance(request.user.id)
        if balance is None:
            messages.error(request, "Could not verify your balance. Please try again.")
            return render(request, "store/purchase.html", _form_ctx())

        if balance < price:
            messages.error(request, f"Insufficient funds. Your balance is {balance} Neuros, but the feature price is {price} Neuros.")
            return render(request, "store/purchase.html", _form_ctx())

        # Store minimal info for payment processing (NOT the password or PIN)
        request.session['payment_info'] = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'total': float(price),
            'feature_type': feature_type,
            'card_number': card_number,
        }
        # Also store payment_total for the loading page (match Shopping module pattern)
        request.session['payment_total'] = float(price)

        messages.success(request, 'Authentication successful. Processing your payment...')
        return redirect("store_payment_loading")

    # GET request - show purchase confirmation page with enhanced billing info
    balance = external_calls.get_user_balance(request.user.id)
    balance_after = None
    if balance is not None:
        balance_after = balance - price

    # Fetch all non-cancelled cards for the dropdown
    from Bank.models import BankCard
    user_cards = BankCard.objects.filter(user=request.user).exclude(status='cancelled')

    context = {
        'feature': feature_info,
        'feature_type': feature_type,
        'price': price,
        'balance': balance,
        'balance_after_purchase': balance_after,
        'user_cards': user_cards,
    }

    return render(request, "store/purchase.html", context)


@login_required()
def store_payment_loading(request):
    """
    Display payment loading/processing page for account purchases.
    """
    total = request.session.get('payment_total', 0)
    return render(request, "store/payment_loading.html", {"total": total})


@login_required()
@require_POST
def store_complete_order(request):
    """
    Complete the account feature purchase after payment confirmation.
    Integrates with Bank client to deduct payment from user's bank account.
    Uses database transaction for atomicity.
    """
    import sys
    print(f"[PAYMENT DEBUG] store_complete_order called by user: {request.user.username} (id={request.user.id})", file=sys.stderr, flush=True)

    payment_info = request.session.get('payment_info', {})
    print(f"[PAYMENT DEBUG] payment_info from session: {payment_info}", file=sys.stderr, flush=True)

    if not payment_info:
        print(f"[PAYMENT DEBUG] FAILED: No payment info in session", file=sys.stderr, flush=True)
        messages.error(request, 'Payment information not found.')
        return redirect('store')

    feature_type = payment_info.get('feature_type')
    if feature_type not in STORE_FEATURES:
        print(f"[PAYMENT DEBUG] FAILED: Invalid feature type", file=sys.stderr, flush=True)
        messages.error(request, 'Invalid feature type.')
        return redirect('store')

    if PurchasedFeature.has_feature(request.user, feature_type):
        messages.info(request, f"You already own this feature.")
        return redirect('store')

    feature_info = STORE_FEATURES[feature_type]
    price = PurchasedFeature.get_price(feature_type)

    payment_success = False
    payment_error_message = None

    try:
        # Connect to Bank system
        from Bank.Utils.client import make_connection
        import time
        cli, sid = make_connection()
        print(f"[PAYMENT DEBUG] Bank connection result: cli={cli is not False and cli is not None}, sid={sid}", file=sys.stderr, flush=True)

        if cli and sid:
            try:
                # Get user's bank account information
                user_response = cli.get_user(sid, request.user.id)
                time.sleep(0.5)
                print(f"[PAYMENT DEBUG] User response: {user_response}", file=sys.stderr, flush=True)

                if isinstance(user_response, dict) and user_response.get("success"):
                    user_data = user_response.get("user", {})
                    current_balance = Decimal(str(user_data.get("balance", 0)))
                    user_id = user_data.get("id")
                    print(f"[PAYMENT DEBUG] User ID: {user_id}, Balance: {current_balance}, Feature price: {price}", file=sys.stderr, flush=True)

                    if price > current_balance:
                        payment_error_message = f'Insufficient funds. Your balance is {current_balance} Neuros, but the feature price is {price} Neuros.'
                    else:
                        result = cli.transaction(
                            sid=sid,
                            from_user=user_id,
                            to_user=STORE_ADMIN_USER_ID,
                            amount=float(price)
                        )
                        time.sleep(0.5)
                        print(f"[PAYMENT DEBUG] Transaction result: {result}", file=sys.stderr, flush=True)

                        if result and result.get('status') == 'success':
                            payment_success = True
                            print(f"[PAYMENT DEBUG] Payment marked as SUCCESS", file=sys.stderr, flush=True)
                        else:
                            error_msg = result.get('message', 'Transaction failed') if result else 'No response from bank server'
                            payment_error_message = f"Payment failed: {error_msg}"
                            print(f"[PAYMENT DEBUG] Payment FAILED: {payment_error_message}", file=sys.stderr, flush=True)
                else:
                    payment_error_message = 'Could not verify your bank account. Please ensure your bank account is set up.'
                    print(f"[PAYMENT DEBUG] Failed to get user account", file=sys.stderr, flush=True)
            finally:
                cli.close_session(sid)
                cli.close()
        else:
            payment_error_message = 'Bank system connection error. Please try again later.'
            print(f"[PAYMENT DEBUG] Bank connection FAILED", file=sys.stderr, flush=True)
    except Exception as e:
        payment_error_message = f'Payment processing error: {str(e)}'
        print(f"[PAYMENT DEBUG] Exception occurred: {e}", file=sys.stderr, flush=True)

    # Look up which card was used (stored during authentication step)
    _card_number_used = payment_info.get('card_number', '')
    _card_used = None
    if _card_number_used:
        try:
            from Bank.models import BankCard as _BankCard
            _card_used = _BankCard.objects.get(user=request.user, payment_number=_card_number_used)
        except Exception:
            pass

    if not payment_success:
        print(f"[PAYMENT DEBUG] Payment FAILED, creating cancelled order. Error: {payment_error_message}", file=sys.stderr, flush=True)
        # Log the failed payment attempt as a Bank Transaction
        BankTransaction.objects.create(
            user=request.user,
            card=_card_used,
            transaction_type='payment',
            amount=price,
            counterpart_label='Account Store',
            note=f'Feature purchase failed ({feature_type}): {payment_error_message}'[:500],
            status='failed',
        )
        messages.error(request, f'Payment failed: {payment_error_message}')
        messages.info(request, 'Your purchase has been cancelled. Please try again or contact support.')
        print(f"[PAYMENT DEBUG] Redirecting to store after payment failure", file=sys.stderr, flush=True)
        return redirect('store')

    print(f"[PAYMENT DEBUG] Payment SUCCESS, completing feature purchase", file=sys.stderr, flush=True)
    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        # Record the purchase in the database
        try:
            PurchasedFeature.objects.create(
                user=request.user,
                feature_type=feature_type,
                price_paid=price,
            )

            # If custom theme, create the theme record
            if feature_type == PurchasedFeature.FEATURE_CUSTOM_THEME:
                ProfileTheme.objects.get_or_create(user=request.user)

            # Log the successful payment as a Bank Transaction
            BankTransaction.objects.create(
                user=request.user,
                card=_card_used,
                transaction_type='payment',
                amount=price,
                counterpart_label='Account Store',
                note=f'Feature purchase: {feature_info["name"]}',
                status='completed',
            )
            logger.info(
                "Store purchase successful: user=%s feature=%s price=%d",
                request.user.username, feature_type, price
            )
            messages.success(
                request,
                f"Successfully purchased {feature_info['name']} for {price} Neuros!"
            )
        except Exception as e:
            logger.error(
                "CRITICAL: Payment succeeded but DB record failed: user=%s feature=%s price=%d error=%s",
                request.user.username, feature_type, price, str(e)
            )
            messages.error(
                request,
                "Payment was processed but there was an issue recording your purchase. "
                "Please contact support with your transaction details."
            )
            return redirect('store')

    # Clear session data
    if 'payment_info' in request.session:
        del request.session['payment_info']
    if 'payment_total' in request.session:
        del request.session['payment_total']

    return redirect('store')


@login_required()
def customize_theme(request):
    """
    Customize profile theme colors.
    Only accessible to users who have purchased the Custom Profile Theme feature.
    """
    # Check 2FA if enabled
    if request.session.get('2FA') != 1 and request.user.profile.totp_key is not None:
        return redirect("/account/process")

    if not PurchasedFeature.has_feature(request.user, PurchasedFeature.FEATURE_CUSTOM_THEME):
        messages.error(request, "You need to purchase the Custom Profile Theme to access this page.")
        return redirect('store')

    theme, _ = ProfileTheme.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        primary_color = request.POST.get('primary_color', '#667eea').strip()
        secondary_color = request.POST.get('secondary_color', '#764ba2').strip()
        bio_bg_color = request.POST.get('bio_background_color', '#f0f0ff').strip()

        hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')
        colors_valid = True
        for color_name, color_val in [('Primary', primary_color), ('Secondary', secondary_color), ('Background', bio_bg_color)]:
            if not hex_pattern.match(color_val):
                messages.error(request, f"Invalid {color_name} color format. Use #RRGGBB format.")
                colors_valid = False

        if colors_valid:
            theme.primary_color = primary_color
            theme.secondary_color = secondary_color
            theme.bio_background_color = bio_bg_color
            theme.save()
            messages.success(request, "Profile theme updated successfully!")
            return redirect('customize_theme')

    context = {
        'theme': theme,
    }
    return render(request, "store/customize_theme.html", context)
