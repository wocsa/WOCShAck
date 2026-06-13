"""
Forum module views for community discussion.

All views follow secure coding practices with proper
authentication, authorization, input validation, and CSRF protection.

Security Measures Implemented:
- Proper HTML escaping in templates to prevent XSS
- Ownership verification for post editing to prevent IDOR
- Django ORM with parameterized queries to prevent SQL injection
- CSRF protection via Django middleware
- Input validation and length limits
- User muting checks for posting restrictions
- Staff-only moderation features
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import JsonResponse, HttpResponseForbidden, Http404
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.utils.html import escape
from django.utils.text import slugify
from datetime import timedelta


from .models import (
    Category, Topic, Post, PostLike, UserReputation,
    UserWarning, UserMute, Report, DeletedContent,
    PostEditHistory, StaffNote, ModerationLog,
    ForumNotification, TopicTag, UserBlock,
    PostBookmark, StickyPost
)
from .Utils.markdown_utils import render_markdown
from .views_extensions import parse_mentions
from .Utils.email_utils import (
    send_reply_notification_email,
    send_warning_notification_email,
    send_mute_notification_email,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_client_ip(request):
    """
    Get client IP address securely.
    Handles proxied requests properly.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def check_user_muted(user, check_posts=True, check_topics=True):
    """
    Check if user is muted and return mute info.
    Returns (is_muted, mute_object) tuple.
    """
    mute = UserMute.get_active_mute(user)
    if not mute:
        return False, None

    if check_posts and mute.mute_posts:
        return True, mute
    if check_topics and mute.mute_topics:
        return True, mute
    return False, None


def staff_required(view_func):
    """
    Decorator to require staff status.
    """
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('forum_index')
        return view_func(request, *args, **kwargs)
    return login_required(_wrapped_view)


# =============================================================================
# FORUM INDEX
# =============================================================================

def forum_index(request):
    """
    Display forum index with all categories.
    Uses Django ORM with proper annotations for statistics.
    Filters categories based on user access permissions.
    """
    categories = Category.objects.filter(is_active=True).annotate(
        topic_count=Count('topics', distinct=True),
        post_count=Count('topics__posts', distinct=True),
        last_post_date=Max('topics__posts__created_at')
    ).order_by('order', 'name')

    accessible_categories = []
    for category in categories:
        if category.user_can_access(request.user):
            category.latest_post = Post.objects.filter(
                topic__category=category
            ).select_related('author', 'topic').order_by('-created_at').first()
            accessible_categories.append(category)

    # Get overall statistics
    stats = {
        'total_topics': Topic.objects.count(),
        'total_posts': Post.objects.count(),
        'total_members': UserReputation.objects.count(),
    }

    # Get recent topics (only from accessible categories)
    recent_topics = Topic.objects.filter(
        category__in=accessible_categories
    ).select_related(
        'category', 'author'
    ).order_by('-created_at')[:5]

    context = {
        'categories': accessible_categories,
        'stats': stats,
        'recent_topics': recent_topics,
    }

    return render(request, 'forum/index.html', context)


# =============================================================================
# CATEGORY VIEWS
# =============================================================================

def category_view(request, slug):
    """
    Display topics within a category.
    Uses allowlisted sorting and proper pagination.
    Checks user access permissions for private categories.
    """
    category = get_object_or_404(Category, slug=slug, is_active=True)

    if not category.user_can_access(request.user):
        messages.error(request, 'You do not have permission to access this category.')
        return redirect('forum_index')

    topics = category.topics.select_related('author').annotate(
        reply_count=Count('posts') - 1,
        last_post_date=Max('posts__created_at')
    )

    sort_by = request.GET.get('sort', '-last_activity')
    valid_sorts = ['-last_activity', '-created_at', 'created_at', '-view_count', 'title']
    if sort_by in valid_sorts:
        # Pinned topics always on top
        topics = topics.order_by('-is_pinned', sort_by)
    else:
        topics = topics.order_by('-is_pinned', '-last_activity')

    paginator = Paginator(topics, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'category': category,
        'topics': page_obj,
        'page_obj': page_obj,
        'sort_by': sort_by,
    }

    return render(request, 'forum/category.html', context)


# =============================================================================
# TOPIC VIEWS
# =============================================================================

