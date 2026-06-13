import json
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from .views import api_success, api_error, api_auth_required, paginate_queryset
from Forum.models import Category, Topic, Post, PostLike, PostBookmark
from Forum.Utils.markdown_utils import render_markdown

@require_http_methods(["GET"])
def categories_view(request):
    """
    List all accessible categories.
    """
    # Categories that are not staff_only, or user is staff
    categories = Category.objects.filter(is_active=True).order_by('order', 'name')
    if not request.user.is_authenticated:
        categories = categories.filter(is_private=False, staff_only=False)
    elif not request.user.is_staff:
        categories = categories.filter(staff_only=False)
        
    data = []
    for cat in categories:
        data.append({
            "id": str(cat.id),
            "name": cat.name,
            "slug": cat.slug,
            "description": cat.description,
            "icon": cat.icon,
            "topic_count": cat.get_topic_count(),
            "is_private": cat.is_private,
        })
    return api_success({"categories": data})

@require_http_methods(["GET", "POST"])
def topics_view(request):
    """
    List topics or create a new topic.
    """
    if request.method == "GET":
        topics = Topic.objects.select_related('author', 'category').annotate(
            reply_count=Count('posts') - 1
        )
        
        # Access control
        if not request.user.is_authenticated:
            topics = topics.filter(category__is_private=False, category__staff_only=False)
        elif not request.user.is_staff:
            topics = topics.filter(category__staff_only=False)

        # Filters
        cat_slug = request.GET.get('category')
        if cat_slug:
            topics = topics.filter(category__slug=cat_slug)
            
        topics = topics.order_by('-is_pinned', '-last_activity')
        paginated = paginate_queryset(topics, request)
        
        data = []
        for t in paginated['items']:
            data.append({
                "id": str(t.id),
                "title": t.title,
                "slug": t.slug,
                "author": t.author.username,
                "category": t.category.name,
                "view_count": t.view_count,
                "reply_count": max(0, t.reply_count),
                "is_pinned": t.is_pinned,
                "is_locked": t.is_locked,
                "created_at": t.created_at.isoformat(),
                "last_activity": t.last_activity.isoformat()
            })
            
        return api_success({
            "topics": data,
            "pagination": paginated['pagination']
        })

    elif request.method == "POST":
        if not request.user.is_authenticated:
            return api_error("Authentication required.", status=401)
            
        try:
            data = json.loads(request.body)
            category_id = data.get("category_id")
            title = str(data.get("title", "")).strip()[:200]
            content = str(data.get("content", "")).strip()[:50000]
        except (json.JSONDecodeError, ValueError, TypeError):
            return api_error("Invalid payload structure.", status=400)
            
        if not category_id or not title or not content:
            return api_error("category_id, title, and content are required.", status=400)
            
        try:
            category = Category.objects.get(id=category_id, is_active=True)
            if not category.user_can_post(request.user):
                return api_error("You cannot post in this category.", status=403)
        except Category.DoesNotExist:
            return api_error("Category not found.", status=404)
            
        topic = Topic.objects.create(category=category, author=request.user, title=title)
        post = Post.objects.create(topic=topic, author=request.user, content=content, ip_address=request.META.get('REMOTE_ADDR'))
        
        return api_success({
            "topic_id": str(topic.id),
            "slug": topic.slug,
            "post_id": str(post.id)
        }, status=201)

