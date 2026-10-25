"""
Moderation Module REST API.
All endpoints require authentication AND is_staff=True.
Mirrors the functionality of Moderation/views*.py as JSON endpoints.
"""
import json
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta

from .views import api_success, api_error, api_auth_required, paginate_queryset
from Moderation.models import (
    ModerationQueue, ContentAction, Report, ReportNote,
    UserWarning, UserMute, UserBan, UserAppeal, AuditLog,
    AuditRetention, StaffRole, StaffAssignment,
    AutoModRule, AutoModLog,
)


def _staff_required(request):
    """Return None if user is staff, else an api_error response."""
    if not request.user.is_staff:
        return api_error("Staff access required.", status=403)
    return None


# =============================================================================
# DASHBOARD
# =============================================================================

@require_http_methods(["GET"])
@api_auth_required
def dashboard_view(request):
    """ Moderation dashboard statistics."""
    err = _staff_required(request)
    if err:
        return err

    from django.db.models import Count, Q
    pending_reports = Report.objects.filter(status='pending').aggregate(
        total=Count('id'),
        critical=Count('id', filter=Q(priority='critical')),
        high=Count('id', filter=Q(priority='high')),
        medium=Count('id', filter=Q(priority='medium')),
        low=Count('id', filter=Q(priority='low')),
    )
    queue_counts = ModerationQueue.objects.filter(status='pending').aggregate(
        total=Count('id'),
        critical=Count('id', filter=Q(priority='critical')),
        high=Count('id', filter=Q(priority='high')),
    )
    active_warnings = UserWarning.objects.filter(expires_at__gt=timezone.now()).count()
    active_mutes = UserMute.objects.filter(
        Q(is_permanent=True) | Q(expires_at__gt=timezone.now()),
        lifted_at__isnull=True,
    ).count()
    active_bans = UserBan.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
        lifted_at__isnull=True,
    ).count()

    AuditLog.objects.create(
        actor=request.user, action_type='view',
        action_name='api_dashboard_access',
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )

    return api_success({
        'pending_reports': pending_reports,
        'queue_counts': queue_counts,
        'sanctions': {
            'active_warnings': active_warnings,
            'active_mutes': active_mutes,
            'active_bans': active_bans,
        },
    })


# =============================================================================
# REPORTS
# =============================================================================

@require_http_methods(["GET"])
@api_auth_required
def reports_view(request):
    """ List reports with optional filters."""
    err = _staff_required(request)
    if err:
        return err

    from django.db.models import Q
    reports = Report.objects.all().select_related('reporter', 'assigned_to')

    status_f = request.GET.get('status')
    if status_f and status_f != 'all':
        reports = reports.filter(status=status_f)
    priority_f = request.GET.get('priority')
    if priority_f and priority_f != 'all':
        reports = reports.filter(priority=priority_f)
    type_f = request.GET.get('type')
    if type_f and type_f != 'all':
        reports = reports.filter(report_type=type_f)
    assignment_f = request.GET.get('assignment')
    if assignment_f == 'unassigned':
        reports = reports.filter(assigned_to__isnull=True)
    elif assignment_f == 'mine':
        reports = reports.filter(assigned_to=request.user)
    q = request.GET.get('q')
    if q:
        reports = reports.filter(
            Q(description__icontains=q) | Q(reporter__username__icontains=q)
        )

    reports = reports.order_by('-created_at')
    paginated = paginate_queryset(reports, request, default_per_page=20)

    data = []
    for r in paginated['items']:
        data.append({
            'id': str(r.id),
            'report_type': r.report_type,
            'status': r.status,
            'priority': r.priority,
            'reporter': r.reporter.username if r.reporter else None,
            'assigned_to': r.assigned_to.username if r.assigned_to else None,
            'description': r.description,
            'created_at': r.created_at.isoformat(),
        })

    return api_success({'reports': data, 'pagination': paginated['pagination']})