def topic_view(request, topic_id):
    """
    Display topic with all its posts.
    Post content is properly escaped in the template to prevent XSS attacks.
    Includes user profile pictures and reputation ranks.
    """
    topic = get_object_or_404(
        Topic.objects.select_related('category', 'author'),
        id=topic_id
    )

    # Increment view count
    topic.increment_view_count()

    posts = topic.posts.select_related(
        'author',
        'author__profile'  # Include profile for picture_path access
    ).prefetch_related('likes')

    if not request.user.is_staff:
        posts = posts.filter(is_hidden=False)

    paginator = Paginator(posts, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Add author rank to each post for display
    for post in page_obj:
        reputation = UserReputation.get_or_create_for_user(post.author)
        post.author_rank = reputation.get_rank()

    # Get like status for authenticated users
    if request.user.is_authenticated:
        liked_post_ids = set(
            PostLike.objects.filter(
                user=request.user,
                post__in=page_obj
            ).values_list('post_id', flat=True)
        )
        bookmarked_post_ids = set(
            PostBookmark.objects.filter(
                user=request.user,
                post__in=page_obj
            ).values_list('post_id', flat=True)
        )
        blocked_user_ids = UserBlock.get_blocked_user_ids(request.user)
    else:
        liked_post_ids = set()
        bookmarked_post_ids = set()
        blocked_user_ids = set()

    sticky_post_ids = set(
        StickyPost.objects.filter(
            post__topic=topic
        ).values_list('post_id', flat=True)
    )

    topic_tags = TopicTag.objects.filter(
        topic=topic
    ).select_related('tag')

    # Add rendered markdown content for each post
    for post in page_obj:
        post.rendered_content = render_markdown(post.content)

    # Handle quote parameter for pre-filling reply
    quote_text = ''
    quote_post_id = request.GET.get('quote', '')
    if quote_post_id:
        try:
            quoted_post = Post.objects.select_related('author').get(id=quote_post_id, topic=topic)
            quoted_lines = quoted_post.content.split('\n')
            quoted_content = '\n'.join(f'> {line}' for line in quoted_lines)
            quote_text = f'> **{escape(quoted_post.author.username)}** wrote:\n{quoted_content}\n\n'
        except (Post.DoesNotExist, ValueError):
            pass

    context = {
        'topic': topic,
        'posts': page_obj,
        'page_obj': page_obj,
        'liked_post_ids': liked_post_ids,
        'bookmarked_post_ids': bookmarked_post_ids,
        'blocked_user_ids': blocked_user_ids,
        'sticky_post_ids': sticky_post_ids,
        'topic_tags': topic_tags,
        'can_reply': not topic.is_locked,
        'quote_text': quote_text,
    }

    return render(request, 'forum/topic.html', context)


@login_required
def create_topic_general(request):
    """
    Create a new topic with category selection in the form.
    Allows any authenticated user to select a category and create a topic.
    Includes CSRF protection via Django's middleware.
    Checks for user mute status before allowing topic creation.
    """
    is_muted, mute = check_user_muted(request.user, check_posts=False, check_topics=True)
    if is_muted:
        if mute.is_permanent:
            messages.error(request, 'You are permanently muted and cannot create new topics.')
        else:
            remaining = mute.get_remaining_duration()
            if remaining:
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                messages.error(request, f'You are muted and cannot create new topics. Mute expires in {hours}h {minutes}m.')
            else:
                messages.error(request, 'You are muted and cannot create new topics.')
        return redirect('forum_index')

    all_categories = Category.objects.filter(is_active=True).order_by('order', 'name')
    postable_categories = [cat for cat in all_categories if cat.user_can_post(request.user)]

    if not postable_categories:
        messages.error(request, 'There are no categories available for you to create topics in.')
        return redirect('forum_index')

    # Pre-select category if provided via query parameter
    preselected_slug = request.GET.get('category', '')
    preselected_category = None
    if preselected_slug:
        for cat in postable_categories:
            if cat.slug == preselected_slug:
                preselected_category = cat
                break

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        category_id = request.POST.get('category', '').strip()

        errors = []
        if not title or len(title) < 5:
            errors.append('Title must be at least 5 characters.')
        if len(title) > 200:
            errors.append('Title cannot exceed 200 characters.')
        if not content or len(content) < 10:
            errors.append('Content must be at least 10 characters.')
        if len(content) > 50000:
            errors.append('Content cannot exceed 50,000 characters.')
        if not category_id:
            errors.append('Please select a category.')

        category = None
        if category_id:
            try:
                category = Category.objects.get(id=category_id, is_active=True)
                if not category.user_can_post(request.user):
                    errors.append('You do not have permission to create topics in this category.')
                    category = None
            except (Category.DoesNotExist, ValueError, ValidationError):
                errors.append('Invalid category selected.')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'forum/create_topic.html', {
                'categories': postable_categories,
                'selected_category_id': category_id,
                'title': title,
                'content': content,
            })

        with transaction.atomic():
            # Create the topic
            topic = Topic.objects.create(
                category=category,
                author=request.user,
                title=title,
            )

            # Create the first post
            post = Post.objects.create(
                topic=topic,
                author=request.user,
                content=content,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            )

            # Update user reputation
            reputation = UserReputation.get_or_create_for_user(request.user)
            reputation.topics_count += 1
            reputation.posts_count += 1
            reputation.add_points(5, 'Created new topic')

            parse_mentions(content, post, request.user)

            # Handle tags if provided
            tags_input = request.POST.get('tags', '').strip()
            if tags_input:
                import re
                from .models import Tag, TopicTag
                tag_names = [t.strip().lower() for t in tags_input.split(',') if t.strip()][:5]
                for tag_name in tag_names:
                    if re.match(r'^[a-z0-9][a-z0-9\-_]*$', tag_name) and 2 <= len(tag_name) <= 50:
                        tag, _ = Tag.objects.get_or_create(
                            name=tag_name,
                            defaults={'slug': slugify(tag_name), 'created_by': request.user}
                        )
                        TopicTag.objects.get_or_create(
                            topic=topic, tag=tag,
                            defaults={'added_by': request.user}
                        )

        try:
            from Community.services.feed_service import create_feed_item
            from Community.models.feed import ActivityFeedItem
            create_feed_item(
                user=request.user,
                action_type=ActivityFeedItem.ActionType.FORUM_TOPIC_CREATED,
                title=f'Started a new discussion: {topic.title}',
                description=content[:200],
                icon='💬',
                related_object_id=str(topic.id),
            )
        except Exception:
            pass

        messages.success(request, 'Topic created successfully!')
        return redirect('forum_topic', topic_id=topic.id)

    context = {
        'categories': postable_categories,
        'selected_category_id': str(preselected_category.id) if preselected_category else '',
        'category': preselected_category,
    }

    return render(request, 'forum/create_topic.html', context)


@login_required
def create_topic(request, category_slug):
    """
    Create a new topic in a specific category (legacy URL support).
    Redirects to the general create topic view with category pre-selected.
    Includes CSRF protection via Django's middleware.
    Checks for user mute status before allowing topic creation.
    Checks category access and posting permissions.
    """
    category = get_object_or_404(Category, slug=category_slug, is_active=True)

    if not category.user_can_post(request.user):
        messages.error(request, 'You do not have permission to create topics in this category.')
        return redirect('forum_index')

    is_muted, mute = check_user_muted(request.user, check_posts=False, check_topics=True)
    if is_muted:
        if mute.is_permanent:
            messages.error(request, 'You are permanently muted and cannot create new topics.')
        else:
            remaining = mute.get_remaining_duration()
            if remaining:
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                messages.error(request, f'You are muted and cannot create new topics. Mute expires in {hours}h {minutes}m.')
            else:
                messages.error(request, 'You are muted and cannot create new topics.')
        return redirect('forum_category', slug=category_slug)

    all_categories = Category.objects.filter(is_active=True).order_by('order', 'name')
    postable_categories = [cat for cat in all_categories if cat.user_can_post(request.user)]

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        # Allow user to change category from the form even when accessed via category URL
        category_id = request.POST.get('category', '').strip()

        if category_id:
            try:
                submitted_category = Category.objects.get(id=category_id, is_active=True)
                if submitted_category.user_can_post(request.user):
                    category = submitted_category
            except (Category.DoesNotExist, ValueError, ValidationError):
                pass  # Fall back to URL category

        errors = []
        if not title or len(title) < 5:
            errors.append('Title must be at least 5 characters.')
        if len(title) > 200:
            errors.append('Title cannot exceed 200 characters.')
        if not content or len(content) < 10:
            errors.append('Content must be at least 10 characters.')
        if len(content) > 50000:
            errors.append('Content cannot exceed 50,000 characters.')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'forum/create_topic.html', {
                'category': category,
                'categories': postable_categories,
                'selected_category_id': str(category.id),
                'title': title,
                'content': content,
            })

        with transaction.atomic():
            # Create the topic
            topic = Topic.objects.create(
                category=category,
                author=request.user,
                title=title,
            )

            # Create the first post
            post = Post.objects.create(
                topic=topic,
                author=request.user,
                content=content,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            )

            # Update user reputation
            reputation = UserReputation.get_or_create_for_user(request.user)
            reputation.topics_count += 1
            reputation.posts_count += 1
            reputation.add_points(5, 'Created new topic')

        messages.success(request, 'Topic created successfully!')
        return redirect('forum_topic', topic_id=topic.id)

    context = {
        'category': category,
        'categories': postable_categories,
        'selected_category_id': str(category.id),
    }

    return render(request, 'forum/create_topic.html', context)


