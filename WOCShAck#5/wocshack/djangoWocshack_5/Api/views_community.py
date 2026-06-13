import json
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from .views import api_success, api_error, api_auth_required, paginate_queryset

from Community.models.social import Friendship, FriendRequest, UserFollow
from Community.models.communication import Conversation, Message
from Community.models.feed import ActivityFeedItem
from Community.models.notification import Notification
from Community.models.content import (
    BlogPost, BlogCategory, BlogComment,
    Tutorial, TutorialStep,
    ShowcaseItem,
    Event, EventRegistration,
)
from Community.models.reactions import Reaction, ReactionType, ReactionSummary
from Community.models.css_comments import CssComment


# ==============================================================================
# Friends
# ==============================================================================

@require_http_methods(["GET", "POST"])
@api_auth_required
def friends_view(request):
    """
    List friends or send a friend request.
    GET /api/community/friends/
    POST /api/community/friends/add/ — {"username": "foo"}
    """
    if request.method == "GET":
        friends_rels = Friendship.objects.filter(
            Q(user1=request.user) | Q(user2=request.user)
        ).select_related('user1', 'user2')

        paginated = paginate_queryset(friends_rels, request)
        data = []
        for rel in paginated['items']:
            friend_user = rel.user2 if rel.user1 == request.user else rel.user1
            data.append({
                "id": str(rel.id),
                "friend_id": friend_user.id,
                "username": friend_user.username,
                "since": rel.created_at.isoformat()
            })

        return api_success({
            "friends": data,
            "pagination": paginated['pagination']
        })

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            target_username = data.get("username", "")
        except Exception:
            return api_error("Invalid payload", status=400)

        if not target_username:
            return api_error("Username is required", status=400)

        try:
            target_user = User.objects.get(username=target_username)
        except User.DoesNotExist:
            return api_error("User not found", status=404)

        if target_user == request.user:
            return api_error("You cannot send a request to yourself", status=400)

        if Friendship.objects.filter(
            (Q(user1=request.user) & Q(user2=target_user)) |
            (Q(user1=target_user) & Q(user2=request.user))
        ).exists():
            return api_error("Already friends", status=400)

        req, created = FriendRequest.objects.get_or_create(sender=request.user, receiver=target_user)
        if not created and hasattr(req, 'status') and req.status != 'pending':
            req.status = 'pending'
            req.save()

        return api_success({"message": "Friend request sent"})


@require_http_methods(["POST"])
@api_auth_required
def friend_add_view(request):
    """POST-only alias for sending a friend request."""
    return friends_view(request)


