"""
Forum module view extensions for announcements, bulk moderation, and new features.

All views follow secure coding practices with proper
authentication, authorization, and input validation.

New Features:
- Post Bookmarks (toggle, list, manage)
- Tag System (add, remove, filter, autocomplete)
- @Mentions (parse, notify, autocomplete)
- Quote Functionality (pre-fill reply with quote)
- User Blocking (block/unblock, manage blocked users)
- Sticky Posts (pin replies within topics)
- Image Uploads (upload, moderate)
- Advanced Search (date range, author, category, tags)
- Forum Statistics (analytics dashboard)
- RSS Feeds (per-category, per-user)
- Social Sharing (share topics)
- Reputation Decay (management command support)
- Notifications (list, mark read, API)
"""
import re
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.validators import validate_image_file_extension
from django.db import transaction
from django.db.models import Count, Q, Max, Sum, F
from django.db.models.functions import Greatest
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.utils.feedgenerator import Rss201rev2Feed
from django.utils.html import escape
from django.utils.text import slugify
from datetime import timedelta

from .models import (
    Category, Topic, Post, UserReputation,
    ModerationLog, DeletedContent, PostLike,
    Tag, TopicTag, PostBookmark, Mention, UserBlock,
    StickyPost, ForumImage, ForumRole, ForumNotification,
    ReputationDecayLog, UserWarning, UserMute
)
from .Utils.markdown_utils import render_markdown
from .Utils.email_utils import send_mention_notification_email


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
# BULK MODERATION VIEWS
# =============================================================================

@staff_required
def bulk_moderation(request):
    """
    Bulk moderation interface for mass actions.
    """
    category_filter = request.GET.get('category', '')
    author_filter = request.GET.get('author', '')

    posts = Post.objects.select_related('author', 'topic', 'topic__category')

    if category_filter:
        posts = posts.filter(topic__category__slug=category_filter)
    if author_filter:
        posts = posts.filter(author__username=author_filter)

    posts = posts.order_by('-created_at')

    paginator = Paginator(posts, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.filter(is_active=True).order_by('name')

    context = {
        'posts': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'category_filter': category_filter,
        'author_filter': author_filter,
    }

    return render(request, 'forum/admin/bulk_moderation.html', context)


@staff_required
@require_POST
def bulk_action(request):
    """
    Execute bulk moderation action on selected posts.
    Supports hide, delete, and move operations.
    """
    action = request.POST.get('action', '')
    post_ids = request.POST.getlist('post_ids[]')
    reason = request.POST.get('reason', '').strip()

    if not post_ids:
        return JsonResponse({'success': False, 'error': 'No posts selected'})

    if not action or action not in ['hide', 'delete', 'lock_topics']:
        return JsonResponse({'success': False, 'error': 'Invalid action'})

    # Get selected posts
    posts = Post.objects.filter(id__in=post_ids).select_related('topic', 'author')

    if not posts.exists():
        return JsonResponse({'success': False, 'error': 'No valid posts found'})

    count = posts.count()

    with transaction.atomic():
        if action == 'hide':
            # Hide all selected posts
            for post in posts:
                post.is_hidden = True
                post.hidden_by = request.user
                post.hidden_reason = reason[:200] if reason else 'Bulk moderation'
                post.save()

                ModerationLog.log_action(
                    moderator=request.user,
                    action_type='post_hidden',
                    description=f'Bulk hide: {reason[:100]}',
                    target_user=post.author,
                    target_post_id=post.id,
                    ip_address=get_client_ip(request)
                )

            return JsonResponse({
                'success': True,
                'message': f'{count} post(s) hidden successfully'
            })

        elif action == 'delete':
            # Delete all selected posts with soft delete
            deletion_reason = 'moderation' if not reason else 'moderation'
            for post in posts:
                # Create soft delete record
                DeletedContent.create_from_post(
                    post=post,
                    deleted_by=request.user,
                    reason=deletion_reason,
                    notes=f'Bulk deletion: {reason[:500]}'
                )

                # Log the moderation action
                ModerationLog.log_action(
                    moderator=request.user,
                    action_type='post_deleted',
                    description=f'Bulk delete: {reason[:100]}',
                    target_user=post.author,
                    target_post_id=post.id,
                    ip_address=get_client_ip(request)
                )

                post.delete()

            return JsonResponse({
                'success': True,
                'message': f'{count} post(s) deleted successfully'
            })

        elif action == 'lock_topics':
            # Lock all topics containing selected posts
            topics = set(post.topic for post in posts)
            locked_count = 0

            for topic in topics:
                if not topic.is_locked:
                    topic.is_locked = True
                    topic.save(update_fields=['is_locked'])
                    locked_count += 1

                    ModerationLog.log_action(
                        moderator=request.user,
                        action_type='topic_locked',
                        description=f'Bulk lock: {reason[:100]}',
                        target_user=topic.author,
                        target_topic_id=topic.id,
                        ip_address=get_client_ip(request)
                    )

            return JsonResponse({
                'success': True,
                'message': f'{locked_count} topic(s) locked successfully'
            })

    return JsonResponse({'success': False, 'error': 'Unknown error occurred'})


# =============================================================================
# BOOKMARK VIEWS
# =============================================================================

@login_required
@require_POST
def toggle_bookmark(request, post_id):
    """
    Toggle bookmark on a post.
    Uses atomic transactions and proper validation.
    """
    post = get_object_or_404(Post, id=post_id)
    note = request.POST.get('note', '').strip()[:500]

    existing = PostBookmark.objects.filter(user=request.user, post=post).first()

    if existing:
        existing.delete()
        bookmarked = False
    else:
        PostBookmark.objects.create(
            user=request.user,
            post=post,
            note=note
        )
        bookmarked = True

    # Return JSON for AJAX or redirect
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'bookmarked': bookmarked,
            'bookmark_count': post.bookmarks.count(),
        })

    if bookmarked:
        messages.success(request, 'Post bookmarked.')
    else:
        messages.success(request, 'Bookmark removed.')
    return redirect(post.get_absolute_url())


