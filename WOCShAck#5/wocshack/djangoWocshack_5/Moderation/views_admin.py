"""
Admin moderation views.
Staff management, audit logs, templates, announcements, and auto-moderation rules.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth.models import User

from django.contrib.contenttypes.models import ContentType

from .models import (
    AuditLog, AuditRetention, StaffRole, StaffAssignment,
    AutoModRule, AutoModLog
)


# =============================================================================
# AUDIT LOGGING
# =============================================================================

@login_required
@require_GET
def audit_log(request):
    """
    Audit log viewer with search and filtering.
    Shows comprehensive moderation activity log.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    logs = AuditLog.objects.all().select_related('actor', 'affected_user')

    # Filters
    action_type_filter = request.GET.get('action_type')
    if action_type_filter and action_type_filter != 'all':
        logs = logs.filter(action_type=action_type_filter)

    actor_filter = request.GET.get('actor')
    if actor_filter and actor_filter != 'all':
        logs = logs.filter(actor__username=actor_filter)

    result_filter = request.GET.get('result')
    if result_filter and result_filter != 'all':
        logs = logs.filter(result=result_filter)

    # Date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        try:
            logs = logs.filter(created_at__gte=date_from)
        except:
            messages.warning(request, "Invalid date format for 'from' date.")

    if date_to:
        try:
            logs = logs.filter(created_at__lte=date_to)
        except:
            messages.warning(request, "Invalid date format for 'to' date.")

    # Search
    search_query = request.GET.get('search')
    if search_query:
        logs = logs.filter(
            Q(action_name__icontains=search_query) |
            Q(details__icontains=search_query) |
            Q(ip_address__icontains=search_query) |
            Q(affected_user__username__icontains=search_query)
        )

    # Ordering
    logs = logs.order_by('-created_at')

    # Pagination
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get unique values for filters
    action_types = AuditLog.objects.values_list(
        'action_type', flat=True
    ).distinct().order_by('action_type')
    
    actors = AuditLog.objects.values_list(
        'actor__username', flat=True
    ).distinct().order_by('actor__username')

    context = {
        'page_obj': page_obj,
        'action_types': action_types,
        'actors': actors,
        'result_choices': AuditLog.RESULT_CHOICES,
        'current_filters': {
            'action_type': action_type_filter,
            'actor': actor_filter,
            'result': result_filter,
            'date_from': date_from,
            'date_to': date_to,
            'search': search_query,
        }
    }

    return render(request, 'admin_panel/audit/log.html', context)


# =============================================================================
# STAFF MANAGEMENT
# =============================================================================

@login_required
@require_GET
def staff_list(request):
    """
    List all users with their staff status.
    Superusers can toggle is_staff directly from this page.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    staff_list_data = [
        {'user': user}
        for user in User.objects.all().order_by('username')
    ]

    return render(request, 'admin_panel/staff/list.html', {'staff_list_data': staff_list_data})