@require_http_methods(["GET", "PATCH", "DELETE"])
def topic_detail_view(request, topic_id):
    """
    Get topic with posts, update, or delete.
    """
    topic = get_object_or_404(Topic.objects.select_related('category', 'author'), id=topic_id)
    
    if request.method == "GET":
        if not topic.category.user_can_access(request.user):
            return api_error("You cannot access this topic.", status=403)
            
        topic.increment_view_count()
        posts = topic.posts.select_related('author').filter(is_hidden=False).order_by('created_at')
        paginated = paginate_queryset(posts, request)
        
        posts_data = []
        for p in paginated['items']:
            posts_data.append({
                "id": str(p.id),
                "author": p.author.username,
                "content_html": render_markdown(p.content),
                "is_edited": p.is_edited,
                "like_count": p.get_like_count(),
                "created_at": p.created_at.isoformat()
            })
            
        return api_success({
            "topic": {
                "id": str(topic.id),
                "title": topic.title,
                "author": topic.author.username,
                "category": topic.category.name,
                "is_locked": topic.is_locked,
                "is_pinned": topic.is_pinned,
                "view_count": topic.view_count,
            },
            "posts": posts_data,
            "pagination": paginated['pagination']
        })
        
    elif request.method == "PATCH":
        if not request.user.is_authenticated:
            return api_error("Authentication required.", status=401)
        if request.user != topic.author and not request.user.is_staff:
            return api_error("Permission denied.", status=403)
            
        try:
            data = json.loads(request.body)
            if "title" in data:
                topic.title = str(data["title"]).strip()[:200]
            if request.user.is_staff:
                if "is_locked" in data:
                    topic.is_locked = bool(data["is_locked"])
                if "is_pinned" in data:
                    topic.is_pinned = bool(data["is_pinned"])
            topic.save()
            return api_success({"message": "Topic updated"})
        except json.JSONDecodeError:
            return api_error("Invalid JSON payload", status=400)
            
    elif request.method == "DELETE":
        if not request.user.is_authenticated:
            return api_error("Authentication required.", status=401)
        if request.user != topic.author and not request.user.is_staff:
            return api_error("Permission denied.", status=403)
            
        topic.delete()
        return api_success({"message": "Topic deleted"})

@require_http_methods(["POST"])
@api_auth_required
def topic_reply_view(request, topic_id):
    """
    Reply to a topic.
    """
    topic = get_object_or_404(Topic, id=topic_id)
    if not topic.category.user_can_post(request.user):
        return api_error("You do not have permission to reply.", status=403)
    if topic.is_locked and not request.user.is_staff:
        return api_error("Topic is locked.", status=403)
        
    try:
        data = json.loads(request.body)
        content = str(data.get("content", "")).strip()[:50000]
    except Exception:
        return api_error("Invalid JSON payload", status=400)
        
    if not content:
        return api_error("Content is required", status=400)
        
    post = Post.objects.create(
        topic=topic,
        author=request.user,
        content=content,
        ip_address=request.META.get('REMOTE_ADDR')
    )
    topic.update_last_activity()
    return api_success({"message": "Reply created", "post_id": str(post.id)}, status=201)

@require_http_methods(["GET", "PATCH", "DELETE"])
@api_auth_required
def post_detail_view(request, post_id):
    """
    Get, edit, or delete a post.
    GET: Returns post data for any authenticated user with topic access.
    PATCH/DELETE: Restricted to post author or staff.
    """
    post = get_object_or_404(Post.objects.select_related('author', 'topic', 'topic__category'), id=post_id)

    if request.method == "GET":
        if not post.topic.category.user_can_access(request.user):
            return api_error("You cannot access this post.", status=403)
        return api_success({
            "id": str(post.id),
            "topic_id": str(post.topic.id),
            "author": post.author.username,
            "content_html": render_markdown(post.content),
            "is_edited": post.is_edited,
            "edited_at": post.edited_at.isoformat() if post.edited_at else None,
            "like_count": post.get_like_count(),
            "is_hidden": post.is_hidden,
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat(),
        })

    if request.user != post.author and not request.user.is_staff:
        return api_error("Permission denied.", status=403)
        
    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
            content = str(data.get("content", "")).strip()[:50000]
            reason = str(data.get("reason", "")).strip()
        except:
            return api_error("Invalid payload", status=400)
        
        if content:
            post.content = content
            post.mark_edited(reason)
            return api_success({"message": "Post updated"})
        return api_error("Content required", status=400)
        
    elif request.method == "DELETE":
        topic = post.topic
        if topic.posts.count() <= 1:
            return api_error("Cannot delete the only post. Delete the topic instead.", status=400)
        post.delete()
        return api_success({"message": "Post deleted"})