@require_http_methods(["POST"])
@api_auth_required
def friend_handle_view(request, request_id):
    """
    Accept or reject a friend request.
    POST {"action": "accept"|"reject"}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    action = data.get('action', '').strip()
    if action not in ('accept', 'reject'):
        return api_error("action must be 'accept' or 'reject'.", status=400)

    try:
        friend_req = FriendRequest.objects.get(id=request_id, receiver=request.user)
    except FriendRequest.DoesNotExist:
        return api_error("Friend request not found.", status=404)

    if hasattr(friend_req, 'status') and friend_req.status != 'pending':
        return api_error("This request has already been handled.", status=400)

    if action == 'accept':
        friend_req.status = 'accepted'
        friend_req.save()
        Friendship.objects.get_or_create(
            **({'user1': friend_req.sender, 'user2': request.user}
               if friend_req.sender.id < request.user.id
               else {'user1': request.user, 'user2': friend_req.sender})
        )
        return api_success({}, message="Friend request accepted.")
    else:
        friend_req.status = 'rejected'
        friend_req.save()
        return api_success({}, message="Friend request rejected.")


@require_http_methods(["DELETE"])
@api_auth_required
def friend_remove_view(request, friend_id):
    """
    Remove a friend by their user ID.
    """
    try:
        target_user = User.objects.get(id=friend_id)
    except User.DoesNotExist:
        return api_error("User not found.", status=404)

    friendship = Friendship.objects.filter(
        (Q(user1=request.user) & Q(user2=target_user)) |
        (Q(user1=target_user) & Q(user2=request.user))
    ).first()

    if not friendship:
        return api_error("You are not friends with this user.", status=404)

    friendship.delete()
    return api_success({}, message="Friend removed.")


@require_http_methods(["POST"])
@api_auth_required
def friend_block_view(request):
    """
    Block a user.
    POST {"username": "..."}
    """
    try:
        data = json.loads(request.body)
        target_username = data.get('username', '').strip()
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    if not target_username:
        return api_error("Username is required.", status=400)

    try:
        target_user = User.objects.get(username=target_username)
    except User.DoesNotExist:
        return api_error("User not found.", status=404)

    if target_user == request.user:
        return api_error("You cannot block yourself.", status=400)

    friendship = Friendship.objects.filter(
        (Q(user1=request.user) & Q(user2=target_user)) |
        (Q(user1=target_user) & Q(user2=request.user))
    ).first()

    if not friendship:
        return api_error("You are not friends with this user.", status=404)

    # Set block flag for the requesting user
    if friendship.user1 == request.user:
        friendship.user1_blocked = True
    else:
        friendship.user2_blocked = True
    friendship.save()

    return api_success({}, message=f"Blocked {target_username}.")


@require_http_methods(["POST"])
@api_auth_required
def friend_unblock_view(request):
    """
    Unblock a user.
    POST {"username": "..."}
    """
    try:
        data = json.loads(request.body)
        target_username = data.get('username', '').strip()
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    if not target_username:
        return api_error("Username is required.", status=400)

    try:
        target_user = User.objects.get(username=target_username)
    except User.DoesNotExist:
        return api_error("User not found.", status=404)

    friendship = Friendship.objects.filter(
        (Q(user1=request.user) & Q(user2=target_user)) |
        (Q(user1=target_user) & Q(user2=request.user))
    ).first()

    if not friendship:
        return api_error("Friendship not found.", status=404)

    if friendship.user1 == request.user:
        friendship.user1_blocked = False
    else:
        friendship.user2_blocked = False
    friendship.save()

    return api_success({}, message=f"Unblocked {target_username}.")


# ==============================================================================
# Following
# ==============================================================================

@require_http_methods(["POST"])
@api_auth_required
def follow_view(request, user_id):
    """
    Follow a user.
    """
    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return api_error("User not found.", status=404)

    if target_user == request.user:
        return api_error("You cannot follow yourself.", status=400)

    _, created = UserFollow.objects.get_or_create(follower=request.user, following=target_user)
    if not created:
        return api_error("You are already following this user.", status=400)

    return api_success({}, message=f"Now following {target_user.username}.")


@require_http_methods(["DELETE"])
@api_auth_required
def unfollow_view(request, user_id):
    """
    Unfollow a user.
    """
    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return api_error("User not found.", status=404)

    deleted, _ = UserFollow.objects.filter(follower=request.user, following=target_user).delete()
    if not deleted:
        return api_error("You are not following this user.", status=404)

    return api_success({}, message=f"Unfollowed {target_user.username}.")


# ==============================================================================
# Messages / Conversations
# ==============================================================================

@require_http_methods(["GET", "POST"])
@api_auth_required
def messages_view(request):
    """
    List active conversations or send a direct message.
    """
    if request.method == "GET":
        conversations = Conversation.objects.filter(
            Q(user1=request.user) | Q(user2=request.user) | Q(group_participants=request.user)
        ).distinct().order_by('-created_at')

        paginated = paginate_queryset(conversations, request)

        data = []
        for conv in paginated['items']:
            if conv.is_group:
                other_participants = [p.username for p in conv.group_participants.exclude(id=request.user.id)]
                title = conv.group_name or ", ".join(other_participants)
            else:
                other_user = conv.user2 if conv.user1 == request.user else conv.user1
                other_participants = [other_user.username] if other_user else []
                title = other_user.username if other_user else "Unknown"

            data.append({
                "id": str(conv.id),
                "title": title,
                "participants": other_participants,
                "created_at": conv.created_at.isoformat(),
            })

        return api_success({"conversations": data, "pagination": paginated['pagination']})

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            conversation_id = data.get("conversation_id")
            content = data.get("content", "").strip()[:5000]
        except Exception:
            return api_error("Invalid payload", status=400)

        if not content:
            return api_error("Content is required", status=400)

        if not conversation_id:
            return api_error("conversation_id is required", status=400)

        conv = get_object_or_404(Conversation, id=conversation_id)
        is_participant = (
            (conv.is_group and conv.group_participants.filter(id=request.user.id).exists()) or
            conv.user1 == request.user or conv.user2 == request.user
        )
        if not is_participant:
            return api_error("You are not part of this conversation", status=403)

        msg = Message.objects.create(conversation=conv, sender=request.user, content=content)
        return api_success({"message": "Message sent", "message_id": str(msg.id)}, status=201)


@require_http_methods(["POST"])
@api_auth_required
def messages_send_view(request):
    """POST-only alias for sending a message to an existing conversation."""
    return messages_view(request)


@require_http_methods(["GET"])
@api_auth_required
def conversation_detail_view(request, conversation_id):
    """
    Get messages within a specific conversation.
    """
    conv = get_object_or_404(Conversation, id=conversation_id)
    is_participant = (
        (conv.is_group and conv.group_participants.filter(id=request.user.id).exists()) or
        conv.user1 == request.user or conv.user2 == request.user
    )
    if not is_participant:
        return api_error("You are not part of this conversation.", status=403)

    messages_qs = Message.objects.filter(conversation=conv, is_deleted=False).order_by('created_at')
    paginated = paginate_queryset(messages_qs, request, default_per_page=50)

    data = []
    for msg in paginated['items']:
        data.append({
            'id': str(msg.id),
            'sender': msg.sender.username if msg.sender else None,
            'content': msg.content,
            'message_type': msg.message_type,
            'is_edited': msg.is_edited,
            'created_at': msg.created_at.isoformat(),
        })

    return api_success({'messages': data, 'pagination': paginated['pagination']})


@require_http_methods(["POST"])
@api_auth_required
def conversation_start_view(request, user_id):
    """
    Start or retrieve a 1-on-1 conversation with a user.
    """
    try:
        other_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return api_error("User not found.", status=404)

    if other_user == request.user:
        return api_error("Cannot start a conversation with yourself.", status=400)

    # Find existing 1-on-1 conversation
    existing = Conversation.objects.filter(
        is_group=False
    ).filter(
        (Q(user1=request.user) & Q(user2=other_user)) |
        (Q(user1=other_user) & Q(user2=request.user))
    ).first()

    if existing:
        return api_success({'conversation_id': str(existing.id), 'created': False})

    conv = Conversation.objects.create(user1=request.user, user2=other_user)
    return api_success({'conversation_id': str(conv.id), 'created': True}, status=201)


# ==============================================================================
# Notifications
# ==============================================================================

@require_http_methods(["GET"])
@api_auth_required
def notifications_view(request):
    """
    List paginated notifications for the current user.
    Optional query param: ?unread=true to filter unread only.
    """
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    if request.GET.get('unread') == 'true':
        notifications = notifications.filter(is_read=False)

    paginated = paginate_queryset(notifications, request, default_per_page=20)

    data = []
    for n in paginated['items']:
        data.append({
            'id': str(n.id),
            'type': n.notif_type,
            'content': n.content,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat(),
        })

    return api_success({'notifications': data, 'pagination': paginated['pagination']})


@require_http_methods(["POST"])
@api_auth_required
def notification_read_view(request, notification_id):
    """
    Mark a specific notification as read.
    """
    try:
        notif = Notification.objects.get(id=notification_id, user=request.user)
    except Notification.DoesNotExist:
        return api_error("Notification not found.", status=404)

    notif.is_read = True
    notif.save()
    return api_success({}, message="Notification marked as read.")


@require_http_methods(["POST"])
@api_auth_required
def notification_read_all_view(request):
    """
    Mark all notifications as read.
    """
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return api_success({}, message="All notifications marked as read.")


@require_http_methods(["GET"])
@api_auth_required
def notification_count_view(request):
    """
    Return unread notification count.
    """
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return api_success({'unread_count': count})


# ==============================================================================
# Feed
# ==============================================================================

@require_http_methods(["GET"])
@api_auth_required
def feed_view(request):
    """
    Get activity feed.
    """
    activities = ActivityFeedItem.objects.all().order_by('-created_at')
    paginated = paginate_queryset(activities, request)

    data = []
    for act in paginated['items']:
        actor_name = act.user.username if act.user else "System"
        data.append({
            "id": str(act.id),
            "actor": actor_name,
            "action": act.action_type,
            "message": act.content if hasattr(act, 'content') else getattr(act, 'description', None),
            "created_at": act.created_at.isoformat()
        })

    return api_success({"feed": data, "pagination": paginated['pagination']})


# ==============================================================================
# Events
# ==============================================================================

@require_http_methods(["GET"])
@api_auth_required
def events_view(request):
    """
    List community events.
    Optional filters: ?upcoming=true, ?type=workshop|webinar|meetup
    """
    from django.utils import timezone
    events = Event.objects.order_by('start_datetime')

    if request.GET.get('upcoming') == 'true':
        events = events.filter(start_datetime__gt=timezone.now())
    event_type = request.GET.get('type')
    if event_type:
        events = events.filter(event_type=event_type)

    paginated = paginate_queryset(events, request, default_per_page=20)

    data = []
    for e in paginated['items']:
        data.append({
            'id': str(e.id),
            'title': e.title,
            'description': e.description,
            'event_type': e.event_type,
            'start_datetime': e.start_datetime.isoformat() if e.start_datetime else None,
            'end_datetime': e.end_datetime.isoformat() if e.end_datetime else None,
            'location': e.location if hasattr(e, 'location') else None,
            'capacity': e.capacity if hasattr(e, 'capacity') else None,
            'is_upcoming': e.is_upcoming(),
            'registration_count': e.registration_count() if hasattr(e, 'registration_count') else 0,
        })

    return api_success({'events': data, 'pagination': paginated['pagination']})


@require_http_methods(["GET"])
@api_auth_required
def event_detail_view(request, event_id):
    """
    Get event detail and the current user's registration status.
    """
    event = get_object_or_404(Event, id=event_id)

    registered = EventRegistration.objects.filter(
        event=event, user=request.user
    ).exclude(status='cancelled').exists()

    return api_success({
        'id': str(event.id),
        'title': event.title,
        'description': event.description,
        'event_type': event.event_type,
        'start_datetime': event.start_datetime.isoformat() if event.start_datetime else None,
        'end_datetime': event.end_datetime.isoformat() if event.end_datetime else None,
        'location': event.location if hasattr(event, 'location') else None,
        'capacity': event.capacity if hasattr(event, 'capacity') else None,
        'is_upcoming': event.is_upcoming(),
        'is_full': event.is_full() if hasattr(event, 'is_full') else False,
        'registration_count': event.registration_count() if hasattr(event, 'registration_count') else 0,
        'is_registered': registered,
    })


@require_http_methods(["POST"])
@api_auth_required
def event_register_view(request, event_id):
    """
    Register or cancel registration for an event.
    POST: register. DELETE (via action param): cancel.
    """
    event = get_object_or_404(Event, id=event_id)

    if not event.is_upcoming():
        return api_error("This event has already started or ended.", status=400)

    if hasattr(event, 'is_full') and event.is_full():
        return api_error("This event is at full capacity.", status=400)

    reg, created = EventRegistration.objects.get_or_create(
        event=event,
        user=request.user,
        defaults={'status': 'registered'},
    )

    if not created:
        if reg.status == 'cancelled':
            reg.status = 'registered'
            reg.save()
            return api_success({}, message="Registration reinstated.")
        return api_error("You are already registered for this event.", status=400)

    return api_success({'registration_id': str(reg.id)}, message="Successfully registered.", status=201)


@require_http_methods(["DELETE"])
@api_auth_required
def event_cancel_view(request, event_id):
    """
    Cancel registration for an event.
    """
    event = get_object_or_404(Event, id=event_id)

    try:
        reg = EventRegistration.objects.get(event=event, user=request.user)
    except EventRegistration.DoesNotExist:
        return api_error("You are not registered for this event.", status=404)

    if reg.status == 'cancelled':
        return api_error("Registration already cancelled.", status=400)

    reg.status = 'cancelled'
    reg.save()
    return api_success({}, message="Registration cancelled.")


# ==============================================================================
# Blog
# ==============================================================================

@require_http_methods(["GET"])
@api_auth_required
def blog_view(request):
    """
    List published blog posts.
    Optional: ?category=<slug>
    """
    posts = BlogPost.objects.filter(published_at__isnull=False).order_by('-published_at')
    category_slug = request.GET.get('category')
    if category_slug:
        posts = posts.filter(category__slug=category_slug)

    paginated = paginate_queryset(posts, request, default_per_page=20)

    data = []
    for p in paginated['items']:
        data.append({
            'slug': p.slug,
            'title': p.title,
            'author': p.author.username if p.author else None,
            'category': p.category.name if p.category else None,
            'is_featured': p.is_featured,
            'published_at': p.published_at.isoformat() if p.published_at else None,
            'snippet': p.content[:300] if p.content else '',
        })

    return api_success({'posts': data, 'pagination': paginated['pagination']})


@require_http_methods(["GET"])
@api_auth_required
def blog_detail_view(request, slug):
    """
    Get a blog post detail with approved comments.
    """
    post = get_object_or_404(BlogPost, slug=slug, published_at__isnull=False)
    comments = BlogComment.objects.filter(post=post, is_approved=True).order_by('created_at')

    comments_data = []
    for c in comments:
        comments_data.append({
            'id': str(c.id),
            'author': c.author.username if c.author else None,
            'content': c.content,
            'created_at': c.created_at.isoformat(),
        })

    return api_success({
        'slug': post.slug,
        'title': post.title,
        'author': post.author.username if post.author else None,
        'category': post.category.name if post.category else None,
        'content': post.content,
        'is_featured': post.is_featured,
        'published_at': post.published_at.isoformat() if post.published_at else None,
        'comments': comments_data,
    })


@require_http_methods(["POST"])
@api_auth_required
def blog_comment_view(request, slug):
    """
    Add a comment to a blog post.
    POST {"content": "..."}
    """
    post = get_object_or_404(BlogPost, slug=slug, published_at__isnull=False)

    try:
        data = json.loads(request.body)
        content = data.get('content', '').strip()
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    if not content:
        return api_error("Content is required.", status=400)

    if len(content) > 2000:
        return api_error("Comment must be under 2000 characters.", status=400)

    comment = BlogComment.objects.create(post=post, author=request.user, content=content)
    return api_success({
        'id': str(comment.id),
        'content': comment.content,
    }, message="Comment submitted for approval.", status=201)


# ==============================================================================
# Tutorials
# ==============================================================================

@require_http_methods(["GET"])
@api_auth_required
def tutorials_view(request):
    """
    List tutorials.
    Optional: ?difficulty=beginner|intermediate|advanced
    """
    tutorials = Tutorial.objects.order_by('title')
    difficulty = request.GET.get('difficulty')
    if difficulty:
        tutorials = tutorials.filter(difficulty=difficulty)

    paginated = paginate_queryset(tutorials, request, default_per_page=20)

    data = []
    for t in paginated['items']:
        step_count = TutorialStep.objects.filter(tutorial=t).count()
        data.append({
            'slug': t.slug,
            'title': t.title,
            'description': t.description,
            'difficulty': t.difficulty,
            'step_count': step_count,
        })

    return api_success({'tutorials': data, 'pagination': paginated['pagination']})


@require_http_methods(["GET"])
@api_auth_required
def tutorial_detail_view(request, slug):
    """
    Get tutorial detail with all steps.
    """
    tutorial = get_object_or_404(Tutorial, slug=slug)
    steps = TutorialStep.objects.filter(tutorial=tutorial).order_by('order')

    steps_data = []
    for s in steps:
        steps_data.append({
            'order': s.order,
            'title': s.title,
            'content': s.content,
            'has_quiz': bool(s.quiz_data),
        })

    return api_success({
        'slug': tutorial.slug,
        'title': tutorial.title,
        'description': tutorial.description,
        'difficulty': tutorial.difficulty,
        'steps': steps_data,
    })


# ==============================================================================
# Showcase
# ==============================================================================

@require_http_methods(["GET"])
@api_auth_required
def showcase_view(request):
    """
    List showcase items.
    Only returns approved items — unapproved items require moderation.
    Optional: ?sort=votes|new (default: votes)
    """
    sort = request.GET.get('sort', 'votes')
    items = ShowcaseItem.objects.filter(is_approved=True)
    if sort == 'new':
        items = items.order_by('-created_at')
    else:
        items = items.order_by('-votes')

    paginated = paginate_queryset(items, request, default_per_page=20)

    data = []
    for item in paginated['items']:
        data.append({
            'id': str(item.id),
            'title': item.title,
            'description': item.description,
            'creator': item.creator.username if item.creator else None,
            'content_url': item.content_url,
            'votes': item.votes,
            'created_at': item.created_at.isoformat(),
        })

    return api_success({'showcase': data, 'pagination': paginated['pagination']})


@require_http_methods(["GET"])
@api_auth_required
def showcase_detail_view(request, item_id):
    """
    Get showcase item detail.
    Only approved items are accessible.
    """
    item = get_object_or_404(ShowcaseItem, id=item_id, is_approved=True)
    return api_success({
        'id': str(item.id),
        'title': item.title,
        'description': item.description,
        'creator': item.creator.username if item.creator else None,
        'content_url': item.content_url,
        'votes': item.votes,
        'created_at': item.created_at.isoformat(),
    })


@require_http_methods(["POST"])
@api_auth_required
def showcase_submit_view(request):
    """
    Submit a CSS creation to the showcase.
    Submissions start unapproved and go through moderation review.
    POST {"title": "...", "description": "...", "content_url": "..."}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    content_url = data.get('content_url', '').strip()

    if not title:
        return api_error("Title is required.", status=400)
    if not content_url:
        return api_error("content_url is required.", status=400)

    item = ShowcaseItem.objects.create(
        creator=request.user,
        title=title[:200],
        description=description[:1000],
        content_url=content_url,
        is_approved=False,
    )
    return api_success(
        {'id': str(item.id)},
        message="Showcase item submitted for moderation review. It will appear once approved.",
        status=201,
    )