@login_required
@require_POST
def create_reply(request, topic_id):
    """
    Create a reply to a topic.
    Checks for user mute status before allowing replies.
    Content is properly sanitized through markdown rendering.
    """
    topic = get_object_or_404(Topic, id=topic_id)

    if topic.is_locked:
        messages.error(request, 'This topic is locked and cannot receive new replies.')
        return redirect('forum_topic', topic_id=topic_id)

    is_muted, mute = check_user_muted(request.user, check_posts=True, check_topics=False)
    if is_muted:
        if mute.is_permanent:
            messages.error(request, 'You are permanently muted and cannot post replies.')
        else:
            remaining = mute.get_remaining_duration()
            if remaining:
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                messages.error(request, f'You are muted and cannot post replies. Mute expires in {hours}h {minutes}m.')
            else:
                messages.error(request, 'You are muted and cannot post replies.')
        return redirect('forum_topic', topic_id=topic_id)

    content = request.POST.get('content', '').strip()

    if not content or len(content) < 1:
        messages.error(request, 'Reply content cannot be empty.')
        return redirect('forum_topic', topic_id=topic_id)

    if len(content) > 50000:
        messages.error(request, 'Reply content cannot exceed 50,000 characters.')
        return redirect('forum_topic', topic_id=topic_id)

    with transaction.atomic():
        post = Post.objects.create(
            topic=topic,
            author=request.user,
            content=content,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        )

        # Update topic's last activity
        topic.update_last_activity()

        # Update user reputation
        reputation = UserReputation.get_or_create_for_user(request.user)
        reputation.posts_count += 1
        reputation.add_points(2, 'Posted reply')

        parse_mentions(content, post, request.user)

        if topic.author != request.user:
            ForumNotification.create_notification(
                recipient=topic.author,
                notification_type='reply',
                message=f'{request.user.username} replied to your topic "{topic.title}"',
                sender=request.user,
                link=post.get_absolute_url(),
                related_post=post,
                related_topic=topic,
            )

            send_reply_notification_email(
                topic_author=topic.author,
                replier_username=request.user.username,
                topic_title=topic.title,
                post_url=post.get_absolute_url(),
            )

    messages.success(request, 'Reply posted successfully!')

    # Redirect to the last page of the topic
    return redirect(f"{topic.get_absolute_url()}?page=last#post-{post.id}")


# =============================================================================
# POST EDITING
# =============================================================================

@login_required
def edit_post(request, post_id):
    """
    Edit an existing post.
    Includes proper ownership verification to prevent IDOR attacks.
    Only the post author or staff members can edit posts.
    Tracks edit history for audit and recovery purposes.
    """
    post = get_object_or_404(Post, id=post_id)

    if post.author != request.user and not request.user.is_staff:
        messages.error(request, 'You do not have permission to edit this post.')
        return HttpResponseForbidden("You cannot edit this post.")

    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        edit_reason = request.POST.get('edit_reason', '').strip()[:200]

        if not content or len(content) < 1:
            messages.error(request, 'Post content cannot be empty.')
            return render(request, 'forum/edit_post.html', {'post': post})

        if len(content) > 50000:
            messages.error(request, 'Post content cannot exceed 50,000 characters.')
            return render(request, 'forum/edit_post.html', {'post': post})

        with transaction.atomic():
            content_before = post.content
            if content != content_before:
                PostEditHistory.create_revision(
                    post=post,
                    edited_by=request.user,
                    content_before=content_before,
                    content_after=content,
                    reason=edit_reason,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )

            post.content = content
            post.mark_edited(edit_reason)

        messages.success(request, 'Post updated successfully!')
        return redirect(post.get_absolute_url())

    # Get edit history for display
    edit_history = post.edit_history.order_by('-created_at')[:10]

    context = {
        'post': post,
        'edit_history': edit_history,
    }

    return render(request, 'forum/edit_post.html', context)


@login_required
@require_POST
def delete_post(request, post_id):
    """
    Delete a post (only own posts or moderators).
    Properly checks ownership before deletion.
    Creates soft delete record for audit trail and recovery.
    """
    post = get_object_or_404(Post, id=post_id)

    if post.author != request.user and not request.user.is_staff:
        messages.error(request, 'You cannot delete this post.')
        return redirect(post.topic.get_absolute_url())

    topic = post.topic
    deletion_reason = request.POST.get('reason', 'user_request')
    deletion_notes = request.POST.get('notes', '')

    # Validate deletion reason
    valid_reasons = [r[0] for r in DeletedContent.DELETION_REASONS]
    if deletion_reason not in valid_reasons:
        deletion_reason = 'other'

    with transaction.atomic():
        # Check if this is the first post (topic starter)
        first_post = topic.get_first_post()
        if post == first_post:
            DeletedContent.create_from_topic(
                topic=topic,
                deleted_by=request.user,
                reason=deletion_reason,
                notes=deletion_notes
            )

            # Log the moderation action
            ModerationLog.log_action(
                moderator=request.user,
                action_type='topic_deleted',
                description=f'Deleted topic: {topic.title}',
                target_user=topic.author,
                target_topic_id=topic.id,
                ip_address=get_client_ip(request)
            )

            # Delete the entire topic
            category_slug = topic.category.slug
            topic.delete()
            messages.success(request, 'Topic deleted successfully.')
            return redirect('forum_category', slug=category_slug)

        DeletedContent.create_from_post(
            post=post,
            deleted_by=request.user,
            reason=deletion_reason,
            notes=deletion_notes
        )

        # Log the moderation action
        ModerationLog.log_action(
            moderator=request.user,
            action_type='post_deleted',
            description=f'Deleted post in topic: {topic.title}',
            target_user=post.author,
            target_post_id=post.id,
            ip_address=get_client_ip(request)
        )

        post.delete()

    messages.success(request, 'Post deleted successfully.')
    return redirect(topic.get_absolute_url())


