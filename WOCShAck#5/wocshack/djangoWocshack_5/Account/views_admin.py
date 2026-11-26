"""
Account admin panel views.
Staff-only views for user management, suspension, promotion/demotion,
and email verification oversight.
"""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from .models import UserProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _staff_required(request):
    """Return True (and emit an error message + redirect) if NOT staff."""
    if not request.user.is_staff:
        messages.error(request, "Access denied. Staff privileges required.")
        return redirect("/")
    return None


def _superuser_required(request):
    """Return True (and emit an error message + redirect) if NOT superuser."""
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect("/")
    return None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
@require_GET
def admin_dashboard(request):
    guard = _staff_required(request)
    if guard:
        return guard

    total_users = User.objects.count()
    staff_users = User.objects.filter(is_staff=True).count()
    active_users = User.objects.filter(is_active=True).count()
    unverified_users = UserProfile.objects.filter(is_activated=False).count()
    recent_signups = User.objects.order_by("-date_joined")[:10]

    context = {
        "total_users": total_users,
        "staff_users": staff_users,
        "active_users": active_users,
        "unverified_users": unverified_users,
        "recent_signups": recent_signups,
    }
    return render(request, "account/admin/dashboard.html", context)


# ---------------------------------------------------------------------------
# User list
# ---------------------------------------------------------------------------

@login_required
@require_GET
def user_list(request):
    guard = _staff_required(request)
    if guard:
        return guard

    qs = User.objects.order_by("-date_joined")

    # Filters
    search = request.GET.get("search", "").strip()
    is_staff_filter = request.GET.get("is_staff", "all")
    is_active_filter = request.GET.get("is_active", "all")

    if search:
        qs = qs.filter(username__icontains=search) | qs.filter(email__icontains=search)
        # De-duplicate after OR
        qs = User.objects.filter(
            pk__in=qs.values_list("pk", flat=True)
        ).order_by("-date_joined")

    if is_staff_filter == "yes":
        qs = qs.filter(is_staff=True)
    elif is_staff_filter == "no":
        qs = qs.filter(is_staff=False)

    if is_active_filter == "yes":
        qs = qs.filter(is_active=True)
    elif is_active_filter == "no":
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "search": search,
        "is_staff_filter": is_staff_filter,
        "is_active_filter": is_active_filter,
    }
    return render(request, "account/admin/user_list.html", context)


# ---------------------------------------------------------------------------
# User detail
# ---------------------------------------------------------------------------

@login_required
@require_GET
def user_detail(request, user_id):
    guard = _staff_required(request)
    if guard:
        return guard

    target_user = get_object_or_404(User, pk=user_id)

    try:
        profile = target_user.profile
    except UserProfile.DoesNotExist:
        profile = None

    context = {
        "target_user": target_user,
        "profile": profile,
    }
    return render(request, "account/admin/user_detail.html", context)


# ---------------------------------------------------------------------------
# Suspend / Unsuspend
# ---------------------------------------------------------------------------

@login_required
@require_POST
def user_suspend(request, user_id):
    guard = _staff_required(request)
    if guard:
        return guard

    target_user = get_object_or_404(User, pk=user_id)

    if target_user == request.user:
        messages.error(request, "You cannot suspend your own account.")
        return redirect("account_admin_user_detail", user_id=user_id)

    if target_user.is_superuser:
        messages.error(request, "Superuser accounts cannot be suspended.")
        return redirect("account_admin_user_detail", user_id=user_id)

    target_user.is_active = False
    target_user.save()
    messages.success(request, f"User '{target_user.username}' has been suspended.")
    return redirect("account_admin_user_detail", user_id=user_id)


@login_required
@require_POST
def user_unsuspend(request, user_id):
    guard = _staff_required(request)
    if guard:
        return guard

    target_user = get_object_or_404(User, pk=user_id)
    target_user.is_active = True
    target_user.save()
    messages.success(request, f"User '{target_user.username}' has been unsuspended.")
    return redirect("account_admin_user_detail", user_id=user_id)


# ---------------------------------------------------------------------------
# Promote / Demote  (superuser only)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def user_promote(request, user_id):
    guard = _staff_required(request)
    if guard:
        return guard
    guard = _superuser_required(request)
    if guard:
        return guard

    target_user = get_object_or_404(User, pk=user_id)

    if target_user == request.user:
        messages.error(request, "You cannot change your own staff status.")
        return redirect("account_admin_user_detail", user_id=user_id)

    target_user.is_staff = True
    target_user.save()
    messages.success(request, f"User '{target_user.username}' has been promoted to staff.")
    return redirect("account_admin_user_detail", user_id=user_id)


@login_required
@require_POST
def user_demote(request, user_id):
    guard = _staff_required(request)
    if guard:
        return guard
    guard = _superuser_required(request)
    if guard:
        return guard

    target_user = get_object_or_404(User, pk=user_id)

    if target_user == request.user:
        messages.error(request, "You cannot change your own staff status.")
        return redirect("account_admin_user_detail", user_id=user_id)

    if target_user.is_superuser:
        messages.error(request, "Superuser accounts cannot be demoted via this panel.")
        return redirect("account_admin_user_detail", user_id=user_id)

    target_user.is_staff = False
    target_user.save()
    messages.success(request, f"User '{target_user.username}' has been demoted from staff.")
    return redirect("account_admin_user_detail", user_id=user_id)


# ---------------------------------------------------------------------------
# Verification list
# ---------------------------------------------------------------------------

@login_required
@require_GET
def verification_list(request):
    guard = _staff_required(request)
    if guard:
        return guard

    unverified_profiles = UserProfile.objects.filter(
        is_activated=False
    ).select_related("user").order_by("user__date_joined")

    paginator = Paginator(unverified_profiles, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
    }
    return render(request, "account/admin/verification_list.html", context)
