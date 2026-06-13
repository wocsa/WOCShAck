"""
Content moderation views.
Queue management, content review, and content action management.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone

from .models import (
    ModerationQueue, ContentAction, AuditLog
)


# =============================================================================
# CONTENT QUEUE MANAGEMENT
# =============================================================================

@login_required
@require_GET
def content_queue(request):
    """
    List moderation queue items with filtering.
    Shows content awaiting review with priority and module filters.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    queue_items = ModerationQueue.objects.all().select_related(
        'assigned_to', 'content_type'
    )

    # Filters
    status_filter = request.GET.get('status')
    if status_filter and status_filter != 'all':
        queue_items = queue_items.filter(status=status_filter)

    priority_filter = request.GET.get('priority')
    if priority_filter and priority_filter != 'all':
        queue_items = queue_items.filter(priority=priority_filter)

    module_filter = request.GET.get('module')
    if module_filter and module_filter != 'all':
        queue_items = queue_items.filter(source_module=module_filter)

    assignment_filter = request.GET.get('assignment')
    if assignment_filter == 'unassigned':
        queue_items = queue_items.filter(assigned_to__isnull=True)
    elif assignment_filter == 'mine':
        queue_items = queue_items.filter(assigned_to=request.user)

    auto_flag_filter = request.GET.get('auto_flagged')
    if auto_flag_filter == 'true':
        queue_items = queue_items.filter(auto_flagged=True)
    elif auto_flag_filter == 'false':
        queue_items = queue_items.filter(auto_flagged=False)

    # Ordering - prioritize critical/high items and auto-flagged
    queue_items = queue_items.order_by(
        'status',
        '-priority',
        '-auto_flagged',
        'created_at'
    )

    # Pagination
    paginator = Paginator(queue_items, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Filter choices
    status_choices = ModerationQueue.STATUS_CHOICES
    priority_choices = ModerationQueue.PRIORITY_CHOICES
    module_choices = ModerationQueue.SOURCE_MODULE_CHOICES

    context = {
        'page_obj': page_obj,
        'status_choices': status_choices,
        'priority_choices': priority_choices,
        'module_choices': module_choices,
        'current_filters': {
            'status': status_filter,
            'priority': priority_filter,
            'module': module_filter,
            'assignment': assignment_filter,
            'auto_flagged': auto_flag_filter,
        }
    }

    return render(request, 'admin_panel/content/queue.html', context)


@login_required
@require_GET
def content_review(request, pk):
    """
    Review individual content item.
    Shows content details and allows moderator to take actions.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    queue_item = get_object_or_404(ModerationQueue, id=pk)

    # Get previous actions on this content
    previous_actions = ContentAction.objects.filter(
        content_type=queue_item.content_type,
        object_id=queue_item.object_id
    ).select_related('actor').order_by('-created_at')

    # Log content review access
    AuditLog.objects.create(
        actor=request.user,
        action_type='view',
        action_name='content_review_access',
        target_type='moderation_queue',
        target_id=str(queue_item.id),
        details=f"Module: {queue_item.source_module}, Auto-flagged: {queue_item.auto_flagged}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    context = {
        'queue_item': queue_item,
        'previous_actions': previous_actions,
        'action_choices': ContentAction.ACTION_TYPE_CHOICES,
    }

    return render(request, 'admin_panel/content/review.html', context)


@login_required
@require_POST
def content_action(request, pk):
    """
    Take moderation action on content.
    Processes approve/reject/hide/delete actions with audit logging.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    queue_item = get_object_or_404(ModerationQueue, id=pk)

    action_type = request.POST.get('action_type')
    reason = request.POST.get('reason', '')
    internal_notes = request.POST.get('internal_notes', '')

    if not action_type:
        messages.error(request, "Action type is required.")
        return redirect('admin_panel:content_review', pk=pk)

    if action_type not in [choice[0] for choice in ContentAction.ACTION_TYPE_CHOICES]:
        messages.error(request, "Invalid action type.")
        return redirect('admin_panel:content_review', pk=pk)

    # Create content action record
    content_action = ContentAction.objects.create(
        content_type=queue_item.content_type,
        object_id=queue_item.object_id,
        action_type=action_type,
        reason=reason,
        internal_notes=internal_notes,
        actor=request.user
    )

    # Apply the action to the actual target object
    target = content_action.content_object
    if target is not None:
        from Forum.models import Post, Topic

        if action_type == 'approve':
            if isinstance(target, Post):
                target.is_hidden = False
                target.hidden_reason = ''
                target.hidden_by = None
                target.save(update_fields=['is_hidden', 'hidden_reason', 'hidden_by'])
            elif isinstance(target, Topic):
                target.is_locked = False
                target.save(update_fields=['is_locked'])

        elif action_type in ('reject', 'hide'):
            if isinstance(target, Post):
                target.is_hidden = True
                target.hidden_reason = reason[:200] if reason else ''
                target.hidden_by = request.user
                target.save(update_fields=['is_hidden', 'hidden_reason', 'hidden_by'])

        elif action_type == 'delete':
            # Snapshot content before deletion
            if isinstance(target, Post):
                content_action.original_content = target.content
            elif isinstance(target, Topic):
                content_action.original_content = target.title
            content_action.save(update_fields=['original_content'])
            target.delete()

        elif action_type == 'lock':
            if isinstance(target, Topic):
                target.is_locked = True
                target.save(update_fields=['is_locked'])

    # Update queue item status
    if action_type in ['approve']:
        queue_item.status = 'approved'
    elif action_type in ['reject', 'hide', 'delete']:
        queue_item.status = 'rejected'
    
    queue_item.assigned_to = request.user
    queue_item.processed_at = timezone.now()
    queue_item.save()

    # Create audit log
    AuditLog.objects.create(
        actor=request.user,
        action_type='moderation',
        action_name=f'content_{action_type}',
        target_type='content',
        target_id=str(queue_item.object_id),
        details=f"Module: {queue_item.source_module}, Reason: {reason}",
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        result='success'
    )

    messages.success(request, f"Content {action_type}ed successfully.")
    
    # Redirect to next item in queue or back to queue list
    next_item = ModerationQueue.objects.filter(
        status='pending',
        priority__in=['critical', 'high', 'medium']
    ).exclude(id=queue_item.id).first()
    
    if next_item:
        return redirect('admin_panel:content_review', pk=next_item.id)
    else:
        return redirect('admin_panel:content_queue')


# =============================================================================
# CONTENT ACTION HISTORY
# =============================================================================

@login_required
@require_GET
def content_action_history(request):
    """
    View content action history with filtering.
    Shows all moderation actions taken on content across modules.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    actions = ContentAction.objects.all().select_related('actor', 'content_type')

    # Filters
    action_filter = request.GET.get('action')
    if action_filter and action_filter != 'all':
        actions = actions.filter(action_type=action_filter)

    actor_filter = request.GET.get('actor')
    if actor_filter and actor_filter != 'all':
        actions = actions.filter(actor__username=actor_filter)

    reversed_filter = request.GET.get('reversed')
    if reversed_filter == 'true':
        actions = actions.filter(is_reversed=True)
    elif reversed_filter == 'false':
        actions = actions.filter(is_reversed=False)

    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        try:
            actions = actions.filter(created_at__gte=date_from)
        except:
            messages.warning(request, "Invalid date format for 'from' date.")

    if date_to:
        try:
            actions = actions.filter(created_at__lte=date_to)
        except:
            messages.warning(request, "Invalid date format for 'to' date.")

    # Search by reason or notes
    search_query = request.GET.get('search')
    if search_query:
        actions = actions.filter(
            Q(reason__icontains=search_query) |
            Q(internal_notes__icontains=search_query)
        )

    # Ordering
    actions = actions.order_by('-created_at')

    # Pagination
    paginator = Paginator(actions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get unique actors for filter
    actors = ContentAction.objects.values_list(
        'actor__username', flat=True
    ).distinct().order_by('actor__username')

    context = {
        'page_obj': page_obj,
        'action_choices': ContentAction.ACTION_TYPE_CHOICES,
        'actors': actors,
        'current_filters': {
            'action': action_filter,
            'actor': actor_filter,
            'reversed': reversed_filter,
            'date_from': date_from,
            'date_to': date_to,
            'search': search_query,
        }
    }

    return render(request, 'admin_panel/content/history.html', context)