@login_required
def bookmark_list(request):
    """
    Display user's bookmarked posts.
    Only shows the current user's bookmarks.
    """
    bookmarks = PostBookmark.objects.filter(
        user=request.user
    ).select_related(
        'post', 'post__topic', 'post__topic__category', 'post__author'
    ).order_by('-created_at')

    paginator = Paginator(bookmarks, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'bookmarks': page_obj,
        'page_obj': page_obj,
    }

    return render(request, 'forum/bookmarks.html', context)


# =============================================================================
# TAG SYSTEM VIEWS
# =============================================================================

@login_required
@require_POST
def add_tag_to_topic(request, topic_id):
    """
    Add a tag to a topic.
    Topic authors and staff can add tags. Max 5 tags per topic.
    """
    topic = get_object_or_404(Topic, id=topic_id)

    if topic.author != request.user and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'})

    tag_name = request.POST.get('tag', '').strip().lower()

    if not tag_name or len(tag_name) < 2 or len(tag_name) > 50:
        return JsonResponse({'success': False, 'error': 'Tag must be 2-50 characters'})

    # Sanitize: only allow alphanumeric, hyphens, underscores
    if not re.match(r'^[a-z0-9][a-z0-9\-_]*$', tag_name):
        return JsonResponse({'success': False, 'error': 'Tags can only contain letters, numbers, hyphens, and underscores'})

    # Check tag limit per topic
    current_count = TopicTag.objects.filter(topic=topic).count()
    if current_count >= 5:
        return JsonResponse({'success': False, 'error': 'Maximum 5 tags per topic'})

    with transaction.atomic():
        tag, created = Tag.objects.get_or_create(
            name=tag_name,
            defaults={
                'slug': slugify(tag_name),
                'created_by': request.user,
            }
        )

        topic_tag, tt_created = TopicTag.objects.get_or_create(
            topic=topic,
            tag=tag,
            defaults={'added_by': request.user}
        )

        if not tt_created:
            return JsonResponse({'success': False, 'error': 'Tag already added'})

        # Update usage count
        Tag.objects.filter(pk=tag.pk).update(usage_count=F('usage_count') + 1)

    return JsonResponse({
        'success': True,
        'tag': {
            'id': str(tag.id),
            'name': tag.name,
            'slug': tag.slug,
            'color': tag.color,
        }
    })


