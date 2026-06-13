"""
Chatbot module moderation views for staff management of chatbot responses.

All views follow secure coding practices with proper
authentication, authorization, input validation, and audit logging.
"""
import logging
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Avg, Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.utils.html import escape

from .models import (
    ChatMessage, KnowledgeBase,
    ChatbotResponseFlag, ChatbotResponseEdit,
    ChatbotKnowledgeModeration, ChatbotModerationAction,
    ChatbotQualityScore,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DECORATORS
# =============================================================================

def staff_required(view_func):
    """
    Decorator to require staff status.
    Returns 403 for non-staff users to prevent information leakage.
    """
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('chatbot:index')
        return view_func(request, *args, **kwargs)
    return login_required(_wrapped_view)


def get_client_ip(request):
    """
    Get client IP address securely.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# =============================================================================
# MODERATION DASHBOARD
# =============================================================================

@staff_required
def moderation_dashboard(request):
    """
    Main moderation dashboard for chatbot management.
    Shows overview statistics, pending flags, and recent actions.
    """
    # Statistics
    pending_flags_count = ChatbotResponseFlag.objects.filter(status='pending').count()
    under_review_count = ChatbotResponseFlag.objects.filter(status='under_review').count()
    resolved_today = ChatbotResponseFlag.objects.filter(
        status__in=['resolved', 'dismissed'],
        resolved_at__date=timezone.now().date()
    ).count()
    total_messages = ChatMessage.objects.count()
    total_kb_entries = KnowledgeBase.objects.filter(is_active=True).count()
    pending_edits = ChatbotResponseEdit.objects.filter(approval_status='pending').count()

    # Pending flags (latest 10)
    pending_flags = ChatbotResponseFlag.objects.filter(
        status='pending'
    ).select_related(
        'chat_message', 'flagged_by', 'assigned_to'
    ).order_by('-severity', '-created_at')[:10]

    # Recent moderation actions (latest 10)
    recent_actions = ChatbotModerationAction.objects.select_related(
        'actor'
    ).order_by('-created_at')[:10]

    # Recent edits pending approval
    pending_edit_list = ChatbotResponseEdit.objects.filter(
        approval_status='pending'
    ).select_related(
        'chat_message', 'edited_by'
    ).order_by('-created_at')[:5]

    context = {
        'pending_flags_count': pending_flags_count,
        'under_review_count': under_review_count,
        'resolved_today': resolved_today,
        'total_messages': total_messages,
        'total_kb_entries': total_kb_entries,
        'pending_edits': pending_edits,
        'pending_flags': pending_flags,
        'recent_actions': recent_actions,
        'pending_edit_list': pending_edit_list,
    }

    return render(request, 'chatbot/admin/dashboard.html', context)


# =============================================================================
# FLAG MANAGEMENT VIEWS
# =============================================================================

@staff_required
def flag_queue(request):
    """
    View all flagged chatbot responses with filtering.
    """
    status_filter = request.GET.get('status', 'pending')
    severity_filter = request.GET.get('severity', '')
    reason_filter = request.GET.get('reason', '')

    flags = ChatbotResponseFlag.objects.select_related(
        'chat_message', 'flagged_by', 'assigned_to', 'resolved_by'
    )

    valid_statuses = [s[0] for s in ChatbotResponseFlag.STATUS_CHOICES]
    if status_filter and status_filter in valid_statuses:
        flags = flags.filter(status=status_filter)

    valid_severities = [s[0] for s in ChatbotResponseFlag.SEVERITY_CHOICES]
    if severity_filter and severity_filter in valid_severities:
        flags = flags.filter(severity=severity_filter)

    valid_reasons = [r[0] for r in ChatbotResponseFlag.FLAG_REASONS]
    if reason_filter and reason_filter in valid_reasons:
        flags = flags.filter(reason=reason_filter)

    flags = flags.order_by('-severity', '-created_at')

    paginator = Paginator(flags, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'flags': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'severity_filter': severity_filter,
        'reason_filter': reason_filter,
        'status_choices': ChatbotResponseFlag.STATUS_CHOICES,
        'severity_choices': ChatbotResponseFlag.SEVERITY_CHOICES,
        'reason_choices': ChatbotResponseFlag.FLAG_REASONS,
    }

    return render(request, 'chatbot/admin/flag_queue.html', context)


@staff_required
def flag_detail(request, flag_id):
    """
    View and manage a specific flagged response.
    """
    flag = get_object_or_404(
        ChatbotResponseFlag.objects.select_related(
            'chat_message', 'chat_message__user',
            'flagged_by', 'assigned_to', 'resolved_by'
        ),
        id=flag_id
    )

    # Get related edits for this message
    related_edits = ChatbotResponseEdit.objects.filter(
        chat_message=flag.chat_message
    ).select_related('edited_by', 'reviewed_by').order_by('-created_at')

    # Get quality scores for this message
    quality_scores = ChatbotQualityScore.objects.filter(
        chat_message=flag.chat_message
    ).select_related('scored_by').order_by('-created_at')

    context = {
        'flag': flag,
        'related_edits': related_edits,
        'quality_scores': quality_scores,
    }

    return render(request, 'chatbot/admin/flag_detail.html', context)


@staff_required
@require_POST
def flag_assign(request, flag_id):
    """
    Assign a flag to the current moderator.
    """
    flag = get_object_or_404(ChatbotResponseFlag, id=flag_id)

    flag.assign(request.user)

    ChatbotModerationAction.log_action(
        actor=request.user,
        action_type='flag_assigned',
        description=f'Assigned flag #{str(flag_id)[:8]} to self',
        target_flag=flag,
        target_message=flag.chat_message,
        ip_address=get_client_ip(request),
    )

    messages.success(request, 'Flag assigned to you for review.')
    return redirect('chatbot:flag_detail', flag_id=flag_id)


@staff_required
@require_POST
def flag_resolve(request, flag_id):
    """
    Resolve or dismiss a flagged response.
    """
    flag = get_object_or_404(ChatbotResponseFlag, id=flag_id)

    action = request.POST.get('action', 'resolve')
    notes = request.POST.get('resolution_notes', '').strip()

    if not notes:
        messages.error(request, 'Resolution notes are required.')
        return redirect('chatbot:flag_detail', flag_id=flag_id)

    if len(notes) > 2000:
        messages.error(request, 'Resolution notes must be under 2000 characters.')
        return redirect('chatbot:flag_detail', flag_id=flag_id)

    dismiss = (action == 'dismiss')

    with transaction.atomic():
        flag.resolve(
            resolved_by=request.user,
            notes=notes,
            dismiss=dismiss,
        )

        action_type = 'flag_dismissed' if dismiss else 'flag_resolved'
        ChatbotModerationAction.log_action(
            actor=request.user,
            action_type=action_type,
            description=f'{"Dismissed" if dismiss else "Resolved"} flag #{str(flag_id)[:8]}: {notes[:100]}',
            target_flag=flag,
            target_message=flag.chat_message,
            ip_address=get_client_ip(request),
        )

    status_label = 'dismissed' if dismiss else 'resolved'
    messages.success(request, f'Flag has been {status_label} successfully.')
    return redirect('chatbot:flag_queue')


# =============================================================================
# RESPONSE EDITING VIEWS
# =============================================================================

@staff_required
def edit_response(request, message_id):
    """
    Edit a chatbot response with full audit trail.
    """
    chat_message = get_object_or_404(
        ChatMessage.objects.select_related('user'),
        id=message_id
    )

    if request.method == 'POST':
        edited_response = request.POST.get('edited_response', '').strip()
        edit_reason = request.POST.get('edit_reason', '').strip()
        flag_id = request.POST.get('related_flag', '')

        errors = []
        if not edited_response:
            errors.append('Edited response cannot be empty.')
        if not edit_reason or len(edit_reason) < 5:
            errors.append('Edit reason must be at least 5 characters.')
        if len(edited_response) > 10000:
            errors.append('Edited response is too long (max 10000 characters).')

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('chatbot:edit_response', message_id=message_id)

        related_flag = None
        if flag_id:
            try:
                related_flag = ChatbotResponseFlag.objects.get(id=flag_id)
            except (ChatbotResponseFlag.DoesNotExist, ValueError):
                pass

        with transaction.atomic():
            edit = ChatbotResponseEdit.objects.create(
                chat_message=chat_message,
                original_response=chat_message.response,
                edited_response=edited_response,
                edit_reason=edit_reason,
                edited_by=request.user,
                related_flag=related_flag,
            )

            ChatbotModerationAction.log_action(
                actor=request.user,
                action_type='response_edited',
                description=f'Submitted edit for message #{message_id}: {edit_reason[:100]}',
                target_message=chat_message,
                ip_address=get_client_ip(request),
                metadata={'edit_id': str(edit.id)},
            )

        messages.success(request, 'Edit submitted for review.')
        return redirect('chatbot:admin_dashboard')

    # Get related flags for this message
    related_flags = ChatbotResponseFlag.objects.filter(
        chat_message=chat_message
    ).order_by('-created_at')

    context = {
        'chat_message': chat_message,
        'related_flags': related_flags,
    }

    return render(request, 'chatbot/admin/edit_response.html', context)


@staff_required
def edit_queue(request):
    """
    View pending response edits for approval.
    """
    status_filter = request.GET.get('status', 'pending')

    valid_statuses = [s[0] for s in ChatbotResponseEdit.APPROVAL_CHOICES]
    if status_filter not in valid_statuses:
        status_filter = 'pending'

    edits = ChatbotResponseEdit.objects.filter(
        approval_status=status_filter
    ).select_related(
        'chat_message', 'edited_by', 'reviewed_by'
    ).order_by('-created_at')

    paginator = Paginator(edits, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'edits': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'approval_choices': ChatbotResponseEdit.APPROVAL_CHOICES,
    }

    return render(request, 'chatbot/admin/edit_queue.html', context)


@staff_required
@require_POST
def approve_edit(request, edit_id):
    """
    Approve a pending response edit.
    The edit is applied to the actual chat message upon approval.
    """
    edit = get_object_or_404(ChatbotResponseEdit, id=edit_id)

    if edit.approval_status != 'pending':
        messages.warning(request, 'This edit has already been reviewed.')
        return redirect('chatbot:edit_queue')

    if edit.edited_by == request.user and not request.user.is_superuser:
        messages.error(request, 'You cannot approve your own edits.')
        return redirect('chatbot:edit_queue')

    review_notes = request.POST.get('review_notes', '').strip()

    with transaction.atomic():
        edit.approve(reviewer=request.user, notes=review_notes)

        ChatbotModerationAction.log_action(
            actor=request.user,
            action_type='edit_approved',
            description=f'Approved edit #{str(edit_id)[:8]} on message #{edit.chat_message_id}',
            target_message=edit.chat_message,
            ip_address=get_client_ip(request),
            metadata={'edit_id': str(edit.id)},
        )

    messages.success(request, 'Edit approved and applied to the response.')
    return redirect('chatbot:edit_queue')


@staff_required
@require_POST
def reject_edit(request, edit_id):
    """
    Reject a pending response edit.
    """
    edit = get_object_or_404(ChatbotResponseEdit, id=edit_id)

    if edit.approval_status != 'pending':
        messages.warning(request, 'This edit has already been reviewed.')
        return redirect('chatbot:edit_queue')

    review_notes = request.POST.get('review_notes', '').strip()
    if not review_notes:
        messages.error(request, 'Please provide a reason for rejection.')
        return redirect('chatbot:edit_queue')

    with transaction.atomic():
        edit.reject(reviewer=request.user, notes=review_notes)

        ChatbotModerationAction.log_action(
            actor=request.user,
            action_type='edit_rejected',
            description=f'Rejected edit #{str(edit_id)[:8]}: {review_notes[:100]}',
            target_message=edit.chat_message,
            ip_address=get_client_ip(request),
            metadata={'edit_id': str(edit.id)},
        )

    messages.success(request, 'Edit has been rejected.')
    return redirect('chatbot:edit_queue')


# =============================================================================
# KNOWLEDGE BASE MODERATION VIEWS
# =============================================================================

@staff_required
def knowledge_base_moderation(request):
    """
    Knowledge base management interface for staff.
    """
    category_filter = request.GET.get('category', '')
    active_filter = request.GET.get('active', '')
    search_query = request.GET.get('q', '').strip()

    entries = KnowledgeBase.objects.all()

    if category_filter:
        entries = entries.filter(category=category_filter)

    if active_filter == 'true':
        entries = entries.filter(is_active=True)
    elif active_filter == 'false':
        entries = entries.filter(is_active=False)

    if search_query:
        entries = entries.filter(
            Q(question__icontains=search_query) |
            Q(answer__icontains=search_query) |
            Q(keywords__icontains=search_query)
        )

    entries = entries.order_by('-updated_at')

    # Get unique categories for filter
    categories = KnowledgeBase.objects.values_list(
        'category', flat=True
    ).distinct().order_by('category')

    paginator = Paginator(entries, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Recent moderation history
    recent_kb_actions = ChatbotKnowledgeModeration.objects.select_related(
        'moderator', 'knowledge_entry'
    ).order_by('-created_at')[:10]

    context = {
        'entries': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'category_filter': category_filter,
        'active_filter': active_filter,
        'search_query': search_query,
        'recent_kb_actions': recent_kb_actions,
    }

    return render(request, 'chatbot/admin/knowledge_base.html', context)


@staff_required
@require_POST
def create_kb_entry(request):
    """
    Create a new knowledge base entry with full audit trail.
    Validates all inputs, creates the entry, logs the action, and reloads the RAG engine.
    """
    question = request.POST.get('question', '').strip()
    answer = request.POST.get('answer', '').strip()
    category = request.POST.get('category', '').strip()
    keywords = request.POST.get('keywords', '').strip()

    errors = []
    if not question or len(question) < 10:
        errors.append('Question must be at least 10 characters long.')
    if len(question) > 1000:
        errors.append('Question must be under 1000 characters.')
    if not answer or len(answer) < 10:
        errors.append('Answer must be at least 10 characters long.')
    if len(answer) > 5000:
        errors.append('Answer must be under 5000 characters.')
    if not category:
        errors.append('Category is required.')
    if len(category) > 100:
        errors.append('Category must be under 100 characters.')
    if category and not re.match(r'^[a-zA-Z0-9_\- ]+$', category):
        errors.append('Category may only contain letters, numbers, spaces, hyphens, and underscores.')
    if not keywords:
        errors.append('At least one keyword is required.')
    if len(keywords) > 1000:
        errors.append('Keywords must be under 1000 characters.')

    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect('chatbot:knowledge_base_admin')

    with transaction.atomic():
        entry = KnowledgeBase.objects.create(
            question=question,
            answer=answer,
            category=category.lower(),
            keywords=keywords,
            is_active=True,
        )

        ChatbotKnowledgeModeration.objects.create(
            knowledge_entry=entry,
            action='created',
            moderator=request.user,
            reason='New knowledge base entry created via moderation interface',
            new_question=question,
            new_answer=answer,
            new_category=category.lower(),
        )

        ChatbotModerationAction.log_action(
            actor=request.user,
            action_type='kb_entry_created',
            description=f'Created knowledge entry #{entry.id}: {escape(question[:80])}',
            target_knowledge_entry=entry,
            ip_address=get_client_ip(request),
            metadata={
                'category': category.lower(),
                'keywords': keywords,
            },
        )

    # Reload RAG engine to include the new entry
    try:
        from .rag_engine import get_rag_engine
        engine = get_rag_engine()
        engine.reload_knowledge_base()
    except Exception as e:
        logger.error(f"Failed to reload RAG engine after creating KB entry: {e}")

    messages.success(request, 'Knowledge base entry created successfully.')
    return redirect('chatbot:knowledge_base_admin')


@staff_required
@require_POST
def toggle_kb_entry(request, entry_id):
    """
    Toggle a knowledge base entry active/inactive with logging.
    """
    entry = get_object_or_404(KnowledgeBase, id=entry_id)

    previous_state = entry.is_active
    entry.is_active = not entry.is_active
    entry.save(update_fields=['is_active', 'updated_at'])

    action = 'activated' if entry.is_active else 'deactivated'

    with transaction.atomic():
        ChatbotKnowledgeModeration.objects.create(
            knowledge_entry=entry,
            action=action,
            moderator=request.user,
            reason=f'Toggled entry to {action}',
        )

        ChatbotModerationAction.log_action(
            actor=request.user,
            action_type='kb_entry_toggled',
            description=f'Knowledge entry #{entry_id} {action}',
            target_knowledge_entry=entry,
            ip_address=get_client_ip(request),
        )

    # Reload RAG engine to apply changes
    try:
        from .rag_engine import get_rag_engine
        engine = get_rag_engine()
        engine.reload_knowledge_base()
    except Exception as e:
        logger.error(f"Failed to reload RAG engine: {e}")

    messages.success(request, f'Knowledge entry {action} successfully.')
    return redirect('chatbot:knowledge_base_admin')


# =============================================================================
# QUALITY SCORING VIEWS
# =============================================================================

@staff_required
def score_response(request, message_id):
    """
    Score a chatbot response for quality tracking.
    """
    chat_message = get_object_or_404(
        ChatMessage.objects.select_related('user'),
        id=message_id
    )

    # Check for existing score by this user
    existing_score = ChatbotQualityScore.objects.filter(
        chat_message=chat_message,
        scored_by=request.user
    ).first()

    if request.method == 'POST':
        try:
            accuracy = int(request.POST.get('accuracy_score', 3))
            helpfulness = int(request.POST.get('helpfulness_score', 3))
            tone = int(request.POST.get('tone_score', 3))
            overall = int(request.POST.get('overall_score', 3))
            notes = request.POST.get('notes', '').strip()

            for score in [accuracy, helpfulness, tone, overall]:
                if score < 1 or score > 5:
                    messages.error(request, 'Scores must be between 1 and 5.')
                    return redirect('chatbot:score_response', message_id=message_id)

        except (ValueError, TypeError):
            messages.error(request, 'Invalid score values.')
            return redirect('chatbot:score_response', message_id=message_id)

        with transaction.atomic():
            if existing_score:
                existing_score.accuracy_score = accuracy
                existing_score.helpfulness_score = helpfulness
                existing_score.tone_score = tone
                existing_score.overall_score = overall
                existing_score.notes = notes[:1000]
                existing_score.save()
            else:
                ChatbotQualityScore.objects.create(
                    chat_message=chat_message,
                    accuracy_score=accuracy,
                    helpfulness_score=helpfulness,
                    tone_score=tone,
                    overall_score=overall,
                    scored_by=request.user,
                    notes=notes[:1000],
                )

            ChatbotModerationAction.log_action(
                actor=request.user,
                action_type='quality_scored',
                description=f'Quality score {overall}/5 for message #{message_id}',
                target_message=chat_message,
                ip_address=get_client_ip(request),
                metadata={
                    'accuracy': accuracy,
                    'helpfulness': helpfulness,
                    'tone': tone,
                    'overall': overall,
                },
            )

        messages.success(request, 'Quality score recorded successfully.')
        return redirect('chatbot:admin_dashboard')

    context = {
        'chat_message': chat_message,
        'existing_score': existing_score,
    }

    return render(request, 'chatbot/admin/score_response.html', context)


# =============================================================================
# MODERATION STATISTICS / ANALYTICS
# =============================================================================

@staff_required
def moderation_statistics(request):
    """
    Chatbot moderation statistics and analytics.
    """
    # Flag statistics
    total_flags = ChatbotResponseFlag.objects.count()
    pending_flags = ChatbotResponseFlag.objects.filter(status='pending').count()
    resolved_flags = ChatbotResponseFlag.objects.filter(status='resolved').count()
    dismissed_flags = ChatbotResponseFlag.objects.filter(status='dismissed').count()

    # Flags by reason
    flags_by_reason = ChatbotResponseFlag.objects.values(
        'reason'
    ).annotate(count=Count('id')).order_by('-count')

    # Flags by severity
    flags_by_severity = ChatbotResponseFlag.objects.values(
        'severity'
    ).annotate(count=Count('id')).order_by('-count')

    # Quality score averages
    avg_quality = ChatbotQualityScore.objects.aggregate(
        avg_accuracy=Avg('accuracy_score'),
        avg_helpfulness=Avg('helpfulness_score'),
        avg_tone=Avg('tone_score'),
        avg_overall=Avg('overall_score'),
    )

    # Edit statistics
    total_edits = ChatbotResponseEdit.objects.count()
    approved_edits = ChatbotResponseEdit.objects.filter(approval_status='approved').count()
    rejected_edits = ChatbotResponseEdit.objects.filter(approval_status='rejected').count()
    pending_edits_count = ChatbotResponseEdit.objects.filter(approval_status='pending').count()

    # Knowledge base statistics
    total_kb_entries = KnowledgeBase.objects.count()
    active_kb_entries = KnowledgeBase.objects.filter(is_active=True).count()

    # Recent moderator activity (top 5 most active)
    moderator_activity = ChatbotModerationAction.objects.values(
        'actor_username'
    ).annotate(
        action_count=Count('id')
    ).order_by('-action_count')[:5]

    # Action log (latest 20)
    recent_actions = ChatbotModerationAction.objects.select_related(
        'actor'
    ).order_by('-created_at')[:20]

    context = {
        'total_flags': total_flags,
        'pending_flags': pending_flags,
        'resolved_flags': resolved_flags,
        'dismissed_flags': dismissed_flags,
        'flags_by_reason': flags_by_reason,
        'flags_by_severity': flags_by_severity,
        'avg_quality': avg_quality,
        'total_edits': total_edits,
        'approved_edits': approved_edits,
        'rejected_edits': rejected_edits,
        'pending_edits_count': pending_edits_count,
        'total_kb_entries': total_kb_entries,
        'active_kb_entries': active_kb_entries,
        'moderator_activity': moderator_activity,
        'recent_actions': recent_actions,
    }

    return render(request, 'chatbot/admin/statistics.html', context)


# =============================================================================
# MODERATION ACTION LOG
# =============================================================================

@staff_required
def action_log(request):
    """
    View the full chatbot moderation action log.
    """
    action_filter = request.GET.get('action', '')
    actor_filter = request.GET.get('actor', '')

    actions = ChatbotModerationAction.objects.select_related('actor')

    valid_action_types = [a[0] for a in ChatbotModerationAction.ACTION_TYPES]
    if action_filter and action_filter in valid_action_types:
        actions = actions.filter(action_type=action_filter)

    if actor_filter:
        actions = actions.filter(actor_username=actor_filter)

    actions = actions.order_by('-created_at')

    paginator = Paginator(actions, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get unique actors for filter
    actors = ChatbotModerationAction.objects.values_list(
        'actor_username', flat=True
    ).distinct().order_by('actor_username')

    context = {
        'actions': page_obj,
        'page_obj': page_obj,
        'action_filter': action_filter,
        'actor_filter': actor_filter,
        'action_types': ChatbotModerationAction.ACTION_TYPES,
        'actors': actors,
    }

    return render(request, 'chatbot/admin/action_log.html', context)


# =============================================================================
# USER-FACING FLAG ENDPOINT
# =============================================================================

@require_POST
def flag_response(request):
    """
    API endpoint for users to flag chatbot responses.
    Accessible to both authenticated and anonymous users.
    CSRF protection is enforced by Django middleware.
    """
    try:
        import json
        data = json.loads(request.body)
        message_id = data.get('message_id')
        reason = data.get('reason', 'other')
        description = data.get('description', '').strip()

        if not message_id:
            return JsonResponse({
                'status': 'error',
                'error': 'Message ID is required'
            }, status=400)

        try:
            chat_message = ChatMessage.objects.get(id=message_id)
        except (ChatMessage.DoesNotExist, ValueError):
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid message ID'
            }, status=404)

        valid_reasons = [r[0] for r in ChatbotResponseFlag.FLAG_REASONS]
        if reason not in valid_reasons:
            reason = 'other'

        one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
        if request.user.is_authenticated:
            recent_flags = ChatbotResponseFlag.objects.filter(
                flagged_by=request.user,
                created_at__gte=one_hour_ago
            ).count()
        else:
            session_id = request.session.session_key
            if not session_id:
                request.session.create()
                session_id = request.session.session_key
            recent_flags = ChatbotResponseFlag.objects.filter(
                flagged_by_session=session_id,
                created_at__gte=one_hour_ago
            ).count()

        if recent_flags >= 10:
            return JsonResponse({
                'status': 'error',
                'error': 'You have reached the flag limit. Please try again later.'
            }, status=429)

        # Prevent duplicate flags on the same message by the same user
        if request.user.is_authenticated:
            existing = ChatbotResponseFlag.objects.filter(
                chat_message=chat_message,
                flagged_by=request.user,
                status__in=['pending', 'under_review']
            ).exists()
        else:
            session_id = request.session.session_key or ''
            existing = ChatbotResponseFlag.objects.filter(
                chat_message=chat_message,
                flagged_by_session=session_id,
                status__in=['pending', 'under_review']
            ).exists()

        if existing:
            return JsonResponse({
                'status': 'error',
                'error': 'You have already flagged this response.'
            }, status=409)

        # Create the flag
        flag = ChatbotResponseFlag.objects.create(
            chat_message=chat_message,
            flagged_by=request.user if request.user.is_authenticated else None,
            flagged_by_session=request.session.session_key if not request.user.is_authenticated else None,
            reason=reason,
            description=description[:2000],
            ip_address=get_client_ip(request),
        )

        return JsonResponse({
            'status': 'success',
            'message': 'Response has been flagged for review. Thank you for your feedback.',
            'flag_id': str(flag.id),
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        logger.error(f"Flag response error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': 'An error occurred. Please try again later.'
        }, status=500)


# =============================================================================
# MESSAGE BROWSE VIEW (for staff to find messages to review)
# =============================================================================

@staff_required
def browse_messages(request):
    """
    Browse chat messages for moderation purposes.
    Staff can search and filter messages, then flag, edit, or score them.
    """
    search_query = request.GET.get('q', '').strip()
    user_filter = request.GET.get('user', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    messages_qs = ChatMessage.objects.select_related('user').order_by('-timestamp')

    if search_query:
        messages_qs = messages_qs.filter(
            Q(message__icontains=search_query) |
            Q(response__icontains=search_query)
        )

    if user_filter:
        messages_qs = messages_qs.filter(user__username=user_filter)

    if date_from:
        try:
            from_dt = timezone.datetime.fromisoformat(date_from)
            messages_qs = messages_qs.filter(timestamp__gte=from_dt)
        except ValueError:
            pass

    if date_to:
        try:
            to_dt = timezone.datetime.fromisoformat(date_to)
            messages_qs = messages_qs.filter(timestamp__lte=to_dt)
        except ValueError:
            pass

    paginator = Paginator(messages_qs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'messages_list': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'user_filter': user_filter,
        'date_from': date_from,
        'date_to': date_to,
    }

    return render(request, 'chatbot/admin/browse_messages.html', context)