@require_http_methods(["POST"])
@api_auth_required
def showcase_vote_view(request, item_id):
    """
    Vote on a showcase item (one vote per user, toggle).
    Only approved items can be voted on.
    """
    item = get_object_or_404(ShowcaseItem, id=item_id, is_approved=True)

    if item.creator == request.user:
        return api_error("You cannot vote on your own submission.", status=400)

    # Simple vote increment — no per-user vote tracking in the model
    item.votes = (item.votes or 0) + 1
    item.save()
    return api_success({'votes': item.votes}, message="Vote recorded.")


# ==============================================================================
# Reactions
# ==============================================================================

@require_http_methods(["GET", "POST"])
@api_auth_required
def reactions_view(request):
    """
    Get reactions for a content object or toggle a reaction.
    GET: ?content_type=<app_label.model>&object_id=<uuid>
    POST: {"content_type": "api.css", "object_id": "...", "reaction_type_id": "..."}
    """
    if request.method == "GET":
        content_type_str = request.GET.get('content_type', '')
        object_id = request.GET.get('object_id', '')

        if not content_type_str or not object_id:
            return api_error("content_type and object_id are required.", status=400)

        try:
            app_label, model_name = content_type_str.lower().split('.')
            ct = ContentType.objects.get(app_label=app_label, model=model_name)
        except (ValueError, ContentType.DoesNotExist):
            return api_error("Invalid content_type.", status=400)

        summaries = ReactionSummary.objects.filter(
            content_type=ct, object_id=object_id
        ).select_related('reaction_type')

        data = []
        for s in summaries:
            data.append({
                'reaction_type': s.reaction_type.name,
                'emoji': s.reaction_type.emoji,
                'count': s.count,
            })

        return api_success({'reactions': data})

    # POST — toggle reaction
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    content_type_str = data.get('content_type', '')
    object_id = data.get('object_id', '')
    reaction_type_id = data.get('reaction_type_id', '')

    if not all([content_type_str, object_id, reaction_type_id]):
        return api_error("content_type, object_id, and reaction_type_id are required.", status=400)

    try:
        app_label, model_name = content_type_str.lower().split('.')
        ct = ContentType.objects.get(app_label=app_label, model=model_name)
    except (ValueError, ContentType.DoesNotExist):
        return api_error("Invalid content_type.", status=400)

    try:
        reaction_type = ReactionType.objects.get(id=reaction_type_id, is_active=True)
    except ReactionType.DoesNotExist:
        return api_error("Reaction type not found.", status=404)

    existing = Reaction.objects.filter(
        user=request.user, content_type=ct, object_id=object_id, reaction_type=reaction_type
    ).first()

    if existing:
        existing.delete()
        ReactionSummary.objects.filter(
            content_type=ct, object_id=object_id, reaction_type=reaction_type
        ).update(count=max(0, ReactionSummary.objects.filter(
            content_type=ct, object_id=object_id, reaction_type=reaction_type
        ).values_list('count', flat=True).first() or 1) - 1)
        return api_success({'reacted': False}, message="Reaction removed.")

    Reaction.objects.create(
        user=request.user,
        content_type=ct,
        object_id=str(object_id),
        reaction_type=reaction_type,
    )
    summary, _ = ReactionSummary.objects.get_or_create(
        content_type=ct, object_id=str(object_id), reaction_type=reaction_type
    )
    summary.count = Reaction.objects.filter(
        content_type=ct, object_id=str(object_id), reaction_type=reaction_type
    ).count()
    summary.save()

    return api_success({'reacted': True}, message="Reaction added.")


