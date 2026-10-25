from django.db.models import Q
from Community.models.communication import Conversation, Message
from Community.models.notification import Notification


def unread_messages(request):
    """Inject unread_message_count into every template context."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {}

    count = Message.objects.filter(
        Q(conversation__user1=request.user) | Q(conversation__user2=request.user),
        is_deleted=False,
    ).exclude(
        sender=request.user,
    ).exclude(
        reads__user=request.user,
    ).count()

    return {'unread_message_count': count}


def notification_context(request):
    """Inject notification bell data into every template context."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {}

    unread = Notification.objects.filter(user=request.user, is_read=False).count()
    recent = list(
        Notification.objects.filter(user=request.user, is_read=False)
        .order_by('-created_at')[:5]
    )

    return {
        'unread_notification_count': unread,
        'recent_notifications': recent,
    }