@login_required
@require_POST
def remove_tag_from_topic(request, topic_id, tag_id):
    """
    Remove a tag from a topic.
    """
    topic = get_object_or_404(Topic, id=topic_id)

    if topic.author != request.user and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'})

    topic_tag = TopicTag.objects.filter(topic=topic, tag_id=tag_id).first()
    if topic_tag:
        tag = topic_tag.tag
        topic_tag.delete()
        # Update usage count
        Tag.objects.filter(pk=tag.pk).update(
            usage_count=Greatest(F('usage_count') - 1, 0)
        )
        return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'error': 'Tag not found on this topic'})


def topics_by_tag(request, tag_slug):
    """
    List topics filtered by tag.
    """
    tag = get_object_or_404(Tag, slug=tag_slug)

    topics = Topic.objects.filter(
        topic_tags__tag=tag
    ).select_related(
        'category', 'author'
    ).annotate(
        reply_count=Count('posts') - 1,
        last_post_date=Max('posts__created_at')
    ).order_by('-last_activity')

    paginator = Paginator(topics, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'tag': tag,
        'topics': page_obj,
        'page_obj': page_obj,
    }

    return render(request, 'forum/topics_by_tag.html', context)


def tag_autocomplete(request):
    """
    Tag autocomplete API endpoint.
    Returns matching tags for autocomplete suggestions.
    """
    query = request.GET.get('q', '').strip().lower()[:50]
    if not query or len(query) < 1:
        return JsonResponse({'tags': []})

    tags = Tag.objects.filter(
        name__icontains=query
    ).order_by('-usage_count')[:10]

    return JsonResponse({
        'tags': [
            {
                'id': str(t.id),
                'name': t.name,
                'slug': t.slug,
                'color': t.color,
                'usage_count': t.usage_count,
            }
            for t in tags
        ]
    })


# =============================================================================
# MENTION VIEWS
# =============================================================================

def mention_autocomplete(request):
    """
    User mention autocomplete API.
    Returns matching usernames for @mention autocomplete.
    """
    query = request.GET.get('q', '').strip()[:50]
    if not query or len(query) < 1:
        return JsonResponse({'users': []})

    users = User.objects.filter(
        username__icontains=query,
        is_active=True
    ).values('username')[:10]

    return JsonResponse({
        'users': [
            {'username': u['username']}
            for u in users
        ]
    })


def parse_mentions(content, post, author):
    """
    Parse @mentions from post content and create notifications.
    Extracts @username patterns and creates Mention records.
    Limits to 10 mentions per post to prevent abuse.
    """
    mention_pattern = re.compile(r'@([a-zA-Z0-9_-]{1,150})\b')
    found_usernames = set(mention_pattern.findall(content))

    # Limit mentions per post
    mentioned_count = 0
    for username in found_usernames:
        if mentioned_count >= 10:
            break

        try:
            mentioned_user = User.objects.get(username=username, is_active=True)
        except User.DoesNotExist:
            continue

        # Don't mention yourself
        if mentioned_user == author:
            continue

        # Create mention record
        Mention.objects.get_or_create(
            post=post,
            mentioned_user=mentioned_user,
            defaults={'mentioned_by': author}
        )

        # Create notification
        ForumNotification.create_notification(
            recipient=mentioned_user,
            notification_type='mention',
            message=f'@{author.username} mentioned you in "{post.topic.title}"',
            sender=author,
            link=post.get_absolute_url(),
            related_post=post,
            related_topic=post.topic,
        )

        send_mention_notification_email(
            mentioned_user=mentioned_user,
            mentioner_username=author.username,
            topic_title=post.topic.title,
            post_url=post.get_absolute_url(),
        )
        mentioned_count += 1


# =============================================================================
# QUOTE FUNCTIONALITY
# =============================================================================

