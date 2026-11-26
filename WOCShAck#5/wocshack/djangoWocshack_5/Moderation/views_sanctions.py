"""
User sanctions views.
Warnings, mutes, bans, appeals, and user moderation overview.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta

from .models import (
    UserWarning, UserMute, UserBan, UserAppeal, AuditLog
)


# =============================================================================
# USER OVERVIEW
# =============================================================================

@login_required
@require_GET
def user_overview(request, username):
    """
    User moderation overview.
    Shows warnings, mutes, bans, and moderation history for a user.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    user = get_object_or_404(User, username=username)

    # Current sanctions
    active_warnings = UserWarning.objects.filter(
        user=user,
        expires_at__gt=timezone.now()
    ).order_by('-created_at')

    active_mutes = UserMute.objects.filter(
        user=user,
        lifted_at__isnull=True
    ).filter(
        Q(is_permanent=True) | Q(expires_at__gt=timezone.now())
    ).order_by('-created_at')

    active_bans = UserBan.objects.filter(
        user=user,
        lifted_at__isnull=True
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    ).order_by('-created_at')

    # History
    warning_history = UserWarning.objects.filter(user=user).order_by('-created_at')[:10]
    mute_history = UserMute.objects.filter(user=user).order_by('-created_at')[:10]
    ban_history = UserBan.objects.filter(user=user).order_by('-created_at')[:10]

    # Appeals
    pending_appeals = UserAppeal.objects.filter(
        user=user,
        status='pending'
    ).order_by('-created_at')

    # Warning points calculation
    total_warning_points = UserWarning.objects.filter(
        user=user,
        expires_at__gt=timezone.now()
    ).aggregate(
        total=Count('points')
    )['total'] or 0

    # Log user overview access
    AuditLog.objects.create(
        actor=request.user,
        action_type='view',
        action_name='user_overview_access',
        affected_user=user,
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    context = {
        'target_user': user,
        'active_warnings': active_warnings,
        'active_mutes': active_mutes,
        'active_bans': active_bans,
        'warning_history': warning_history,
        'mute_history': mute_history,
        'ban_history': ban_history,
        'pending_appeals': pending_appeals,
        'total_warning_points': total_warning_points,
    }

    return render(request, 'admin_panel/sanctions/user_overview.html', context)


# =============================================================================
# WARNING SYSTEM
# =============================================================================

@login_required
def issue_warning(request, username):
    """
    Issue warning to user.
    GET: Show warning form, POST: Process warning issuance.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    user = get_object_or_404(User, username=username)

    if request.method == 'POST':
        warning_type = request.POST.get('warning_type')
        severity = request.POST.get('severity')
        reason = request.POST.get('reason')
        evidence = request.POST.get('evidence', '')
        expires_days = request.POST.get('expires_days', '30')

        if not all([warning_type, severity, reason]):
            messages.error(request, "Warning type, severity, and reason are required.")
            return redirect('admin_panel:issue_warning', username=username)

        try:
            expires_days = int(expires_days)
            if expires_days <= 0:
                expires_days = 30
        except ValueError:
            expires_days = 30

        # Calculate points based on severity
        points_map = {'low': 1, 'medium': 3, 'high': 5, 'critical': 10}
        points = points_map.get(severity, 1)

        # Create warning
        warning = UserWarning.objects.create(
            user=user,
            issuer=request.user,
            warning_type=warning_type,
            severity=severity,
            points=points,
            reason=reason,
            evidence=evidence,
            expires_at=timezone.now() + timedelta(days=expires_days)
        )

        # Create audit log
        AuditLog.objects.create(
            actor=request.user,
            action_type='moderation',
            action_name='warning_issued',
            affected_user=user,
            target_type='warning',
            target_id=str(warning.id),
            details=f"Type: {warning_type}, Severity: {severity}, Points: {points}",
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            result='success'
        )

        messages.success(request, f"Warning issued to {user.username}.")
        return redirect('admin_panel:user_overview', username=username)

    # GET request - show form
    context = {
        'target_user': user,
        'warning_types': UserWarning.WARNING_TYPE_CHOICES,
        'severity_choices': [
            ('low', 'Low (1 point)'),
            ('medium', 'Medium (3 points)'),
            ('high', 'High (5 points)'),
            ('critical', 'Critical (10 points)')
        ]
    }

    return render(request, 'admin_panel/sanctions/warning_form.html', context)