@require_http_methods(["POST"])
@api_auth_required
def toggle_like_view(request, post_id):
    """
    Toggle like on a post.
    """
    post = get_object_or_404(Post, id=post_id)
    like_qs = PostLike.objects.filter(post=post, user=request.user)
    if like_qs.exists():
        like_qs.delete()
        status = "unliked"
    else:
        PostLike.objects.create(post=post, user=request.user)
        status = "liked"
        
    return api_success({"message": f"Post {status}", "like_count": post.get_like_count()})

@require_http_methods(["GET"])
def forum_search_view(request):
    """
    Search forum posts and topics.
    """
    query = request.GET.get('q', '').strip()
    if not query:
        return api_error("Query 'q' is required for search.", status=400)
        
    posts = Post.objects.select_related('topic', 'author').filter(
        Q(content__icontains=query) | Q(topic__title__icontains=query),
        is_hidden=False
    )
    
    # Access control
    if not request.user.is_authenticated:
        posts = posts.filter(topic__category__is_private=False, topic__category__staff_only=False)
    elif not request.user.is_staff:
        posts = posts.filter(topic__category__staff_only=False)
        
    posts = posts.order_by('-created_at')
    paginated = paginate_queryset(posts, request)
    
    data = []
    for p in paginated['items']:
        data.append({
            "post_id": str(p.id),
            "topic_id": str(p.topic.id),
            "topic_title": p.topic.title,
            "author": p.author.username,
            "snippet": p.content[:200] + ("..." if len(p.content) > 200 else ""),
            "created_at": p.created_at.isoformat()
        })
        
    return api_success({
        "results": data,
        "pagination": paginated['pagination'],
        "query": query
    })

from Forum.models import Tag, TopicTag, ForumNotification, UserReputation
from django.db.models import Sum

@require_http_methods(["GET"])
def tags_view(request):
    """
    List all tags with topic counts.
    """
    tags = Tag.objects.annotate(topic_count=Count('tagged_topics')).order_by('-topic_count')
    paginated = paginate_queryset(tags, request)
    data = []
    for t in paginated['items']:
        data.append({
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "topic_count": t.topic_count
        })
    return api_success({
        "tags": data,
        "pagination": paginated['pagination']
    })

@require_http_methods(["GET"])
@api_auth_required
def notifications_view(request):
    """
    List or mark notifications as read.
    GET /api/forum/notifications/ - List unread notifications
    POST /api/forum/notifications/read-all/ - Mark all as read
    """
    if request.method == "GET":
        notifs = ForumNotification.objects.filter(recipient=request.user, is_read=False).order_by('-created_at')
        paginated = paginate_queryset(notifs, request)
        data = []
        for n in paginated['items']:
            data.append({
                "id": str(n.id),
                "type": n.notification_type,
                "message": n.message,
                "link": n.link,
                "created_at": n.created_at.isoformat()
            })
        return api_success({
            "notifications": data,
            "pagination": paginated['pagination']
        })
        
@require_http_methods(["POST"])
@api_auth_required
def notifications_read_all_view(request):
    """POST-only alias that marks all forum notifications as read."""
    ForumNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return api_success({"message": "All notifications marked as read."})

from django.contrib.auth.models import User

@require_http_methods(["GET"])
def statistics_view(request):
    """
    Forum-wide statistics.
    """
    total_topics = Topic.objects.count()
    total_posts = Post.objects.count()
    total_users = User.objects.filter(forum_posts__isnull=False).distinct().count()
    popular_tags = Tag.objects.annotate(topic_count=Count('tagged_topics')).order_by('-topic_count')[:10]
    
    tags_data = [{"slug": t.slug, "name": t.name, "count": t.topic_count} for t in popular_tags]
    
    return api_success({
        "statistics": {
            "topics": total_topics,
            "posts": total_posts,
            "users": total_users,
            "popular_tags": tags_data
        }
    })