@login_required
def quote_post(request, post_id):
    """
    Generate a quote block for a post.
    Returns the quoted text that can be inserted into a reply.
    """
    post = get_object_or_404(
        Post.objects.select_related('author', 'topic'),
        id=post_id
    )

    # Format as markdown blockquote
    quoted_lines = post.content.split('\n')
    quoted_content = '\n'.join(f'> {line}' for line in quoted_lines)
    quote_text = f'> **{escape(post.author.username)}** wrote:\n{quoted_content}\n\n'

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'quote_text': quote_text,
            'author': post.author.username,
        })

    # For non-AJAX, redirect to the topic with quote pre-filled
    return redirect(f"{post.topic.get_absolute_url()}?quote={post.id}#reply-form")


# =============================================================================
# USER BLOCKING VIEWS
# =============================================================================

@login_required
@require_POST
def toggle_block_user(request, username):
    """
    Toggle block on a user.
    Cannot block staff or yourself.
    """
    target_user = get_object_or_404(User, username=username)

    # Cannot block yourself
    if target_user == request.user:
        return JsonResponse({'success': False, 'error': 'Cannot block yourself'})

    # Cannot block staff members
    if target_user.is_staff:
        return JsonResponse({'success': False, 'error': 'Cannot block staff members'})

    reason = request.POST.get('reason', '').strip()[:200]

    existing = UserBlock.objects.filter(
        blocker=request.user, blocked=target_user
    ).first()

    if existing:
        existing.delete()
        blocked = False
    else:
        UserBlock.objects.create(
            blocker=request.user,
            blocked=target_user,
            reason=reason,
        )
        blocked = True

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'blocked': blocked,
        })

    if blocked:
        messages.success(request, f'You have blocked {target_user.username}. Their posts will be hidden from your view.')
    else:
        messages.success(request, f'You have unblocked {target_user.username}.')

    return redirect(request.META.get('HTTP_REFERER', 'forum_index'))


@login_required
def blocked_users_list(request):
    """
    Display list of users the current user has blocked.
    """
    blocked = UserBlock.objects.filter(
        blocker=request.user
    ).select_related('blocked').order_by('-created_at')

    context = {
        'blocked_users': blocked,
    }

    return render(request, 'forum/blocked_users.html', context)


# =============================================================================
# STICKY POST VIEWS
# =============================================================================

@staff_required
@require_POST
def toggle_sticky_post(request, post_id):
    """
    Toggle sticky status on a post within a topic.
    Only staff can pin/unpin posts.
    """
    post = get_object_or_404(Post, id=post_id)
    reason = request.POST.get('reason', '').strip()[:200]

    existing = StickyPost.objects.filter(post=post).first()

    if existing:
        existing.delete()
        is_sticky = False
    else:
        StickyPost.objects.create(
            post=post,
            pinned_by=request.user,
            reason=reason,
        )
        is_sticky = True

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'is_sticky': is_sticky,
        })

    if is_sticky:
        messages.success(request, 'Post pinned to top of topic.')
    else:
        messages.success(request, 'Post unpinned.')

    return redirect(post.get_absolute_url())


# =============================================================================
# IMAGE UPLOAD VIEWS
# =============================================================================

@login_required
@require_POST
def upload_image(request):
    """
    Upload an image for use in forum posts.
    Validates file type, size, and creates a moderation record.
    """
    if 'image' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'No image file provided'})

    image_file = request.FILES['image']

    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if image_file.content_type not in allowed_types:
        return JsonResponse({'success': False, 'error': 'Only JPEG, PNG, GIF, and WebP images are allowed'})

    max_size = 5 * 1024 * 1024
    if image_file.size > max_size:
        return JsonResponse({'success': False, 'error': 'Image must be under 5MB'})

    allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    _, ext = os.path.splitext(image_file.name)
    if ext.lower() not in allowed_extensions:
        return JsonResponse({'success': False, 'error': 'Invalid file extension'})

    alt_text = request.POST.get('alt_text', '').strip()[:200]

    forum_image = ForumImage.objects.create(
        uploaded_by=request.user,
        image=image_file,
        original_filename=image_file.name[:255],
        file_size=image_file.size,
        alt_text=alt_text,
        status='approved',
    )

    return JsonResponse({
        'success': True,
        'image_url': forum_image.get_url(),
        'image_id': str(forum_image.id),
        'markdown': f'![{escape(alt_text or "image")}]({forum_image.get_url()})',
    })


# =============================================================================
# ADVANCED SEARCH VIEW
# =============================================================================