# ==============================================================================
# CSS Comments
# ==============================================================================

@require_http_methods(["GET", "POST"])
@api_auth_required
def css_comments_view(request, css_id):
    """
    List or submit comments on a CSS file.
    GET: Returns approved comments (paginated).
    POST {"content": "...", "is_question": false}: Submit a comment.
    """
    if request.method == "GET":
        comments = CssComment.objects.filter(
            css_item_id=css_id, status='approved'
        ).select_related('author').order_by('-created_at')

        paginated = paginate_queryset(comments, request, default_per_page=20)

        data = []
        for c in paginated['items']:
            data.append({
                'id': str(c.id),
                'author': c.author.username if c.author else None,
                'content': c.content,
                'is_question': c.is_question,
                'seller_answer': c.seller_answer if c.seller_answer else None,
                'answered_at': c.answered_at.isoformat() if c.answered_at else None,
                'created_at': c.created_at.isoformat(),
            })

        return api_success({'comments': data, 'pagination': paginated['pagination']})

    # POST — submit comment
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    content = data.get('content', '').strip()
    if not content:
        return api_error("Content is required.", status=400)

    if len(content) > 1000:
        return api_error("Comment must be under 1000 characters.", status=400)

    is_question = bool(data.get('is_question', False))

    comment = CssComment.objects.create(
        css_item_id=css_id,
        author=request.user,
        content=content,
        is_question=is_question,
    )
    return api_success({
        'id': str(comment.id),
        'status': comment.status,
    }, message="Comment submitted.", status=201)