@require_http_methods(["GET"])
@api_auth_required
def bookmarks_view(request):
    """
    List the current user's bookmarked posts.
    """
    bookmarks = PostBookmark.objects.filter(user=request.user).select_related(
        'post', 'post__topic', 'post__author'
    ).order_by('-created_at')

    paginated = paginate_queryset(bookmarks, request, default_per_page=20)

    data = []
    for bm in paginated['items']:
        post = bm.post
        data.append({
            'id': str(bm.id),
            'note': bm.note,
            'created_at': bm.created_at.isoformat(),
            'post': {
                'id': str(post.id),
                'snippet': post.content[:200] if post.content else '',
                'author': post.author.username if post.author else None,
                'topic_id': str(post.topic.id) if post.topic else None,
                'topic_title': post.topic.title if post.topic else None,
                'created_at': post.created_at.isoformat() if post.created_at else None,
            },
        })

    return api_success({'bookmarks': data, 'pagination': paginated['pagination']})


@require_http_methods(["POST"])
@api_auth_required
def toggle_bookmark_view(request, post_id):
    """
    Toggle bookmark on a post.
    POST body (optional): {"note": "optional personal note"}
    Returns the new bookmark state.
    """
    post = get_object_or_404(Post, id=post_id)

    existing = PostBookmark.objects.filter(user=request.user, post=post).first()
    if existing:
        existing.delete()
        return api_success({'bookmarked': False}, message="Bookmark removed.")

    note = ''
    try:
        body = json.loads(request.body)
        note = str(body.get('note', ''))[:500]
    except (json.JSONDecodeError, TypeError):
        pass

    bm = PostBookmark.objects.create(user=request.user, post=post, note=note)
    return api_success({
        'bookmarked': True,
        'bookmark_id': str(bm.id),
    }, message="Post bookmarked.", status=201)


@require_http_methods(["GET"])
def reputation_view(request, username):
    """
    Get forum reputation for a user.
    Public endpoint — no authentication required.
    """
    from django.contrib.auth.models import User as AuthUser
    try:
        target = AuthUser.objects.get(username=username)
    except AuthUser.DoesNotExist:
        return api_error("User not found.", status=404)

    rep = UserReputation.get_or_create_for_user(target)
    return api_success({
        "username": target.username,
        "reputation_points": rep.reputation_points,
        "posts_count": rep.posts_count,
        "topics_count": rep.topics_count,
        "likes_received": rep.likes_received,
        "likes_given": rep.likes_given,
        "rank": rep.get_rank(),
    })


@require_http_methods(["GET"])
def tag_topics_view(request, slug):
    """
    List topics for a given tag slug.
    Respects the same category access controls as the main topics list.
    """
    tag = get_object_or_404(Tag, slug=slug)

    topic_ids = TopicTag.objects.filter(tag=tag).values_list('topic_id', flat=True)
    topics = Topic.objects.filter(id__in=topic_ids).select_related('author', 'category').annotate(
        reply_count=Count('posts') - 1
    )

    if not request.user.is_authenticated:
        topics = topics.filter(category__is_private=False, category__staff_only=False)
    elif not request.user.is_staff:
        topics = topics.filter(category__staff_only=False)

    topics = topics.order_by('-is_pinned', '-last_activity')
    paginated = paginate_queryset(topics, request)

    data = []
    for t in paginated['items']:
        data.append({
            "id": str(t.id),
            "title": t.title,
            "slug": t.slug,
            "author": t.author.username,
            "category": t.category.name,
            "view_count": t.view_count,
            "reply_count": max(0, t.reply_count),
            "is_pinned": t.is_pinned,
            "is_locked": t.is_locked,
            "created_at": t.created_at.isoformat(),
            "last_activity": t.last_activity.isoformat(),
        })

    return api_success({
        "tag": {"name": tag.name, "slug": tag.slug},
        "topics": data,
        "pagination": paginated['pagination'],
    })