def advanced_search(request):
    """
    Advanced search with multiple filter options.
    Uses Django ORM with parameterized queries to prevent SQL injection.
    """
    query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'all')
    author = request.GET.get('author', '').strip()
    category_slug = request.GET.get('category', '').strip()
    tag_slug = request.GET.get('tag', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    sort_by = request.GET.get('sort', 'relevance')

    results = []
    total_count = 0

    if query or author or category_slug or tag_slug:
        # Build topic search
        if search_type in ('all', 'topics'):
            topic_qs = Topic.objects.select_related('category', 'author')

            if query:
                topic_qs = topic_qs.filter(title__icontains=query)
            if author:
                topic_qs = topic_qs.filter(author__username__icontains=author)
            if category_slug:
                topic_qs = topic_qs.filter(category__slug=category_slug)
            if tag_slug:
                topic_qs = topic_qs.filter(topic_tags__tag__slug=tag_slug)
            if date_from:
                try:
                    from_date = timezone.datetime.fromisoformat(date_from)
                    topic_qs = topic_qs.filter(created_at__gte=from_date)
                except (ValueError, TypeError):
                    pass
            if date_to:
                try:
                    to_date = timezone.datetime.fromisoformat(date_to)
                    topic_qs = topic_qs.filter(created_at__lte=to_date)
                except (ValueError, TypeError):
                    pass

            # Sort
            if sort_by == 'newest':
                topic_qs = topic_qs.order_by('-created_at')
            elif sort_by == 'oldest':
                topic_qs = topic_qs.order_by('created_at')
            elif sort_by == 'views':
                topic_qs = topic_qs.order_by('-view_count')
            else:
                topic_qs = topic_qs.order_by('-last_activity')

            for topic in topic_qs[:50]:
                tags = list(
                    TopicTag.objects.filter(topic=topic).select_related('tag').values_list('tag__name', flat=True)
                )
                results.append({
                    'id': str(topic.id),
                    'title': topic.title,
                    'type': 'topic',
                    'category': topic.category.name,
                    'category_slug': topic.category.slug,
                    'author': topic.author.username,
                    'created_at': topic.created_at,
                    'view_count': topic.view_count,
                    'tags': tags,
                })

        # Build post search
        if search_type in ('all', 'posts') and query:
            post_qs = Post.objects.filter(
                content__icontains=query
            ).select_related('topic', 'topic__category', 'author')

            if author:
                post_qs = post_qs.filter(author__username__icontains=author)
            if category_slug:
                post_qs = post_qs.filter(topic__category__slug=category_slug)
            if date_from:
                try:
                    from_date = timezone.datetime.fromisoformat(date_from)
                    post_qs = post_qs.filter(created_at__gte=from_date)
                except (ValueError, TypeError):
                    pass
            if date_to:
                try:
                    to_date = timezone.datetime.fromisoformat(date_to)
                    post_qs = post_qs.filter(created_at__lte=to_date)
                except (ValueError, TypeError):
                    pass

            if sort_by == 'newest':
                post_qs = post_qs.order_by('-created_at')
            elif sort_by == 'oldest':
                post_qs = post_qs.order_by('created_at')
            else:
                post_qs = post_qs.order_by('-created_at')

            for post in post_qs[:50]:
                results.append({
                    'id': str(post.id),
                    'title': f'Reply in: {post.topic.title}',
                    'type': 'post',
                    'topic_id': str(post.topic.id),
                    'category': post.topic.category.name,
                    'author': post.author.username,
                    'excerpt': post.content[:200] + '...' if len(post.content) > 200 else post.content,
                    'created_at': post.created_at,
                })

        total_count = len(results)

    # Get categories and tags for filter dropdowns
    categories = Category.objects.filter(is_active=True).order_by('name')
    popular_tags = Tag.objects.order_by('-usage_count')[:20]

    context = {
        'query': escape(query),
        'search_type': search_type,
        'author_filter': escape(author),
        'category_filter': category_slug,
        'tag_filter': tag_slug,
        'date_from': date_from,
        'date_to': date_to,
        'sort_by': sort_by,
        'results': results,
        'total_count': total_count,
        'categories': categories,
        'popular_tags': popular_tags,
    }

    return render(request, 'forum/advanced_search.html', context)


# =============================================================================
# FORUM STATISTICS VIEW
# =============================================================================

@login_required
def forum_statistics(request):
    """
    Advanced analytics dashboard for the forum.
    Shows active users, post frequency, engagement metrics.
    """
    days = int(request.GET.get('days', 30))
    days = min(max(days, 7), 365)
    since = timezone.now() - timedelta(days=days)

    # Overall stats
    overall = {
        'total_topics': Topic.objects.count(),
        'total_posts': Post.objects.count(),
        'total_users': UserReputation.objects.count(),
        'total_likes': PostLike.objects.count(),
    }

    # Period stats
    period = {
        'new_topics': Topic.objects.filter(created_at__gte=since).count(),
        'new_posts': Post.objects.filter(created_at__gte=since).count(),
        'new_users': UserReputation.objects.filter(created_at__gte=since).count(),
        'new_likes': PostLike.objects.filter(created_at__gte=since).count(),
    }

    # Most active categories
    active_categories = Category.objects.filter(
        is_active=True
    ).annotate(
        recent_posts=Count('topics__posts', filter=Q(topics__posts__created_at__gte=since)),
        recent_topics=Count('topics', filter=Q(topics__created_at__gte=since)),
    ).order_by('-recent_posts')[:10]

    # Top contributors
    top_contributors = UserReputation.objects.select_related(
        'user'
    ).order_by('-reputation_points')[:10]

    # Most active posters (in period)
    active_posters = Post.objects.filter(
        created_at__gte=since
    ).values('author__username').annotate(
        post_count=Count('id')
    ).order_by('-post_count')[:10]

    # Popular topics (most viewed in period)
    popular_topics = Topic.objects.filter(
        created_at__gte=since
    ).order_by('-view_count')[:10]

    # Most liked posts
    most_liked = Post.objects.annotate(
        like_count=Count('likes')
    ).filter(
        created_at__gte=since,
        like_count__gt=0
    ).select_related('topic', 'author').order_by('-like_count')[:10]

    # Popular tags
    popular_tags = Tag.objects.order_by('-usage_count')[:15]

    context = {
        'days': days,
        'overall': overall,
        'period': period,
        'active_categories': active_categories,
        'top_contributors': top_contributors,
        'active_posters': active_posters,
        'popular_topics': popular_topics,
        'most_liked': most_liked,
        'popular_tags': popular_tags,
    }

    return render(request, 'forum/statistics.html', context)


# =============================================================================
# RSS FEED VIEWS
# =============================================================================

def rss_feed_latest(request):
    """
    RSS feed for latest forum topics.
    """
    feed = Rss201rev2Feed(
        title='V.R.C Forum - Latest Topics',
        link='/forum/',
        description='Latest topics from the V.R.C Community Forum',
        language='en',
    )

    topics = Topic.objects.select_related(
        'category', 'author'
    ).order_by('-created_at')[:20]

    for topic in topics:
        first_post = topic.get_first_post()
        description = ''
        if first_post:
            description = first_post.content[:500]

        feed.add_item(
            title=topic.title,
            link=f'/forum/topic/{topic.id}/',
            description=escape(description),
            author_name=topic.author.username,
            pubdate=topic.created_at,
            categories=[topic.category.name],
        )

    response = HttpResponse(content_type='application/rss+xml; charset=utf-8')
    feed.write(response, 'utf-8')
    return response


def rss_feed_category(request, slug):
    """
    RSS feed for a specific category.
    """
    category = get_object_or_404(Category, slug=slug, is_active=True)

    # Do not expose private/staff-only categories via RSS
    if category.is_private or category.staff_only:
        return HttpResponse('Feed not available for this category.', status=403)

    feed = Rss201rev2Feed(
        title=f'V.R.C Forum - {category.name}',
        link=f'/forum/category/{category.slug}/',
        description=f'Latest topics in {category.name}',
        language='en',
    )

    topics = Topic.objects.filter(
        category=category
    ).select_related('author').order_by('-created_at')[:20]

    for topic in topics:
        first_post = topic.get_first_post()
        description = ''
        if first_post:
            description = first_post.content[:500]

        feed.add_item(
            title=topic.title,
            link=f'/forum/topic/{topic.id}/',
            description=escape(description),
            author_name=topic.author.username,
            pubdate=topic.created_at,
        )

    response = HttpResponse(content_type='application/rss+xml; charset=utf-8')
    feed.write(response, 'utf-8')
    return response


# =============================================================================
# SOCIAL SHARING VIEW
# =============================================================================

def social_share(request, topic_id):
    """
    Generate social sharing data for a topic.
    Returns metadata for social sharing cards.
    """
    topic = get_object_or_404(
        Topic.objects.select_related('category', 'author'),
        id=topic_id
    )

    first_post = topic.get_first_post()
    description = ''
    if first_post:
        description = first_post.content[:200]

    share_data = {
        'title': topic.title,
        'description': escape(description),
        'author': topic.author.username,
        'category': topic.category.name,
        'url': request.build_absolute_uri(topic.get_absolute_url()),
        'share_urls': {
            'twitter': f"https://twitter.com/intent/tweet?text={escape(topic.title)}&url={request.build_absolute_uri(topic.get_absolute_url())}",
            'facebook': f"https://www.facebook.com/sharer/sharer.php?u={request.build_absolute_uri(topic.get_absolute_url())}",
            'linkedin': f"https://www.linkedin.com/sharing/share-offsite/?url={request.build_absolute_uri(topic.get_absolute_url())}",
        }
    }

    return JsonResponse(share_data)


# =============================================================================
# NOTIFICATION VIEWS
# =============================================================================

@login_required
def notification_list(request):
    """
    Display user's forum notifications.
    Only shows notifications for the current user.
    """
    notifications = ForumNotification.objects.filter(
        recipient=request.user
    ).select_related('sender').order_by('-created_at')

    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    unread_count = ForumNotification.get_unread_count(request.user)

    context = {
        'notifications': page_obj,
        'page_obj': page_obj,
        'unread_count': unread_count,
    }

    return render(request, 'forum/notifications.html', context)


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """
    Mark a notification as read.
    Verifies ownership before marking.
    """
    notification = get_object_or_404(
        ForumNotification,
        id=notification_id,
        recipient=request.user
    )
    notification.mark_read()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    if notification.link:
        return redirect(notification.link)
    return redirect('forum_notifications')


@login_required
@require_POST
def mark_all_notifications_read(request):
    """
    Mark all notifications as read for the current user.
    """
    ForumNotification.objects.filter(
        recipient=request.user,
        is_read=False
    ).update(
        is_read=True,
        read_at=timezone.now()
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    messages.success(request, 'All notifications marked as read.')
    return redirect('forum_notifications')


@login_required
def notification_count_api(request):
    """
    API endpoint to get unread notification count.
    For use in AJAX polling from the header.
    """
    count = ForumNotification.get_unread_count(request.user)
    return JsonResponse({'unread_count': count})


# =============================================================================
# REPUTATION DECAY
# =============================================================================

def apply_reputation_decay():
    """
    Apply reputation point decay for inactive users.
    Called by a management command or scheduled task.
    Users who have not posted in 30+ days lose 5% of their reputation.
    Minimum reputation is 0.
    """
    threshold = timezone.now() - timedelta(days=30)

    # Find users whose last post was before the threshold
    active_user_ids = set(
        Post.objects.filter(
            created_at__gte=threshold
        ).values_list('author_id', flat=True).distinct()
    )

    inactive_reputations = UserReputation.objects.filter(
        reputation_points__gt=0
    ).exclude(
        user_id__in=active_user_ids
    )

    decayed_count = 0
    for rep in inactive_reputations:
        decay_amount = max(1, int(rep.reputation_points * 0.05))
        points_before = rep.reputation_points
        points_after = max(0, rep.reputation_points - decay_amount)

        if points_before != points_after:
            ReputationDecayLog.objects.create(
                user=rep.user,
                points_before=points_before,
                points_after=points_after,
                points_decayed=points_before - points_after,
                reason='Monthly inactivity decay (5%)',
            )

            rep.reputation_points = points_after
            rep.save(update_fields=['reputation_points', 'updated_at'])
            decayed_count += 1

    return decayed_count