@require_http_methods(["GET"])
@api_auth_required
def report_detail_view(request, pk):
    """ Get report details with notes and related actions."""
    err = _staff_required(request)
    if err:
        return err

    report = get_object_or_404(Report, id=pk)
    notes = ReportNote.objects.filter(report=report).select_related('author').order_by('created_at')
    content_actions = ContentAction.objects.filter(
        content_type=report.content_type,
        object_id=report.object_id,
    ).select_related('actor').order_by('-created_at')

    return api_success({
        'id': str(report.id),
        'report_type': report.report_type,
        'status': report.status,
        'priority': report.priority,
        'reporter': report.reporter.username if report.reporter else None,
        'assigned_to': report.assigned_to.username if report.assigned_to else None,
        'description': report.description,
        'resolution_type': report.resolution_type,
        'resolution_notes': report.resolution_notes,
        'is_valid': report.is_valid,
        'resolved_at': report.resolved_at.isoformat() if report.resolved_at else None,
        'created_at': report.created_at.isoformat(),
        'notes': [
            {
                'id': str(n.id),
                'author': n.author.username,
                'content': n.content,
                'visibility': n.visibility,
                'created_at': n.created_at.isoformat(),
            } for n in notes
        ],
        'content_actions': [
            {
                'id': str(a.id),
                'action_type': a.action_type,
                'actor': a.actor.username if a.actor else None,
                'reason': a.reason,
                'created_at': a.created_at.isoformat(),
            } for a in content_actions
        ],
    })