@login_required
def staff_assign_role(request, user_id):
    """
    Assign moderation role to staff.
    GET: Show assignment form, POST: Process assignment.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    user = get_object_or_404(User, id=user_id, is_staff=True)
    
    if request.method == 'POST':
        role_id = request.POST.get('role_id')
        module_access = request.POST.get('module_access', '')
        daily_action_limit = request.POST.get('daily_action_limit', '100')
        notes = request.POST.get('notes', '')

        if not role_id:
            messages.error(request, "Role is required.")
            return redirect('admin_panel:staff_assign_role', user_id=user_id)

        try:
            role = StaffRole.objects.get(id=role_id)
        except StaffRole.DoesNotExist:
            messages.error(request, "Invalid role selected.")
            return redirect('admin_panel:staff_assign_role', user_id=user_id)

        try:
            daily_limit = int(daily_action_limit)
        except ValueError:
            daily_limit = 100

        # Check for existing active assignment (is_active is a @property, filter via DB fields)
        today = timezone.now().date()
        existing = StaffAssignment.objects.filter(
            user=user,
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).first()

        if existing:
            # Update existing assignment
            existing.role = role
            existing.module_access = module_access
            existing.daily_action_limit = daily_limit
            existing.notes = notes
            existing.save()
            action = 'updated'
        else:
            # Create new assignment
            StaffAssignment.objects.create(
                user=user,
                role=role,
                assigned_by=request.user,
                module_access=module_access,
                daily_action_limit=daily_limit,
                notes=notes,
                start_date=timezone.now().date()
            )
            action = 'assigned'

        # Create audit log
        AuditLog.objects.create(
            actor=request.user,
            action_type='staff',
            action_name=f'staff_role_{action}',
            affected_user=user,
            details=f"Role: {role.name}, Modules: {module_access}, Limit: {daily_limit}",
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            result='success'
        )

        messages.success(request, f"Staff role {action} for {user.username}.")
        return redirect('admin_panel:staff_list')

    # GET request - show form
    roles = StaffRole.objects.all()
    today = timezone.now().date()
    existing_assignment = StaffAssignment.objects.filter(
        user=user,
        start_date__lte=today
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    ).first()

    context = {
        'target_user': user,
        'roles': roles,
        'existing_assignment': existing_assignment,
        'module_choices': [
            ('forum', 'Forum'),
            ('shopping', 'Shopping'),
            ('chatbot', 'Chatbot'),
            ('community', 'Community'),
            ('developer', 'Developer'),
        ]
    }

    return render(request, 'admin_panel/staff/assign_role.html', context)


@login_required
@require_POST
def staff_promote(request):
    """
    Promote a user to staff by username.
    Superuser-only. Creates an AuditLog entry and redirects to role assignment.
    """
    if not request.user.is_superuser:
        messages.error(request, "Access denied.")
        return redirect('admin_panel:staff_list')

    username = request.POST.get('username', '').strip()
    if not username:
        messages.error(request, "Username is required.")
        return redirect('admin_panel:staff_list')

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        messages.error(request, f"User '{username}' not found.")
        return redirect('admin_panel:staff_list')

    if user.is_staff:
        messages.warning(request, f"{user.username} is already a staff member.")
        return redirect('admin_panel:staff_assign_role', user_id=user.id)

    user.is_staff = True
    user.save()

    AuditLog.objects.create(
        actor=request.user,
        action_type='staff',
        action_name='staff_promoted',
        affected_user=user,
        details={"promoted_user": user.username, "actor": request.user.username},
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    messages.success(request, f"{user.username} promoted to staff.")
    return redirect('admin_panel:staff_assign_role', user_id=user.id)


@login_required
@require_POST
def staff_remove(request, user_id):
    """
    Remove a user from staff.
    Superuser-only. Expires active StaffAssignments and creates an AuditLog entry.
    """
    if not request.user.is_superuser:
        messages.error(request, "Access denied.")
        return redirect('admin_panel:staff_list')

    user = get_object_or_404(User, id=user_id, is_staff=True)

    if user == request.user:
        messages.error(request, "You cannot remove yourself from staff.")
        return redirect('admin_panel:staff_list')

    user.is_staff = False
    user.save()

    # Expire all active StaffAssignments for this user
    today = timezone.now().date()
    active_assignments = StaffAssignment.objects.filter(
        user=user,
        start_date__lte=today
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    )
    for assignment in active_assignments:
        assignment.end_date = today
        assignment.save()

    AuditLog.objects.create(
        actor=request.user,
        action_type='staff',
        action_name='staff_removed',
        affected_user=user,
        details={"removed_user": user.username, "actor": request.user.username},
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    messages.success(request, f"{user.username} removed from staff.")
    return redirect('admin_panel:staff_list')


@login_required
@require_POST
def staff_toggle(request, user_id):
    """Toggle is_staff for a user. Superuser-only."""
    if not request.user.is_superuser:
        messages.error(request, "Access denied.")
        return redirect('admin_panel:staff_list')

    user = get_object_or_404(User, id=user_id)

    if user == request.user:
        messages.error(request, "You cannot change your own staff status.")
        return redirect('admin_panel:staff_list')

    user.is_staff = not user.is_staff
    user.save()

    AuditLog.objects.create(
        actor=request.user,
        action_type='staff',
        action_name='staff_promoted' if user.is_staff else 'staff_removed',
        affected_user=user,
        details={"user": user.username, "is_staff": user.is_staff, "actor": request.user.username},
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    status = "promoted to staff" if user.is_staff else "removed from staff"
    messages.success(request, f"{user.username} {status}.")
    return redirect('admin_panel:staff_list')


@login_required
def staff_user_search(request):
    """AJAX endpoint: search users by username. Returns JSON list of {id, username}."""
    if not request.user.is_staff:
        return JsonResponse({'results': []}, status=403)

    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'results': []})

    users = User.objects.filter(username__icontains=q).order_by('username')[:10]
    return JsonResponse({'results': [{'id': u.id, 'username': u.username} for u in users]})


# =============================================================================
# AUTO-MODERATION
# =============================================================================

@login_required
@require_GET
def automod_rules(request):
    """
    List auto-moderation rules.
    Shows configured rules for automated content moderation.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    rules = AutoModRule.objects.all().select_related('created_by')

    # Filter by trigger type
    trigger_filter = request.GET.get('trigger')
    if trigger_filter and trigger_filter != 'all':
        rules = rules.filter(trigger_type=trigger_filter)

    # Filter by active status
    active_filter = request.GET.get('active')
    if active_filter == 'true':
        rules = rules.filter(is_active=True)
    elif active_filter == 'false':
        rules = rules.filter(is_active=False)

    # Ordering
    rules = rules.order_by('-is_active', 'priority', 'name')

    context = {
        'rules': rules,
        'trigger_choices': AutoModRule.TRIGGER_TYPE_CHOICES,
        'current_filters': {
            'trigger': trigger_filter,
            'active': active_filter,
        }
    }

    return render(request, 'admin_panel/automod/rules.html', context)