# =============================================================================
# SEARCH
# =============================================================================

def search(request):
    """
    Search forum topics and posts.
    Uses Django ORM with parameterized queries to prevent SQL injection.
    """
    query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'all')  # all, topics, posts

    results = []

    if query:
        # This prevents SQL injection by using parameterized queries
        if search_type in ('all', 'topics'):
            topic_results = Topic.objects.filter(
                title__icontains=query
            ).select_related('category', 'author').order_by('-created_at')[:50]

            for topic in topic_results:
                results.append({
                    'id': str(topic.id),
                    'title': topic.title,
                    'type': 'topic',
                    'category': topic.category.name,
                    'author': topic.author.username,
                })

        if search_type in ('all', 'posts'):
            post_query = Post.objects.filter(content__icontains=query)
            if not request.user.is_staff:
                post_query = post_query.filter(is_hidden=False)
            post_results = post_query.select_related('topic', 'author')[:50]

            for post in post_results:
                results.append({
                    'id': str(post.id),
                    'title': f"Reply in: {post.topic.title}",
                    'type': 'post',
                    'topic_id': str(post.topic.id),
                    'author': post.author.username,
                    'excerpt': post.content[:200] + '...' if len(post.content) > 200 else post.content,
                })

    context = {
        'query': escape(query),  # Escape for display (doesn't fix SQL injection)
        'search_type': search_type,
        'results': results,
        'result_count': len(results),
    }

    return render(request, 'forum/search.html', context)


# =============================================================================
# LIKE/UNLIKE
# =============================================================================

@login_required
@require_POST
def moderate_post(request, post_id):
    """
    Moderate a post (hide/unhide).
    Only accessible to staff members.
    Logs all moderation actions for audit trail.
    """
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'})

    post = get_object_or_404(Post, id=post_id)
    action = request.POST.get('action') or request.GET.get('action')

    if not action:
        try:
            import json
            data = json.loads(request.body)
            action = data.get('action')
        except:
            pass

    if action not in ['hide', 'unhide', 'delete', 'lock', 'approve', 'reject']:
        return JsonResponse({'success': False, 'error': f'Invalid action: {action}'})

    with transaction.atomic():
        if action in ['hide', 'reject']:
            post.is_hidden = True
            post.hidden_by = request.user
            post.hidden_reason = request.POST.get('reason', '')[:200]
            post.save()

            # Log the moderation action
            ModerationLog.log_action(
                moderator=request.user,
                action_type='post_hidden',
                description=f'Hidden post: {post.hidden_reason}',
                target_user=post.author,
                target_post_id=post.id,
                ip_address=get_client_ip(request)
            )
        elif action in ['unhide', 'approve']:
            post.is_hidden = False
            post.hidden_by = None
            post.hidden_reason = ''
            post.save()

            # Log the moderation action
            ModerationLog.log_action(
                moderator=request.user,
                action_type='post_unhidden',
                description='Unhidden post',
                target_user=post.author,
                target_post_id=post.id,
                ip_address=get_client_ip(request)
            )
        elif action == 'delete':
            post.delete()
            return JsonResponse({'success': True, 'action': action})

    return JsonResponse({'success': True, 'action': action})


@login_required
@require_POST
def toggle_like(request, post_id):
    """
    Toggle like on a post.
    Uses atomic transactions and proper validation.
    """
    post = get_object_or_404(Post, id=post_id)

    # Can't like your own post
    if post.author == request.user:
        return JsonResponse({'success': False, 'error': 'Cannot like your own post'})

    with transaction.atomic():
        like, created = PostLike.objects.get_or_create(
            user=request.user,
            post=post
        )

        if not created:
            # Unlike - remove the like
            like.delete()
            liked = False
            # Update reputation
            author_rep = UserReputation.get_or_create_for_user(post.author)
            author_rep.likes_received = max(0, author_rep.likes_received - 1)
            author_rep.add_points(-1, 'Like removed')

            user_rep = UserReputation.get_or_create_for_user(request.user)
            user_rep.likes_given = max(0, user_rep.likes_given - 1)
            user_rep.save()
        else:
            # Like - created above
            liked = True
            # Update reputation
            author_rep = UserReputation.get_or_create_for_user(post.author)
            author_rep.likes_received += 1
            author_rep.add_points(1, 'Received like')

            user_rep = UserReputation.get_or_create_for_user(request.user)
            user_rep.likes_given += 1
            user_rep.save()

    return JsonResponse({
        'success': True,
        'liked': liked,
        'like_count': post.get_like_count(),
    })


# =============================================================================
# USER PROFILE (FORUM)
# =============================================================================

def user_forum_profile(request, username):
    """
    Display user's forum activity.
    Includes profile picture from Account module.
    """
    from django.contrib.auth.models import User

    user = get_object_or_404(User.objects.select_related('profile'), username=username)
    reputation = UserReputation.get_or_create_for_user(user)

    # Get user's recent topics
    recent_topics = Topic.objects.filter(author=user).order_by('-created_at')[:10]

    # Get user's recent posts
    post_query = Post.objects.filter(author=user)
    if not request.user.is_staff:
        post_query = post_query.filter(is_hidden=False)
    recent_posts = post_query.select_related('topic').order_by('-created_at')[:10]

    context = {
        'profile_user': user,
        'reputation': reputation,
        'recent_topics': recent_topics,
        'recent_posts': recent_posts,
    }

    return render(request, 'forum/user_profile.html', context)


# =============================================================================
# MODERATION VIEWS - WARNINGS
# =============================================================================

