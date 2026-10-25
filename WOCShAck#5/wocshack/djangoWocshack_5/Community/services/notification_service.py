from django.conf import settings
from django.utils import timezone
from Community.models.notification import Notification, NotificationPreference

import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

NOTIF_EMAIL_SOURCE = 'V.R.C Notifications'


def _prefs_allow(user, pref_field):
    """Checks if the preference is enabled (creates if non-existent)."""
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    return getattr(prefs, pref_field, True)


def _send_notification_email(user, title, message, action_url=''):
    """Send a notification email via the internal webmail HTTP service (fire-and-forget)."""
    if not user.email:
        return None

    server_name = os.environ.get('SERVER_NAME', 'localhost:8000')
    link_html = ''
    if action_url:
        absolute_url = f"http://{server_name}{action_url}"
        link_html = f"<br><br><a href='{absolute_url}' target='_blank'>View details</a>"

    content = (
        f"Hello {user.username},<br><br>"
        f"<strong>{title}</strong><br>"
        f"{message}{link_html}<br><br>"
        f"-- V.R.C Platform"
    )

    query_data = {
        'source': NOTIF_EMAIL_SOURCE,
        'destination': user.email,
        'subject': title,
        'content': content,
    }
    url = f'http://{settings.WEBMAIL_HOST}/send?' + urllib.parse.urlencode(query_data)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'wocshack-notification/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {'status': resp.getcode()}
    except Exception as e:
        logger.warning("Notification email failed: user=%s error=%s", user.username, str(e))
        return None


def create_notification(user, notif_type, title, message, action_url='', priority='normal'):
    """Creates an in-app notification for a user and sends an email."""
    # Map type → preference field
    pref_map = {
        Notification.NotifType.FRIEND_REQUEST:   'friend_requests',
        Notification.NotifType.FRIEND_ACCEPT:    'friend_requests',
        Notification.NotifType.NEW_MESSAGE:      'messages',
        Notification.NotifType.NEW_FOLLOWER:     'followers',
        Notification.NotifType.SYSTEM:           'system',
        Notification.NotifType.NEW_BLOG_POST:    'blog',
        Notification.NotifType.BLOG_COMMENT:     'blog',
        Notification.NotifType.FORUM_REPLY:      'forum',
        Notification.NotifType.FORUM_MENTION:    'forum',
        Notification.NotifType.ORDER_UPDATE:     'orders',
        Notification.NotifType.AD_STATUS:        'advertisements',
        Notification.NotifType.NEW_REVIEW:       'orders',
        Notification.NotifType.MISSION_ASSIGNED: 'system',
    }
    pref_field = pref_map.get(notif_type, 'system')
    if not _prefs_allow(user, pref_field):
        return None

    notif = Notification.objects.create(
        user=user,
        notif_type=notif_type,
        title=title,
        message=message,
        action_url=action_url,
        priority=priority,
    )

    # Fire-and-forget email
    try:
        _send_notification_email(user, title, message, action_url)
    except Exception:
        pass

    return notif


def mark_read(notification_id, user):
    """Marks a notification as read."""
    Notification.objects.filter(id=notification_id, user=user).update(is_read=True)


def mark_all_read(user):
    """Marks all notifications as read."""
    Notification.objects.filter(user=user, is_read=False).update(is_read=True)


def unread_count(user):
    """Number of unread notifications."""
    return Notification.objects.filter(user=user, is_read=False).count()


def purge_expired(user):
    """Deletes expired notifications."""
    now = timezone.now()
    Notification.objects.filter(user=user, expires_at__lt=now).delete()


def send_notification(user, notif_type, title, message, action_url='', priority='normal'):
    """Alias for create_notification for expected API."""
    return create_notification(user, notif_type, title, message, action_url, priority)


def get_unread_count(user):
    """Alias for unread_count for expected API."""
    return unread_count(user)