# =============================================================================
# MUTE SYSTEM
# =============================================================================

@login_required
def mute_user(request, username):
    """
    Mute user from posting/commenting.
    GET: Show mute form, POST: Process mute.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    user = get_object_or_404(User, username=username)

    # Check if user is already muted
    existing_mute = UserMute.objects.filter(
        user=user,
        lifted_at__isnull=True
    ).filter(
        Q(is_permanent=True) | Q(expires_at__gt=timezone.now())
    ).first()

    if request.method == 'POST':
        if existing_mute:
            messages.error(request, f"{user.username} is already muted.")
            return redirect('admin_panel:user_overview', username=username)

        scope = request.POST.get('scope')
        reason = request.POST.get('reason')
        duration = request.POST.get('duration', '24')
        is_permanent = request.POST.get('is_permanent') == 'on'

        if not all([scope, reason]):
            messages.error(request, "Scope and reason are required.")
            return redirect('admin_panel:mute_user', username=username)

        # Calculate expiration
        expires_at = None
        if not is_permanent:
            try:
                duration_hours = int(duration)
                expires_at = timezone.now() + timedelta(hours=duration_hours)
            except ValueError:
                expires_at = timezone.now() + timedelta(hours=24)

        # Create mute
        mute = UserMute.objects.create(
            user=user,
            issuer=request.user,
            scope=scope,
            reason=reason,
            duration=duration if not is_permanent else None,
            is_permanent=is_permanent,
            expires_at=expires_at
        )

        # Create audit log
        duration_text = "Permanent" if is_permanent else f"{duration} hours"
        AuditLog.objects.create(
            actor=request.user,
            action_type='moderation',
            action_name='user_muted',
            affected_user=user,
            target_type='mute',
            target_id=str(mute.id),
            details=f"Scope: {scope}, Duration: {duration_text}",
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            result='success'
        )

        messages.success(request, f"{user.username} has been muted.")
        return redirect('admin_panel:user_overview', username=username)

    # GET request - show form
    context = {
        'target_user': user,
        'existing_mute': existing_mute,
        'scope_choices': UserMute.SCOPE_CHOICES,
    }

    return render(request, 'admin_panel/sanctions/mute_form.html', context)


@login_required
@require_POST
def lift_mute(request, pk):
    """
    Lift an active mute.
    Removes mute and logs the action.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    mute = get_object_or_404(UserMute, id=pk, lifted_at__isnull=True)

    lift_reason = request.POST.get('lift_reason', 'Lifted by moderator')

    mute.lifted_by = request.user
    mute.lifted_at = timezone.now()
    mute.lift_reason = lift_reason
    mute.save()

    # Create audit log
    AuditLog.objects.create(
        actor=request.user,
        action_type='moderation',
        action_name='mute_lifted',
        affected_user=mute.user,
        target_type='mute',
        target_id=str(mute.id),
        details=f"Reason: {lift_reason}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    messages.success(request, f"Mute lifted for {mute.user.username}.")
    return redirect('admin_panel:user_overview', username=mute.user.username)


# =============================================================================
# BAN SYSTEM
# =============================================================================

@login_required
def ban_user(request, username):
    """
    Ban user from platform.
    GET: Show ban form, POST: Process ban.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    user = get_object_or_404(User, username=username)

    # Check if user is already banned
    existing_ban = UserBan.objects.filter(
        user=user,
        lifted_at__isnull=True
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    ).first()

    if request.method == 'POST':
        if existing_ban:
            messages.error(request, f"{user.username} is already banned.")
            return redirect('admin_panel:user_overview', username=username)

        ban_type = request.POST.get('ban_type')
        reason = request.POST.get('reason')
        evidence = request.POST.get('evidence', '')
        duration = request.POST.get('duration', '7')
        ip_addresses = request.POST.get('ip_addresses', '')
        allow_appeal = request.POST.get('allow_appeal') == 'on'

        if not all([ban_type, reason]):
            messages.error(request, "Ban type and reason are required.")
            return redirect('admin_panel:ban_user', username=username)

        # Calculate expiration for temporary bans
        expires_at = None
        if ban_type == 'temporary':
            try:
                duration_days = int(duration)
                expires_at = timezone.now() + timedelta(days=duration_days)
            except ValueError:
                expires_at = timezone.now() + timedelta(days=7)

        # Create ban
        ban = UserBan.objects.create(
            user=user,
            issuer=request.user,
            ban_type=ban_type,
            reason=reason,
            evidence=evidence,
            duration=duration if ban_type == 'temporary' else None,
            expires_at=expires_at,
            ip_addresses=ip_addresses,
            allow_appeal=allow_appeal
        )

        # Create audit log
        duration_text = "Permanent" if ban_type == 'permanent' else f"{duration} days"
        AuditLog.objects.create(
            actor=request.user,
            action_type='moderation',
            action_name='user_banned',
            affected_user=user,
            target_type='ban',
            target_id=str(ban.id),
            details=f"Type: {ban_type}, Duration: {duration_text}, Appeal allowed: {allow_appeal}",
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            result='success'
        )

        messages.success(request, f"{user.username} has been banned.")
        return redirect('admin_panel:user_overview', username=username)

    # GET request - show form
    context = {
        'target_user': user,
        'existing_ban': existing_ban,
        'ban_types': UserBan.BAN_TYPE_CHOICES,
    }

    return render(request, 'admin_panel/sanctions/ban_form.html', context)


@login_required
@require_POST
def lift_ban(request, pk):
    """
    Lift an active ban.
    Removes ban and logs the action.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    ban = get_object_or_404(UserBan, id=pk, lifted_at__isnull=True)

    lift_reason = request.POST.get('lift_reason', 'Lifted by moderator')

    ban.lifted_by = request.user
    ban.lifted_at = timezone.now()
    ban.lift_reason = lift_reason
    ban.save()

    # Create audit log
    AuditLog.objects.create(
        actor=request.user,
        action_type='moderation',
        action_name='ban_lifted',
        affected_user=ban.user,
        target_type='ban',
        target_id=str(ban.id),
        details=f"Reason: {lift_reason}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    messages.success(request, f"Ban lifted for {ban.user.username}.")
    return redirect('admin_panel:user_overview', username=ban.user.username)


# =============================================================================
# APPEAL SYSTEM
# =============================================================================

@login_required
@require_GET
def appeal_list(request):
    """
    List pending appeals.
    Shows all appeals awaiting review.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    appeals = UserAppeal.objects.all().select_related('user', 'reviewer')

    # Filters
    status_filter = request.GET.get('status')
    if status_filter and status_filter != 'all':
        appeals = appeals.filter(status=status_filter)

    sanction_type_filter = request.GET.get('sanction_type')
    if sanction_type_filter and sanction_type_filter != 'all':
        appeals = appeals.filter(sanction_type=sanction_type_filter)

    # Ordering - pending first
    appeals = appeals.order_by(
        'status',  # pending first
        '-created_at'
    )

    # Pagination
    paginator = Paginator(appeals, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'status_choices': UserAppeal.STATUS_CHOICES,
        'sanction_type_choices': UserAppeal.SANCTION_TYPE_CHOICES,
        'current_filters': {
            'status': status_filter,
            'sanction_type': sanction_type_filter,
        }
    }

    return render(request, 'admin_panel/appeals/list.html', context)


@login_required
def appeal_review(request, pk):
    """
    Review and decide on appeal.
    GET: Show appeal details, POST: Process decision.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    appeal = get_object_or_404(UserAppeal, id=pk)

    if request.method == 'POST':
        if appeal.status != 'pending':
            messages.error(request, "Appeal has already been reviewed.")
            return redirect('admin_panel:appeal_list')

        outcome = request.POST.get('outcome')
        decision_notes = request.POST.get('decision_notes', '')

        if not outcome:
            messages.error(request, "Decision outcome is required.")
            return redirect('admin_panel:appeal_review', pk=pk)

        # Update appeal
        appeal.status = 'reviewed'
        appeal.reviewer = request.user
        appeal.outcome = outcome
        appeal.decision_notes = decision_notes
        appeal.reviewed_at = timezone.now()
        appeal.save()

        # Create audit log
        AuditLog.objects.create(
            actor=request.user,
            action_type='moderation',
            action_name='appeal_reviewed',
            affected_user=appeal.user,
            target_type='appeal',
            target_id=str(appeal.id),
            details=f"Outcome: {outcome}, Sanction: {appeal.sanction_type}",
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            result='success'
        )

        messages.success(request, f"Appeal {outcome}.")
        return redirect('admin_panel:appeal_list')

    # GET request - show appeal details
    context = {
        'appeal': appeal,
        'outcome_choices': UserAppeal.OUTCOME_CHOICES,
    }

    return render(request, 'admin_panel/appeals/review.html', context)