@staff_required
def moderation_dashboard(request):
    """
    Main moderation dashboard for staff.
    Shows pending reports, recent activity, and key metrics.
    """
    # Get pending reports count and list
    pending_reports = Report.objects.filter(status='pending').order_by('-priority', '-created_at')[:10]
    pending_count = Report.objects.filter(status='pending').count()

    # Get reports under review
    under_review = Report.objects.filter(status='under_review').count()

    # Get recent moderation actions
    recent_actions = ModerationLog.objects.select_related(
        'moderator', 'target_user'
    ).order_by('-created_at')[:15]

    # Get active mutes
    active_mutes = UserMute.objects.filter(
        is_active=True,
        revoked=False
    ).filter(
        Q(is_permanent=True) | Q(ends_at__gt=timezone.now())
    ).count()

    # Get recent warnings
    recent_warnings = UserWarning.objects.select_related(
        'user', 'issued_by'
    ).order_by('-created_at')[:10]

    context = {
        'pending_reports': pending_reports,
        'pending_count': pending_count,
        'under_review': under_review,
        'recent_actions': recent_actions,
        'active_mutes': active_mutes,
        'recent_warnings': recent_warnings,
    }

    return render(request, 'forum/admin/dashboard.html', context)


@staff_required
def issue_warning(request, username):
    """
    Issue a warning to a user.
    Creates warning record with full audit trail.
    """
    target_user = get_object_or_404(User, username=username)

    if request.method == 'POST':
        severity = request.POST.get('severity', 'warning')
        reason = request.POST.get('reason', '').strip()
        rule_violated = request.POST.get('rule_violated', '').strip()
        points = int(request.POST.get('points', 1))
        expires_days = request.POST.get('expires_days', '')
        related_post_id = request.POST.get('related_post_id', '')

        # Validate inputs
        if not reason or len(reason) < 10:
            messages.error(request, 'Reason must be at least 10 characters.')
            return redirect('forum_issue_warning', username=username)

        if severity not in ['notice', 'warning', 'final_warning']:
            severity = 'warning'

        # Calculate expiration
        expires_at = None
        if expires_days and expires_days.isdigit():
            expires_at = timezone.now() + timedelta(days=int(expires_days))

        # Get related post if provided
        related_post = None
        if related_post_id:
            try:
                related_post = Post.objects.get(id=related_post_id)
            except (Post.DoesNotExist, ValueError):
                pass

        with transaction.atomic():
            warning = UserWarning.objects.create(
                user=target_user,
                issued_by=request.user,
                severity=severity,
                reason=reason,
                rule_violated=rule_violated[:200],
                points=min(max(points, 1), 10),  # Clamp between 1-10
                expires_at=expires_at,
                related_post=related_post,
                related_topic=related_post.topic if related_post else None,
                ip_address=get_client_ip(request),
            )

            # Log the moderation action
            ModerationLog.log_action(
                moderator=request.user,
                action_type='warning_issued',
                description=f'{severity.replace("_", " ").title()}: {reason[:100]}',
                target_user=target_user,
                ip_address=get_client_ip(request),
                related_warning=warning,
            )

            ForumNotification.create_notification(
                recipient=target_user,
                notification_type='warning',
                message=f'You received a {severity.replace("_", " ")}: {reason[:100]}',
                sender=request.user,
            )

            send_warning_notification_email(
                warned_user=target_user,
                severity=severity,
                reason=reason,
                moderator_username=request.user.username,
            )

        messages.success(request, f'Warning issued to {target_user.username}.')
        return redirect('forum_user_admin', username=username)

    # Get user's warning history
    warnings = UserWarning.objects.filter(user=target_user).order_by('-created_at')
    active_warnings = UserWarning.get_active_warnings(target_user)
    warning_points = UserWarning.get_warning_points(target_user)

    context = {
        'target_user': target_user,
        'warnings': warnings,
        'active_warnings': active_warnings,
        'warning_points': warning_points,
    }

    return render(request, 'forum/admin/issue_warning.html', context)