@login_required
def automod_rule_edit(request, pk):
    """
    Edit/create auto-mod rule.
    GET: Show form, POST: Process update/creation.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    rule = None
    if pk != 'new':
        rule = get_object_or_404(AutoModRule, id=pk)

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        trigger_type = request.POST.get('trigger_type')
        trigger_value = request.POST.get('trigger_value')
        action = request.POST.get('action')
        action_params = request.POST.get('action_params', '')
        scope = request.POST.get('scope', 'all')
        priority = request.POST.get('priority', '1')
        is_active = request.POST.get('is_active') == 'on'

        if not all([name, trigger_type, trigger_value, action]):
            messages.error(request, "Name, trigger type, trigger value, and action are required.")
            return redirect('admin_panel:automod_rule_edit', pk=pk)

        try:
            priority = int(priority)
        except ValueError:
            priority = 1

        if rule:
            # Update existing rule
            rule.name = name
            rule.description = description
            rule.trigger_type = trigger_type
            rule.trigger_value = trigger_value
            rule.action = action
            rule.action_params = action_params
            rule.scope = scope
            rule.priority = priority
            rule.is_active = is_active
            rule.updated_at = timezone.now()
            rule.save()
            action_name = 'automod_rule_updated'
            success_message = f"Auto-mod rule '{name}' updated successfully."
        else:
            # Create new rule
            rule = AutoModRule.objects.create(
                name=name,
                description=description,
                trigger_type=trigger_type,
                trigger_value=trigger_value,
                action=action,
                action_params=action_params,
                scope=scope,
                priority=priority,
                is_active=is_active,
                created_by=request.user
            )
            action_name = 'automod_rule_created'
            success_message = f"Auto-mod rule '{name}' created successfully."

        # Create audit log
        AuditLog.objects.create(
            actor=request.user,
            action_type='admin',
            action_name=action_name,
            target_type=ContentType.objects.get_for_model(AutoModRule),
            target_id=str(rule.id),
            details=f"Trigger: {trigger_type}, Action: {action}, Active: {is_active}",
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            result='success'
        )

        messages.success(request, success_message)
        return redirect('admin_panel:automod_rules')

    # GET request - show form
    context = {
        'rule': rule,
        'trigger_type_choices': AutoModRule.TRIGGER_TYPE_CHOICES,
        'action_choices': AutoModRule.ACTION_CHOICES,
    }

    return render(request, 'admin_panel/automod/rule_form.html', context)


@login_required
@require_GET
def automod_logs(request):
    """
    View auto-moderation action logs.
    Shows actions taken by automated moderation rules.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    logs = AutoModLog.objects.all().select_related('rule', 'user', 'reviewed_by')

    # Filters
    rule_filter = request.GET.get('rule')
    if rule_filter and rule_filter != 'all':
        logs = logs.filter(rule__name=rule_filter)

    action_filter = request.GET.get('action')
    if action_filter and action_filter != 'all':
        logs = logs.filter(action_taken=action_filter)

    review_filter = request.GET.get('review_status')
    if review_filter and review_filter != 'all':
        logs = logs.filter(review_status=review_filter)

    # Date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        try:
            logs = logs.filter(created_at__gte=date_from)
        except:
            messages.warning(request, "Invalid date format for 'from' date.")

    if date_to:
        try:
            logs = logs.filter(created_at__lte=date_to)
        except:
            messages.warning(request, "Invalid date format for 'to' date.")

    # Ordering
    logs = logs.order_by('-created_at')

    # Pagination
    paginator = Paginator(logs, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get unique values for filters
    rule_names = AutoModLog.objects.values_list(
        'rule__name', flat=True
    ).distinct().order_by('rule__name')

    context = {
        'page_obj': page_obj,
        'rule_names': rule_names,
        'review_status_choices': AutoModLog.REVIEW_STATUS_CHOICES,
        'current_filters': {
            'rule': rule_filter,
            'action': action_filter,
            'review_status': review_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
    }

    return render(request, 'admin_panel/automod/logs.html', context)