@require_http_methods(["POST"])
@api_auth_required
def report_resolve_view(request, pk):
    """ Resolve a report. Body: {resolution_type, resolution_notes, is_valid}"""
    err = _staff_required(request)
    if err:
        return err

    report = get_object_or_404(Report, id=pk)
    if report.status == 'resolved':
        return api_error("Report is already resolved.", status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    resolution_type = data.get('resolution_type')
    if not resolution_type:
        return api_error("resolution_type is required.", status=400)

    report.status = 'resolved'
    report.resolution_type = resolution_type
    report.resolution_notes = data.get('resolution_notes', '')
    report.is_valid = bool(data.get('is_valid', False))
    report.resolved_at = timezone.now()
    report.save()

    AuditLog.objects.create(
        actor=request.user, action_type='moderation',
        action_name='report_resolved', target_type='report',
        target_id=str(report.id), affected_user=report.reporter,
        details=f"Resolution: {resolution_type}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )
    return api_success({'status': 'resolved', 'resolution_type': resolution_type})


@require_http_methods(["POST"])
@api_auth_required
def report_assign_view(request, pk):
    """ Assign report. Body: {assignee_id: 'self'|'unassign'|<user_id>}"""
    err = _staff_required(request)
    if err:
        return err

    report = get_object_or_404(Report, id=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    assignee_id = str(data.get('assignee_id', '')).strip()
    if assignee_id == 'self':
        assignee = request.user
    elif assignee_id == 'unassign':
        assignee = None
    else:
        try:
            assignee = User.objects.get(id=assignee_id, is_staff=True)
        except (User.DoesNotExist, ValueError):
            return api_error("Invalid assignee.", status=400)

    report.assigned_to = assignee
    report.save()
    return api_success({
        'assigned_to': assignee.username if assignee else None,
    }, message="Report assigned." if assignee else "Report unassigned.")


@require_http_methods(["POST"])
@api_auth_required
def report_note_view(request, pk):
    """ Add internal note. Body: {content, visibility}"""
    err = _staff_required(request)
    if err:
        return err

    report = get_object_or_404(Report, id=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    content = str(data.get('content', '')).strip()
    if not content:
        return api_error("content is required.", status=400)

    note = ReportNote.objects.create(
        report=report, author=request.user,
        content=content,
        visibility=data.get('visibility', 'staff'),
    )
    return api_success({'id': str(note.id)}, message="Note added.", status=201)


# =============================================================================
# CONTENT QUEUE
# =============================================================================

@require_http_methods(["GET"])
@api_auth_required
def content_queue_view(request):
    """ List moderation queue items."""
    err = _staff_required(request)
    if err:
        return err

    items = ModerationQueue.objects.all().select_related('assigned_to', 'content_type')

    status_f = request.GET.get('status')
    if status_f and status_f != 'all':
        items = items.filter(status=status_f)
    priority_f = request.GET.get('priority')
    if priority_f and priority_f != 'all':
        items = items.filter(priority=priority_f)
    module_f = request.GET.get('module')
    if module_f and module_f != 'all':
        items = items.filter(source_module=module_f)
    assignment_f = request.GET.get('assignment')
    if assignment_f == 'unassigned':
        items = items.filter(assigned_to__isnull=True)
    elif assignment_f == 'mine':
        items = items.filter(assigned_to=request.user)

    items = items.order_by('status', '-priority', '-auto_flagged', 'created_at')
    paginated = paginate_queryset(items, request, default_per_page=20)

    data = []
    for item in paginated['items']:
        data.append({
            'id': str(item.id),
            'source_module': item.source_module,
            'status': item.status,
            'priority': item.priority,
            'auto_flagged': item.auto_flagged,
            'assigned_to': item.assigned_to.username if item.assigned_to else None,
            'created_at': item.created_at.isoformat(),
        })
    return api_success({'items': data, 'pagination': paginated['pagination']})


@require_http_methods(["GET"])
@api_auth_required
def content_review_view(request, pk):
    """ Get queue item details."""
    err = _staff_required(request)
    if err:
        return err

    item = get_object_or_404(ModerationQueue, id=pk)
    previous_actions = ContentAction.objects.filter(
        content_type=item.content_type, object_id=item.object_id
    ).select_related('actor').order_by('-created_at')

    return api_success({
        'id': str(item.id),
        'source_module': item.source_module,
        'status': item.status,
        'priority': item.priority,
        'auto_flagged': item.auto_flagged,
        'assigned_to': item.assigned_to.username if item.assigned_to else None,
        'created_at': item.created_at.isoformat(),
        'previous_actions': [
            {
                'id': str(a.id),
                'action_type': a.action_type,
                'actor': a.actor.username if a.actor else None,
                'reason': a.reason,
                'created_at': a.created_at.isoformat(),
            } for a in previous_actions
        ],
    })


@require_http_methods(["POST"])
@api_auth_required
def content_action_view(request, pk):
    """ Take action on queue item. Body: {action_type, reason, internal_notes}"""
    err = _staff_required(request)
    if err:
        return err

    item = get_object_or_404(ModerationQueue, id=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    action_type = data.get('action_type')
    valid_actions = [c[0] for c in ContentAction.ACTION_TYPE_CHOICES]
    if not action_type or action_type not in valid_actions:
        return api_error(f"action_type must be one of: {', '.join(valid_actions)}", status=400)

    ContentAction.objects.create(
        content_type=item.content_type,
        object_id=item.object_id,
        action_type=action_type,
        reason=data.get('reason', ''),
        internal_notes=data.get('internal_notes', ''),
        actor=request.user,
    )

    if action_type == 'approve':
        item.status = 'approved'
    elif action_type in ('reject', 'hide', 'delete'):
        item.status = 'rejected'
    item.assigned_to = request.user
    item.processed_at = timezone.now()
    item.save()

    AuditLog.objects.create(
        actor=request.user, action_type='moderation',
        action_name=f'content_{action_type}',
        target_type='content', target_id=str(item.object_id),
        details=f"Module: {item.source_module}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )
    return api_success({'status': item.status}, message=f"Content {action_type}ed.")


@require_http_methods(["GET"])
@api_auth_required
def content_history_view(request):
    """ Content action history."""
    err = _staff_required(request)
    if err:
        return err

    from django.db.models import Q
    actions = ContentAction.objects.all().select_related('actor', 'content_type')

    action_f = request.GET.get('action')
    if action_f and action_f != 'all':
        actions = actions.filter(action_type=action_f)
    actor_f = request.GET.get('actor')
    if actor_f:
        actions = actions.filter(actor__username=actor_f)

    actions = actions.order_by('-created_at')
    paginated = paginate_queryset(actions, request, default_per_page=25)

    data = [{
        'id': str(a.id),
        'action_type': a.action_type,
        'actor': a.actor.username if a.actor else None,
        'reason': a.reason,
        'is_reversed': a.is_reversed,
        'created_at': a.created_at.isoformat(),
    } for a in paginated['items']]

    return api_success({'actions': data, 'pagination': paginated['pagination']})


# =============================================================================
# SANCTIONS — USER OVERVIEW
# =============================================================================

@require_http_methods(["GET"])
@api_auth_required
def user_overview_view(request, username):
    """ User moderation overview (warnings, mutes, bans, appeals)."""
    err = _staff_required(request)
    if err:
        return err

    from django.db.models import Q
    user = get_object_or_404(User, username=username)
    now = timezone.now()

    active_warnings = list(UserWarning.objects.filter(
        user=user, expires_at__gt=now
    ).values('id', 'warning_type', 'severity', 'points', 'reason', 'expires_at'))

    active_mutes = list(UserMute.objects.filter(
        user=user, lifted_at__isnull=True
    ).filter(Q(is_permanent=True) | Q(expires_at__gt=now)).values(
        'id', 'scope', 'reason', 'is_permanent', 'expires_at'
    ))

    active_bans = list(UserBan.objects.filter(
        user=user, lifted_at__isnull=True
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).values(
        'id', 'ban_type', 'reason', 'expires_at', 'allow_appeal'
    ))

    pending_appeals = list(UserAppeal.objects.filter(
        user=user, status='pending'
    ).values('id', 'sanction_type', 'statement', 'created_at'))

    # Serialize datetime fields
    for w in active_warnings:
        w['id'] = str(w['id'])
        w['expires_at'] = w['expires_at'].isoformat() if w['expires_at'] else None
    for m in active_mutes:
        m['id'] = str(m['id'])
        m['expires_at'] = m['expires_at'].isoformat() if m['expires_at'] else None
    for b in active_bans:
        b['id'] = str(b['id'])
        b['expires_at'] = b['expires_at'].isoformat() if b['expires_at'] else None
    for a in pending_appeals:
        a['id'] = str(a['id'])
        a['created_at'] = a['created_at'].isoformat() if a['created_at'] else None

    AuditLog.objects.create(
        actor=request.user, action_type='view',
        action_name='api_user_overview_access', affected_user=user,
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )

    return api_success({
        'username': user.username,
        'active_warnings': active_warnings,
        'active_mutes': active_mutes,
        'active_bans': active_bans,
        'pending_appeals': pending_appeals,
    })


# =============================================================================
# WARNINGS
# =============================================================================

@require_http_methods(["POST"])
@api_auth_required
def issue_warning_view(request, username):
    """ Issue a warning. Body: {warning_type, severity, reason, evidence, expires_days}"""
    err = _staff_required(request)
    if err:
        return err

    user = get_object_or_404(User, username=username)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    warning_type = data.get('warning_type')
    severity = data.get('severity')
    reason = data.get('reason', '').strip()
    if not all([warning_type, severity, reason]):
        return api_error("warning_type, severity, and reason are required.", status=400)

    try:
        expires_days = max(1, int(data.get('expires_days', 30)))
    except (ValueError, TypeError):
        expires_days = 30

    points_map = {'low': 1, 'medium': 3, 'high': 5, 'critical': 10}
    points = points_map.get(severity, 1)

    warning = UserWarning.objects.create(
        user=user, issuer=request.user,
        warning_type=warning_type, severity=severity,
        points=points, reason=reason,
        evidence=data.get('evidence', ''),
        expires_at=timezone.now() + timedelta(days=expires_days),
    )

    AuditLog.objects.create(
        actor=request.user, action_type='moderation',
        action_name='warning_issued', affected_user=user,
        target_type='warning', target_id=str(warning.id),
        details=f"Type: {warning_type}, Severity: {severity}, Points: {points}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )
    return api_success({'id': str(warning.id), 'points': points}, message="Warning issued.", status=201)


# =============================================================================
# MUTES
# =============================================================================

@require_http_methods(["POST"])
@api_auth_required
def mute_user_view(request, username):
    """ Mute a user. Body: {scope, reason, duration_hours, is_permanent}"""
    err = _staff_required(request)
    if err:
        return err

    from django.db.models import Q
    user = get_object_or_404(User, username=username)

    existing = UserMute.objects.filter(
        user=user, lifted_at__isnull=True
    ).filter(Q(is_permanent=True) | Q(expires_at__gt=timezone.now())).first()
    if existing:
        return api_error(f"{username} is already muted.", status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    scope = data.get('scope')
    reason = data.get('reason', '').strip()
    if not scope or not reason:
        return api_error("scope and reason are required.", status=400)

    is_permanent = bool(data.get('is_permanent', False))
    expires_at = None
    if not is_permanent:
        try:
            hours = int(data.get('duration_hours', 24))
        except (ValueError, TypeError):
            hours = 24
        expires_at = timezone.now() + timedelta(hours=hours)

    mute = UserMute.objects.create(
        user=user, issuer=request.user,
        scope=scope, reason=reason,
        is_permanent=is_permanent, expires_at=expires_at,
    )

    AuditLog.objects.create(
        actor=request.user, action_type='moderation',
        action_name='user_muted', affected_user=user,
        target_type='mute', target_id=str(mute.id),
        details=f"Scope: {scope}, Permanent: {is_permanent}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )
    return api_success({'id': str(mute.id)}, message=f"{username} muted.", status=201)


@require_http_methods(["POST"])
@api_auth_required
def lift_mute_view(request, pk):
    """ Lift an active mute. Body: {lift_reason}"""
    err = _staff_required(request)
    if err:
        return err

    mute = get_object_or_404(UserMute, id=pk, lifted_at__isnull=True)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}

    mute.lifted_by = request.user
    mute.lifted_at = timezone.now()
    mute.lift_reason = data.get('lift_reason', 'Lifted by moderator')
    mute.save()

    AuditLog.objects.create(
        actor=request.user, action_type='moderation',
        action_name='mute_lifted', affected_user=mute.user,
        target_type='mute', target_id=str(mute.id),
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )
    return api_success({}, message=f"Mute lifted for {mute.user.username}.")


# =============================================================================
# BANS
# =============================================================================

@require_http_methods(["POST"])
@api_auth_required
def ban_user_view(request, username):
    """ Ban a user. Body: {ban_type, reason, evidence, duration_days, allow_appeal}"""
    err = _staff_required(request)
    if err:
        return err

    from django.db.models import Q
    user = get_object_or_404(User, username=username)

    existing = UserBan.objects.filter(
        user=user, lifted_at__isnull=True
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).first()
    if existing:
        return api_error(f"{username} is already banned.", status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    ban_type = data.get('ban_type')
    reason = data.get('reason', '').strip()
    if not ban_type or not reason:
        return api_error("ban_type and reason are required.", status=400)

    expires_at = None
    if ban_type == 'temporary':
        try:
            days = int(data.get('duration_days', 7))
        except (ValueError, TypeError):
            days = 7
        expires_at = timezone.now() + timedelta(days=days)

    ban = UserBan.objects.create(
        user=user, issuer=request.user,
        ban_type=ban_type, reason=reason,
        evidence=data.get('evidence', ''),
        expires_at=expires_at,
        allow_appeal=bool(data.get('allow_appeal', True)),
    )

    AuditLog.objects.create(
        actor=request.user, action_type='moderation',
        action_name='user_banned', affected_user=user,
        target_type='ban', target_id=str(ban.id),
        details=f"Type: {ban_type}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )
    return api_success({'id': str(ban.id)}, message=f"{username} banned.", status=201)


@require_http_methods(["POST"])
@api_auth_required
def lift_ban_view(request, pk):
    """ Lift an active ban. Body: {lift_reason}"""
    err = _staff_required(request)
    if err:
        return err

    ban = get_object_or_404(UserBan, id=pk, lifted_at__isnull=True)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}

    ban.lifted_by = request.user
    ban.lifted_at = timezone.now()
    ban.lift_reason = data.get('lift_reason', 'Lifted by moderator')
    ban.save()

    AuditLog.objects.create(
        actor=request.user, action_type='moderation',
        action_name='ban_lifted', affected_user=ban.user,
        target_type='ban', target_id=str(ban.id),
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )
    return api_success({}, message=f"Ban lifted for {ban.user.username}.")


# =============================================================================
# APPEALS
# =============================================================================

@require_http_methods(["GET"])
@api_auth_required
def appeals_view(request):
    """ List appeals."""
    err = _staff_required(request)
    if err:
        return err

    appeals = UserAppeal.objects.all().select_related('user', 'reviewer')
    status_f = request.GET.get('status')
    if status_f and status_f != 'all':
        appeals = appeals.filter(status=status_f)
    sanction_f = request.GET.get('sanction_type')
    if sanction_f and sanction_f != 'all':
        appeals = appeals.filter(sanction_type=sanction_f)

    appeals = appeals.order_by('status', '-created_at')
    paginated = paginate_queryset(appeals, request, default_per_page=20)

    data = [{
        'id': str(a.id),
        'user': a.user.username,
        'sanction_type': a.sanction_type,
        'status': a.status,
        'outcome': getattr(a, 'outcome', None),
        'created_at': a.created_at.isoformat(),
    } for a in paginated['items']]

    return api_success({'appeals': data, 'pagination': paginated['pagination']})


@require_http_methods(["GET", "POST"])
@api_auth_required
def appeal_review_view(request, pk):
    """ Get or review an appeal. POST body: {outcome, decision_notes}"""
    err = _staff_required(request)
    if err:
        return err

    appeal = get_object_or_404(UserAppeal, id=pk)

    if request.method == "GET":
        return api_success({
            'id': str(appeal.id),
            'user': appeal.user.username,
            'sanction_type': appeal.sanction_type,
            'statement': appeal.statement,
            'status': appeal.status,
            'outcome': getattr(appeal, 'outcome', None),
            'decision_notes': getattr(appeal, 'decision_notes', ''),
            'created_at': appeal.created_at.isoformat(),
        })

    # POST — review
    if appeal.status != 'pending':
        return api_error("Appeal has already been reviewed.", status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    outcome = data.get('outcome')
    if not outcome:
        return api_error("outcome is required.", status=400)

    appeal.status = 'reviewed'
    appeal.reviewer = request.user
    appeal.outcome = outcome
    appeal.decision_notes = data.get('decision_notes', '')
    appeal.reviewed_at = timezone.now()
    appeal.save()

    AuditLog.objects.create(
        actor=request.user, action_type='moderation',
        action_name='appeal_reviewed', affected_user=appeal.user,
        target_type='appeal', target_id=str(appeal.id),
        details=f"Outcome: {outcome}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )
    return api_success({'outcome': outcome}, message=f"Appeal {outcome}.")


# =============================================================================
# AUDIT LOG
# =============================================================================

@require_http_methods(["GET"])
@api_auth_required
def audit_log_view(request):
    """ Paginated audit log with filters."""
    err = _staff_required(request)
    if err:
        return err

    from django.db.models import Q
    logs = AuditLog.objects.all().select_related('actor', 'affected_user')

    action_type_f = request.GET.get('action_type')
    if action_type_f and action_type_f != 'all':
        logs = logs.filter(action_type=action_type_f)
    actor_f = request.GET.get('actor')
    if actor_f:
        logs = logs.filter(actor__username=actor_f)
    result_f = request.GET.get('result')
    if result_f and result_f != 'all':
        logs = logs.filter(result=result_f)
    q = request.GET.get('q')
    if q:
        logs = logs.filter(
            Q(action_name__icontains=q) | Q(details__icontains=q) |
            Q(affected_user__username__icontains=q)
        )

    logs = logs.order_by('-created_at')
    paginated = paginate_queryset(logs, request, default_per_page=50)

    data = [{
        'id': str(l.id),
        'actor': l.actor.username if l.actor else None,
        'action_type': l.action_type,
        'action_name': l.action_name,
        'affected_user': l.affected_user.username if l.affected_user else None,
        'target_type': l.target_type,
        'target_id': l.target_id,
        'details': l.details,
        'result': l.result,
        'ip_address': l.ip_address,
        'created_at': l.created_at.isoformat(),
    } for l in paginated['items']]

    return api_success({'logs': data, 'pagination': paginated['pagination']})


# =============================================================================
# STAFF
# =============================================================================

@require_http_methods(["GET"])
@api_auth_required
def staff_list_view(request):
    """ List active staff assignments."""
    err = _staff_required(request)
    if err:
        return err

    assignments = StaffAssignment.objects.filter(
        is_active=True
    ).select_related('user', 'role', 'assigned_by')

    data = [{
        'user': a.user.username,
        'role': a.role.name if a.role else None,
        'module_access': a.module_access,
        'daily_action_limit': a.daily_action_limit,
        'start_date': a.start_date.isoformat() if a.start_date else None,
    } for a in assignments]

    return api_success({'staff': data})


@require_http_methods(["POST"])
@api_auth_required
def staff_assign_role_view(request, user_id):
    """ Assign/update staff role. Body: {role_id, module_access, daily_action_limit, notes}"""
    err = _staff_required(request)
    if err:
        return err

    user = get_object_or_404(User, id=user_id, is_staff=True)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    role_id = data.get('role_id')
    if not role_id:
        return api_error("role_id is required.", status=400)

    role = get_object_or_404(StaffRole, id=role_id)

    try:
        daily_limit = int(data.get('daily_action_limit', 100))
    except (ValueError, TypeError):
        daily_limit = 100

    existing = StaffAssignment.objects.filter(user=user, is_active=True).first()
    if existing:
        existing.role = role
        existing.module_access = data.get('module_access', existing.module_access)
        existing.daily_action_limit = daily_limit
        existing.notes = data.get('notes', existing.notes)
        existing.save()
        action = 'updated'
    else:
        StaffAssignment.objects.create(
            user=user, role=role, assigned_by=request.user,
            module_access=data.get('module_access', ''),
            daily_action_limit=daily_limit,
            notes=data.get('notes', ''),
            start_date=timezone.now().date(),
        )
        action = 'assigned'

    AuditLog.objects.create(
        actor=request.user, action_type='staff',
        action_name=f'staff_role_{action}', affected_user=user,
        details=f"Role: {role.name}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success',
    )
    return api_success({'action': action, 'role': role.name})


# =============================================================================
# AUTO-MOD RULES
# =============================================================================

@require_http_methods(["GET"])
@api_auth_required
def automod_rules_view(request):
    """ List auto-mod rules."""
    err = _staff_required(request)
    if err:
        return err

    rules = AutoModRule.objects.all().select_related('created_by')
    trigger_f = request.GET.get('trigger')
    if trigger_f and trigger_f != 'all':
        rules = rules.filter(trigger_type=trigger_f)
    active_f = request.GET.get('active')
    if active_f == 'true':
        rules = rules.filter(is_active=True)
    elif active_f == 'false':
        rules = rules.filter(is_active=False)

    rules = rules.order_by('-is_active', 'priority', 'name')
    data = [{
        'id': str(r.id), 'name': r.name, 'trigger_type': r.trigger_type,
        'trigger_value': r.trigger_value, 'action': r.action,
        'scope': r.scope, 'priority': r.priority, 'is_active': r.is_active,
    } for r in rules]

    return api_success({'rules': data})


@require_http_methods(["POST"])
@api_auth_required
def automod_rule_create_view(request):
    """ Create auto-mod rule."""
    err = _staff_required(request)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    required = ('name', 'trigger_type', 'trigger_value', 'action')
    if not all(data.get(f, '') for f in required):
        return api_error(f"Required fields: {', '.join(required)}", status=400)

    rule = AutoModRule.objects.create(
        name=data['name'], description=data.get('description', ''),
        trigger_type=data['trigger_type'], trigger_value=data['trigger_value'],
        action=data['action'], action_params=data.get('action_params', ''),
        scope=data.get('scope', 'all'),
        priority=int(data.get('priority', 1)),
        is_active=bool(data.get('is_active', True)),
        created_by=request.user,
    )
    return api_success({'id': str(rule.id), 'name': rule.name}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_auth_required
def automod_rule_detail_view(request, pk):
    """ Get, update, or delete an auto-mod rule."""
    err = _staff_required(request)
    if err:
        return err

    rule = get_object_or_404(AutoModRule, id=pk)

    if request.method == "GET":
        return api_success({
            'id': str(rule.id), 'name': rule.name, 'description': rule.description,
            'trigger_type': rule.trigger_type, 'trigger_value': rule.trigger_value,
            'action': rule.action, 'action_params': rule.action_params,
            'scope': rule.scope, 'priority': rule.priority, 'is_active': rule.is_active,
        })

    if request.method == "DELETE":
        rule.delete()
        return api_success({}, message="Rule deleted.")

    # PATCH
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    for field in ('name', 'description', 'trigger_type', 'trigger_value',
                  'action', 'action_params', 'scope'):
        if field in data:
            setattr(rule, field, str(data[field]))
    if 'priority' in data:
        rule.priority = int(data['priority'])
    if 'is_active' in data:
        rule.is_active = bool(data['is_active'])
    rule.save()
    return api_success({'id': str(rule.id)}, message="Rule updated.")


# =============================================================================
# AUTO-MOD LOGS
# =============================================================================

@require_http_methods(["GET"])
@api_auth_required
def automod_logs_view(request):
    """ Auto-mod log entries."""
    err = _staff_required(request)
    if err:
        return err

    logs = AutoModLog.objects.all().select_related('rule', 'user', 'reviewed_by')

    rule_f = request.GET.get('rule')
    if rule_f and rule_f != 'all':
        logs = logs.filter(rule__name=rule_f)
    action_f = request.GET.get('action')
    if action_f and action_f != 'all':
        logs = logs.filter(action_taken=action_f)

    logs = logs.order_by('-created_at')
    paginated = paginate_queryset(logs, request, default_per_page=30)

    data = [{
        'id': str(l.id),
        'rule': l.rule.name if l.rule else None,
        'user': l.user.username if l.user else None,
        'action_taken': l.action_taken,
        'review_status': l.review_status,
        'reviewed_by': l.reviewed_by.username if l.reviewed_by else None,
        'created_at': l.created_at.isoformat(),
    } for l in paginated['items']]

    return api_success({'logs': data, 'pagination': paginated['pagination']})