@staff_required
def view_warnings(request, username):
    """
    View all warnings for a user.
    """
    target_user = get_object_or_404(User, username=username)
    warnings = UserWarning.objects.filter(user=target_user).select_related(
        'issued_by', 'related_post', 'related_topic'
    ).order_by('-created_at')

    paginator = Paginator(warnings, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    active_warnings = UserWarning.get_active_warnings(target_user)
    warning_points = UserWarning.get_warning_points(target_user)

    context = {
        'target_user': target_user,
        'warnings': page_obj,
        'page_obj': page_obj,
        'active_warnings_count': active_warnings.count(),
        'warning_points': warning_points,
    }

    return render(request, 'forum/admin/view_warnings.html', context)


# =============================================================================
# MODERATION VIEWS - MUTING
# =============================================================================

@staff_required
def mute_user(request, username):
    """
    Mute a user to prevent posting.
    Creates mute record with configurable duration and scope.
    """
    target_user = get_object_or_404(User, username=username)

    # Check if user already has active mute
    existing_mute = UserMute.get_active_mute(target_user)

    if request.method == 'POST':
        reason_type = request.POST.get('reason_type', 'other')
        reason = request.POST.get('reason', '').strip()
        duration_hours = request.POST.get('duration_hours', '24')
        is_permanent = request.POST.get('is_permanent') == 'on'
        mute_posts = request.POST.get('mute_posts', 'on') == 'on'
        mute_topics = request.POST.get('mute_topics', 'on') == 'on'
        mute_likes = request.POST.get('mute_likes') == 'on'
        related_warning_id = request.POST.get('related_warning_id', '')

        # Validate inputs
        if not reason or len(reason) < 10:
            messages.error(request, 'Reason must be at least 10 characters.')
            return redirect('forum_mute_user', username=username)

        # Calculate end time
        if is_permanent:
            ends_at = timezone.now() + timedelta(days=365 * 100)  # Far future
        else:
            try:
                hours = int(duration_hours)
                hours = min(max(hours, 1), 8760)  # Clamp between 1 hour and 1 year
            except ValueError:
                hours = 24
            ends_at = timezone.now() + timedelta(hours=hours)

        # Get related warning if provided
        related_warning = None
        if related_warning_id:
            try:
                related_warning = UserWarning.objects.get(id=related_warning_id)
            except (UserWarning.DoesNotExist, ValueError):
                pass

        with transaction.atomic():
            # Revoke existing mute if any
            if existing_mute:
                existing_mute.revoke(request.user, 'Replaced with new mute')

            mute = UserMute.objects.create(
                user=target_user,
                muted_by=request.user,
                reason_type=reason_type,
                reason=reason,
                ends_at=ends_at,
                is_permanent=is_permanent,
                mute_posts=mute_posts,
                mute_topics=mute_topics,
                mute_likes=mute_likes,
                related_warning=related_warning,
            )

            # Log the moderation action
            duration_str = 'permanently' if is_permanent else f'for {duration_hours} hours'
            ModerationLog.log_action(
                moderator=request.user,
                action_type='mute_applied',
                description=f'Muted user {duration_str}: {reason[:100]}',
                target_user=target_user,
                ip_address=get_client_ip(request),
                related_mute=mute,
            )

            ForumNotification.create_notification(
                recipient=target_user,
                notification_type='mute',
                message=f'You have been muted {duration_str}: {reason[:100]}',
                sender=request.user,
            )

            send_mute_notification_email(
                muted_user=target_user,
                reason=reason,
                duration_str=f'{duration_hours} hours' if not is_permanent else '',
                is_permanent=is_permanent,
            )

        messages.success(request, f'{target_user.username} has been muted.')
        return redirect('forum_user_admin', username=username)

    # Get user's mute history
    mute_history = UserMute.objects.filter(user=target_user).order_by('-created_at')[:10]

    # Get recent warnings for linking
    recent_warnings = UserWarning.objects.filter(user=target_user).order_by('-created_at')[:5]

    context = {
        'target_user': target_user,
        'existing_mute': existing_mute,
        'mute_history': mute_history,
        'recent_warnings': recent_warnings,
        'mute_reasons': UserMute.MUTE_REASONS,
    }

    return render(request, 'forum/admin/mute_user.html', context)


@staff_required
@require_POST
def unmute_user(request, username):
    """
    Revoke active mute on a user.
    """
    target_user = get_object_or_404(User, username=username)
    mute = UserMute.get_active_mute(target_user)

    if not mute:
        messages.info(request, f'{target_user.username} is not currently muted.')
        return redirect('forum_user_admin', username=username)

    revoke_reason = request.POST.get('reason', 'Manually revoked by staff')

    with transaction.atomic():
        mute.revoke(request.user, revoke_reason)

        # Log the moderation action
        ModerationLog.log_action(
            moderator=request.user,
            action_type='mute_revoked',
            description=f'Revoked mute: {revoke_reason[:100]}',
            target_user=target_user,
            ip_address=get_client_ip(request),
            related_mute=mute,
        )

    messages.success(request, f'Mute on {target_user.username} has been revoked.')
    return redirect('forum_user_admin', username=username)


# =============================================================================
# MODERATION VIEWS - REPORTS
# =============================================================================

@login_required
@require_POST
def report_content(request):
    """
    Submit a report for content or user.
    Validates report data and creates report record.
    """
    report_type = request.POST.get('report_type', 'other')
    description = request.POST.get('description', '').strip()
    post_id = request.POST.get('post_id', '')
    topic_id = request.POST.get('topic_id', '')
    user_id = request.POST.get('user_id', '')

    # Validate description
    if not description or len(description) < 10:
        messages.error(request, 'Please provide a detailed description (at least 10 characters).')
        return redirect(request.META.get('HTTP_REFERER', 'forum_index'))

    # Rate limiting - max 10 reports per day
    recent_reports = Report.get_user_report_count(request.user, days=1)
    if recent_reports >= 10:
        messages.error(request, 'You have reached the maximum number of reports for today.')
        return redirect(request.META.get('HTTP_REFERER', 'forum_index'))

    # Get reported content
    reported_post = None
    reported_topic = None
    reported_user = None
    content_snapshot = ''

    if post_id:
        try:
            reported_post = Post.objects.get(id=post_id)
            reported_user = reported_post.author
            content_snapshot = reported_post.content[:5000]
        except (Post.DoesNotExist, ValueError):
            messages.error(request, 'The reported content could not be found.')
            return redirect(request.META.get('HTTP_REFERER', 'forum_index'))
    elif topic_id:
        try:
            reported_topic = Topic.objects.get(id=topic_id)
            reported_user = reported_topic.author
            first_post = reported_topic.get_first_post()
            if first_post:
                content_snapshot = first_post.content[:5000]
        except (Topic.DoesNotExist, ValueError):
            messages.error(request, 'The reported content could not be found.')
            return redirect(request.META.get('HTTP_REFERER', 'forum_index'))
    elif user_id:
        try:
            reported_user = User.objects.get(id=user_id)
        except (User.DoesNotExist, ValueError):
            messages.error(request, 'The reported user could not be found.')
            return redirect(request.META.get('HTTP_REFERER', 'forum_index'))

    if not reported_post and not reported_topic and not reported_user:
        messages.error(request, 'Please specify what you want to report.')
        return redirect(request.META.get('HTTP_REFERER', 'forum_index'))

    # Prevent self-reporting
    if reported_user == request.user:
        messages.error(request, 'You cannot report yourself.')
        return redirect(request.META.get('HTTP_REFERER', 'forum_index'))

    # Validate report type
    valid_types = [r[0] for r in Report.REPORT_TYPES]
    if report_type not in valid_types:
        report_type = 'other'

    # Calculate priority based on report type
    priority_map = {
        'harassment': 4,
        'hate_speech': 5,
        'personal_info': 5,
        'spam': 2,
        'inappropriate': 3,
        'misinformation': 3,
        'copyright': 3,
        'off_topic': 1,
        'other': 2,
    }
    priority = priority_map.get(report_type, 2)

    with transaction.atomic():
        report = Report.objects.create(
            reporter=request.user,
            reported_post=reported_post,
            reported_topic=reported_topic,
            reported_user=reported_user,
            report_type=report_type,
            description=description,
            content_snapshot=content_snapshot,
            priority=priority,
            reporter_ip=get_client_ip(request),
        )

    messages.success(request, 'Your report has been submitted. Thank you for helping keep the community safe.')

    # Redirect back
    if reported_post:
        return redirect(reported_post.get_absolute_url())
    elif reported_topic:
        return redirect(reported_topic.get_absolute_url())
    else:
        return redirect('forum_user_profile', username=reported_user.username)


@staff_required
def report_queue(request):
    """
    View and manage report queue.
    Filterable by status, type, and assignment.
    """
    status_filter = request.GET.get('status', 'pending')
    type_filter = request.GET.get('type', '')
    assigned_filter = request.GET.get('assigned', '')

    reports = Report.objects.select_related(
        'reporter', 'reported_post', 'reported_topic', 'reported_user', 'assigned_to'
    )

    # Apply filters
    if status_filter:
        reports = reports.filter(status=status_filter)
    if type_filter:
        reports = reports.filter(report_type=type_filter)
    if assigned_filter == 'me':
        reports = reports.filter(assigned_to=request.user)
    elif assigned_filter == 'unassigned':
        reports = reports.filter(assigned_to__isnull=True)

    reports = reports.order_by('-priority', '-created_at')

    paginator = Paginator(reports, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get counts for filter badges
    status_counts = {
        'pending': Report.objects.filter(status='pending').count(),
        'under_review': Report.objects.filter(status='under_review').count(),
        'action_taken': Report.objects.filter(status='action_taken').count(),
        'dismissed': Report.objects.filter(status='dismissed').count(),
    }

    context = {
        'reports': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'assigned_filter': assigned_filter,
        'status_counts': status_counts,
        'report_types': Report.REPORT_TYPES,
        'status_choices': Report.STATUS_CHOICES,
    }

    return render(request, 'forum/admin/report_queue.html', context)


@staff_required
def report_detail(request, report_id):
    """
    View and manage individual report.
    """
    report = get_object_or_404(
        Report.objects.select_related(
            'reporter', 'reported_post', 'reported_topic', 'reported_user',
            'assigned_to', 'resolved_by'
        ),
        id=report_id
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        with transaction.atomic():
            if action == 'assign':
                report.assign(request.user)
                ModerationLog.log_action(
                    moderator=request.user,
                    action_type='report_assigned',
                    description=f'Assigned report to self',
                    target_user=report.get_reported_content_author(),
                    ip_address=get_client_ip(request),
                    related_report=report,
                )
                messages.success(request, 'Report assigned to you.')

            elif action == 'resolve':
                resolution_notes = request.POST.get('resolution_notes', '')
                report_valid = request.POST.get('report_valid') == 'true'
                send_feedback = request.POST.get('send_feedback') == 'on'
                feedback_message = request.POST.get('feedback_message', '').strip()

                # Record actions taken
                report.action_warning_issued = request.POST.get('action_warning') == 'on'
                report.action_content_hidden = request.POST.get('action_hidden') == 'on'
                report.action_content_deleted = request.POST.get('action_deleted') == 'on'
                report.action_user_muted = request.POST.get('action_muted') == 'on'

                # Send feedback to reporter if requested
                if send_feedback and report.reporter:
                    report.reporter_notified = True
                    default_feedback = (
                        f"Your report has been reviewed. Status: {'Valid - Action Taken' if report_valid else 'Dismissed'}. "
                        f"Thank you for helping keep the community safe."
                    )
                    report.reporter_feedback = feedback_message if feedback_message else default_feedback

                    # Award reputation for valid reports
                    if report_valid:
                        reporter_rep = UserReputation.get_or_create_for_user(report.reporter)
                        reporter_rep.add_points(5, 'Valid report submitted')
                        messages.success(request, f'Reporter {report.reporter.username} awarded 5 reputation points for valid report.')

                report.resolve(request.user, resolution_notes, report_valid)

                ModerationLog.log_action(
                    moderator=request.user,
                    action_type='report_resolved',
                    description=f'Resolved report: {"Valid" if report_valid else "Dismissed"}',
                    target_user=report.get_reported_content_author(),
                    ip_address=get_client_ip(request),
                    related_report=report,
                )
                messages.success(request, 'Report resolved.')

            elif action == 'escalate':
                escalation_notes = request.POST.get('escalation_notes', '')
                report.escalate(escalation_notes)

                ModerationLog.log_action(
                    moderator=request.user,
                    action_type='report_escalated',
                    description=f'Escalated report: {escalation_notes[:100]}',
                    target_user=report.get_reported_content_author(),
                    ip_address=get_client_ip(request),
                    related_report=report,
                )
                messages.success(request, 'Report escalated.')

        return redirect('forum_report_detail', report_id=report_id)

    # Get related reports (same user or content)
    related_reports = Report.objects.filter(
        Q(reported_user=report.reported_user) |
        Q(reported_post=report.reported_post) |
        Q(reported_topic=report.reported_topic)
    ).exclude(id=report.id).order_by('-created_at')[:5]

    # Get user's moderation history if reported user exists
    user_history = None
    if report.reported_user:
        user_history = {
            'warnings': UserWarning.get_active_warnings(report.reported_user).count(),
            'muted': UserMute.is_user_muted(report.reported_user),
            'total_reports': Report.objects.filter(reported_user=report.reported_user).count(),
        }

    context = {
        'report': report,
        'related_reports': related_reports,
        'user_history': user_history,
    }

    return render(request, 'forum/admin/report_detail.html', context)


# =============================================================================
# MODERATION VIEWS - STAFF NOTES
# =============================================================================

@staff_required
def user_moderation(request, username):
    """
    User moderation overview page.
    Shows warnings, mutes, reports, and staff notes for a user.
    """
    target_user = get_object_or_404(User.objects.select_related('profile'), username=username)

    # Get user's forum reputation
    reputation = UserReputation.get_or_create_for_user(target_user)

    # Get active warnings and mute
    active_warnings = UserWarning.get_active_warnings(target_user)
    warning_points = UserWarning.get_warning_points(target_user)
    active_mute = UserMute.get_active_mute(target_user)

    # Get recent warnings
    recent_warnings = UserWarning.objects.filter(user=target_user).order_by('-created_at')[:5]

    # Get reports against user
    reports_against = Report.objects.filter(reported_user=target_user).order_by('-created_at')[:5]
    total_reports = Report.objects.filter(reported_user=target_user).count()

    # Get staff notes
    staff_notes = StaffNote.objects.filter(user=target_user).select_related('created_by').order_by('-is_pinned', '-is_important', '-created_at')[:10]

    # Get recent posts for context
    recent_posts = Post.objects.filter(author=target_user).select_related('topic').order_by('-created_at')[:5]

    context = {
        'target_user': target_user,
        'reputation': reputation,
        'active_warnings': active_warnings,
        'warning_points': warning_points,
        'active_mute': active_mute,
        'recent_warnings': recent_warnings,
        'reports_against': reports_against,
        'total_reports': total_reports,
        'staff_notes': staff_notes,
        'recent_posts': recent_posts,
    }

    return render(request, 'forum/admin/user_moderation.html', context)


@staff_required
def add_staff_note(request, username):
    """
    Add a staff note to a user's profile.
    """
    target_user = get_object_or_404(User, username=username)

    if request.method == 'POST':
        note_type = request.POST.get('note_type', 'general')
        content = request.POST.get('content', '').strip()
        is_pinned = request.POST.get('is_pinned') == 'on'
        is_important = request.POST.get('is_important') == 'on'
        related_warning_id = request.POST.get('related_warning_id', '')
        related_report_id = request.POST.get('related_report_id', '')

        # Validate content
        if not content or len(content) < 5:
            messages.error(request, 'Note content must be at least 5 characters.')
            return redirect('forum_add_staff_note', username=username)

        # Validate note type
        valid_types = [t[0] for t in StaffNote.NOTE_TYPES]
        if note_type not in valid_types:
            note_type = 'general'

        # Get related objects
        related_warning = None
        related_report = None
        if related_warning_id:
            try:
                related_warning = UserWarning.objects.get(id=related_warning_id)
            except (UserWarning.DoesNotExist, ValueError):
                pass
        if related_report_id:
            try:
                related_report = Report.objects.get(id=related_report_id)
            except (Report.DoesNotExist, ValueError):
                pass

        with transaction.atomic():
            note = StaffNote.objects.create(
                user=target_user,
                created_by=request.user,
                note_type=note_type,
                content=content,
                is_pinned=is_pinned,
                is_important=is_important,
                related_warning=related_warning,
                related_report=related_report,
            )

            # Log the action
            ModerationLog.log_action(
                moderator=request.user,
                action_type='staff_note_added',
                description=f'Added {note_type} note',
                target_user=target_user,
                ip_address=get_client_ip(request),
            )

        messages.success(request, 'Staff note added.')
        return redirect('forum_user_admin', username=username)

    # Get existing notes
    existing_notes = StaffNote.objects.filter(user=target_user).order_by('-created_at')[:10]

    # Get recent warnings and reports for linking
    recent_warnings = UserWarning.objects.filter(user=target_user).order_by('-created_at')[:5]
    recent_reports = Report.objects.filter(reported_user=target_user).order_by('-created_at')[:5]

    context = {
        'target_user': target_user,
        'existing_notes': existing_notes,
        'recent_warnings': recent_warnings,
        'recent_reports': recent_reports,
        'note_types': StaffNote.NOTE_TYPES,
    }

    return render(request, 'forum/admin/add_staff_note.html', context)


# =============================================================================
# MODERATION VIEWS - DELETED CONTENT
# =============================================================================

@staff_required
def deleted_content_list(request):
    """
    View list of soft-deleted content.
    """
    content_type = request.GET.get('type', '')
    deleted_content = DeletedContent.objects.select_related(
        'original_author', 'deleted_by', 'related_report'
    )

    if content_type:
        deleted_content = deleted_content.filter(content_type=content_type)

    deleted_content = deleted_content.order_by('-created_at')

    paginator = Paginator(deleted_content, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'deleted_content': page_obj,
        'page_obj': page_obj,
        'content_type_filter': content_type,
    }

    return render(request, 'forum/admin/deleted_content.html', context)


@staff_required
def deleted_content_detail(request, content_id):
    """
    View details of deleted content.
    Allows recovery if content is recoverable.
    """
    content = get_object_or_404(DeletedContent, id=content_id)

    if request.method == 'POST' and request.POST.get('action') == 'recover':
        if not content.is_recoverable:
            messages.error(request, 'This content cannot be recovered.')
            return redirect('forum_deleted_content_detail', content_id=content_id)

        if content.recovered:
            messages.info(request, 'This content has already been recovered.')
            return redirect('forum_deleted_content_detail', content_id=content_id)

        # Note: Actual recovery would need to recreate the post/topic
        # This is a simplified version that just marks it as recovered
        with transaction.atomic():
            content.recovered = True
            content.recovered_by = request.user
            content.recovered_at = timezone.now()
            content.save()

            ModerationLog.log_action(
                moderator=request.user,
                action_type='content_recovered',
                description=f'Recovered {content.content_type}: {content.title or str(content.original_id)[:8]}',
                target_user=content.original_author,
                ip_address=get_client_ip(request),
            )

        messages.success(request, 'Content marked as recovered. Manual restoration may be required.')
        return redirect('forum_deleted_content_detail', content_id=content_id)

    context = {
        'content': content,
    }

    return render(request, 'forum/admin/deleted_content_detail.html', context)


# =============================================================================
# MODERATION VIEWS - LOGS AND ANALYTICS
# =============================================================================

@staff_required
def moderation_log(request):
    """
    View moderation action log.
    """
    action_filter = request.GET.get('action', '')
    moderator_filter = request.GET.get('moderator', '')

    logs = ModerationLog.objects.select_related('moderator', 'target_user')

    if action_filter:
        logs = logs.filter(action_type=action_filter)
    if moderator_filter:
        logs = logs.filter(moderator__username=moderator_filter)

    logs = logs.order_by('-created_at')

    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get list of moderators for filter
    moderators = User.objects.filter(is_staff=True).values_list('username', flat=True)

    context = {
        'logs': page_obj,
        'page_obj': page_obj,
        'action_filter': action_filter,
        'moderator_filter': moderator_filter,
        'action_types': ModerationLog.ACTION_TYPES,
        'moderators': moderators,
    }

    return render(request, 'forum/admin/log.html', context)


@staff_required
def report_analytics(request):
    """
    Report analytics dashboard.
    Shows statistics on reports, resolution times, and common issues.
    """
    # Time range filter
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)

    # Reports by type
    reports_by_type = Report.objects.filter(
        created_at__gte=since
    ).values('report_type').annotate(
        count=Count('id')
    ).order_by('-count')

    # Reports by status
    reports_by_status = Report.objects.filter(
        created_at__gte=since
    ).values('status').annotate(
        count=Count('id')
    ).order_by('-count')

    # Most reported users
    most_reported = Report.objects.filter(
        created_at__gte=since,
        reported_user__isnull=False
    ).values('reported_user__username').annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    # Resolution stats
    resolved_reports = Report.objects.filter(
        resolved_at__gte=since,
        resolved_at__isnull=False
    )
    valid_reports = resolved_reports.filter(report_valid=True).count()
    invalid_reports = resolved_reports.filter(report_valid=False).count()

    # Moderator activity
    moderator_activity = ModerationLog.objects.filter(
        created_at__gte=since
    ).values('moderator__username').annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    context = {
        'days': days,
        'reports_by_type': reports_by_type,
        'reports_by_status': reports_by_status,
        'most_reported': most_reported,
        'valid_reports': valid_reports,
        'invalid_reports': invalid_reports,
        'moderator_activity': moderator_activity,
    }

    return render(request, 'forum/admin/analytics.html', context)


