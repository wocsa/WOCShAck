"""
Signal handler: notify staff users when a new ModerationQueue item is created.

Respects per-user NotificationPreference.moderation flag.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from Moderation.models import ModerationQueue
from Community.models.notification import Notification, NotificationPreference


def _map_priority(queue_priority: str) -> str:
    """Map ModerationQueue priority to Notification priority."""
    if queue_priority in ('critical', 'high'):
        return Notification.Priority.HIGH
    return Notification.Priority.NORMAL


@receiver(post_save, sender=ModerationQueue)
def notify_staff_on_new_queue_item(sender, instance, created, **kwargs):
    """Create a Notification for every staff user when a queue item is created."""
    if not created:
        return

    staff_users = User.objects.filter(is_staff=True).select_related('notif_preferences')

    priority = _map_priority(instance.priority)
    content_label = instance.content_type.model_class().__name__ if instance.content_type else 'Content'
    module_label = instance.get_source_module_display()

    title = "New item pending review"
    message = f"{module_label} — {content_label} submitted for review"
    action_url = f"/admin_panel/content/review/{instance.pk}/"

    notifications = []
    for user in staff_users:
        # Respect the moderation preference flag (default True if no prefs exist)
        try:
            prefs = user.notif_preferences
            if not prefs.moderation:
                continue
        except NotificationPreference.DoesNotExist:
            pass  # No preferences row → default is to notify

        notifications.append(
            Notification(
                user=user,
                notif_type=Notification.NotifType.REVIEW_SUBMITTED,
                title=title,
                message=message,
                action_url=action_url,
                priority=priority,
            )
        )

    if notifications:
        Notification.objects.bulk_create(notifications)
