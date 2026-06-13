"""
Main moderation views.
Dashboard, report management, and core moderation functionality.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.contrib.auth.models import User

from .models import (
    ModerationQueue, ContentAction, Report, ReportNote,
    UserWarning, UserMute, UserBan, AuditLog
)


# =============================================================================
# MAIN DASHBOARD
# =============================================================================

@login_required
@require_GET
def moderation_dashboard(request):
    """
    Staff-only dashboard showing moderation overview.
    Shows pending reports, queue status, active sanctions, and quick actions.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    # Pending reports with priority breakdown
    pending_reports = Report.objects.filter(status='pending')
    report_counts = pending_reports.aggregate(
        total=Count('id'),
        critical=Count('id', filter=Q(priority='critical')),
        high=Count('id', filter=Q(priority='high')),
        medium=Count('id', filter=Q(priority='medium')),
        low=Count('id', filter=Q(priority='low'))
    )

    # Moderation queue status
    queue_counts = ModerationQueue.objects.filter(status='pending').aggregate(
        total=Count('id'),
        critical=Count('id', filter=Q(priority='critical')),
        high=Count('id', filter=Q(priority='high'))
    )

    # Active sanctions
    active_warnings = UserWarning.objects.filter(
        expires_at__gt=timezone.now()
    ).count()
    
    active_mutes = UserMute.objects.filter(
        Q(is_permanent=True) | Q(expires_at__gt=timezone.now()),
        lifted_at__isnull=True
    ).count()
    
    active_bans = UserBan.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
        lifted_at__isnull=True
    ).count()

    # Recent moderation actions (last 24h)
    recent_actions = ContentAction.objects.filter(
        created_at__gte=timezone.now() - timezone.timedelta(hours=24)
    ).select_related('actor')[:10]

    # Staff's assigned reports
    my_reports = Report.objects.filter(
        assigned_to=request.user,
        status='pending'
    )[:5]

    # Log dashboard access
    AuditLog.objects.create(
        actor=request.user,
        action_type='view',
        action_name='moderation_dashboard_access',
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    context = {
        'report_counts': report_counts,
        'queue_counts': queue_counts,
        'active_warnings': active_warnings,
        'active_mutes': active_mutes,
        'active_bans': active_bans,
        'recent_actions': recent_actions,
        'my_reports': my_reports,
    }

    return render(request, 'admin_panel/dashboard.html', context)


# =============================================================================
# REPORT MANAGEMENT
# =============================================================================

@login_required
@require_GET
def report_list(request):
    """
    List reports with filtering and pagination.
    Allows filtering by status, priority, type, and assignment.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    reports = Report.objects.all().select_related('reporter', 'assigned_to')

    # Filters
    status_filter = request.GET.get('status')
    if status_filter and status_filter != 'all':
        reports = reports.filter(status=status_filter)

    priority_filter = request.GET.get('priority')
    if priority_filter and priority_filter != 'all':
        reports = reports.filter(priority=priority_filter)

    type_filter = request.GET.get('type')
    if type_filter and type_filter != 'all':
        reports = reports.filter(report_type=type_filter)

    assignment_filter = request.GET.get('assignment')
    if assignment_filter == 'unassigned':
        reports = reports.filter(assigned_to__isnull=True)
    elif assignment_filter == 'mine':
        reports = reports.filter(assigned_to=request.user)

    # Search
    search_query = request.GET.get('search')
    if search_query:
        reports = reports.filter(
            Q(description__icontains=search_query) |
            Q(reporter__username__icontains=search_query) |
            Q(resolution_notes__icontains=search_query)
        )

    # Ordering
    reports = reports.order_by('-created_at')

    # Pagination
    paginator = Paginator(reports, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Filter choices
    status_choices = Report.STATUS_CHOICES
    priority_choices = Report.PRIORITY_CHOICES
    type_choices = Report.REPORT_TYPE_CHOICES

    context = {
        'page_obj': page_obj,
        'status_choices': status_choices,
        'priority_choices': priority_choices,
        'type_choices': type_choices,
        'current_filters': {
            'status': status_filter,
            'priority': priority_filter,
            'type': type_filter,
            'assignment': assignment_filter,
            'search': search_query,
        }
    }

    return render(request, 'admin_panel/reports/list.html', context)


@login_required
@require_GET
def report_detail(request, pk):
    """
    View report details with notes and actions.
    Shows full report information, internal notes, and action history.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    report = get_object_or_404(Report, id=pk)

    # Get report notes
    notes = ReportNote.objects.filter(report=report).select_related('author').order_by('created_at')

    # Get related content actions
    content_actions = ContentAction.objects.filter(
        content_type=report.content_type,
        object_id=report.object_id
    ).select_related('actor').order_by('-created_at')

    # Log report access
    AuditLog.objects.create(
        actor=request.user,
        action_type='view',
        action_name='report_detail_access',
        target_type='report',
        target_id=str(report.id),
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    context = {
        'report': report,
        'notes': notes,
        'content_actions': content_actions,
    }

    return render(request, 'admin_panel/reports/detail.html', context)


@login_required
@require_POST
def report_resolve(request, pk):
    """
    Resolve a report with outcome and notes.
    Updates report status and creates audit log entry.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    report = get_object_or_404(Report, id=pk)

    if report.status == 'resolved':
        messages.error(request, "Report is already resolved.")
        return redirect('admin_panel:report_detail', pk=pk)

    resolution_type = request.POST.get('resolution_type')
    resolution_notes = request.POST.get('resolution_notes', '')
    is_valid = request.POST.get('is_valid') == 'on'

    if not resolution_type:
        messages.error(request, "Resolution type is required.")
        return redirect('admin_panel:report_detail', pk=pk)

    # Update report
    report.status = 'resolved'
    report.resolution_type = resolution_type
    report.resolution_notes = resolution_notes
    report.is_valid = is_valid
    report.resolved_at = timezone.now()
    report.save()

    # Create audit log
    AuditLog.objects.create(
        actor=request.user,
        action_type='moderation',
        action_name='report_resolved',
        target_type='report',
        target_id=str(report.id),
        affected_user=report.reporter,
        details=f"Resolution: {resolution_type}, Valid: {is_valid}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    messages.success(request, f"Report resolved as {resolution_type}.")
    return redirect('admin_panel:report_detail', pk=pk)


@login_required
@require_POST
def report_assign(request, pk):
    """
    Assign report to a moderator.
    Allows staff to assign reports to themselves or other moderators.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    report = get_object_or_404(Report, id=pk)
    
    assignee_id = request.POST.get('assignee_id')
    if assignee_id == 'self':
        assignee = request.user
    elif assignee_id == 'unassign':
        assignee = None
    else:
        try:
            assignee = User.objects.get(id=assignee_id, is_staff=True)
        except User.DoesNotExist:
            messages.error(request, "Invalid assignee selected.")
            return redirect('admin_panel:report_detail', pk=pk)

    old_assignee = report.assigned_to
    report.assigned_to = assignee
    report.save()

    # Create audit log
    action_detail = f"Assigned from {old_assignee} to {assignee}" if assignee else "Unassigned"
    AuditLog.objects.create(
        actor=request.user,
        action_type='moderation',
        action_name='report_assigned',
        target_type='report',
        target_id=str(report.id),
        affected_user=assignee,
        details=action_detail,
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    if assignee:
        messages.success(request, f"Report assigned to {assignee.username}.")
    else:
        messages.success(request, "Report unassigned.")

    return redirect('admin_panel:report_detail', pk=pk)


@login_required
@require_POST
def add_report_note(request, pk):
    """
    Add internal note to a report.
    Creates a staff-only note for internal communication about the report.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    report = get_object_or_404(Report, id=pk)
    
    content = request.POST.get('content')
    visibility = request.POST.get('visibility', 'staff')

    if not content or not content.strip():
        messages.error(request, "Note content is required.")
        return redirect('admin_panel:report_detail', pk=pk)

    # Create note
    note = ReportNote.objects.create(
        report=report,
        author=request.user,
        content=content.strip(),
        visibility=visibility
    )

    # Create audit log
    AuditLog.objects.create(
        actor=request.user,
        action_type='moderation',
        action_name='report_note_added',
        target_type='report',
        target_id=str(report.id),
        details=f"Visibility: {visibility}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    messages.success(request, "Report note added successfully.")
    return redirect('admin_panel:report_detail', pk=pk)