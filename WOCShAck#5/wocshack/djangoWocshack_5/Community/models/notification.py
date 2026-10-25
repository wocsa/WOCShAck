from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class Notification(models.Model):
    """In-app notification for a user."""

    class NotifType(models.TextChoices):
        FRIEND_REQUEST  = 'friend_request',  'Friend Request'
        FRIEND_ACCEPT   = 'friend_accept',   'Friend Request Accepted'
        NEW_MESSAGE     = 'new_message',     'New Message'
        LEVEL_UP        = 'level_up',        'Level Up'
        ACHIEVEMENT     = 'achievement',     'Achievement Unlocked'
        DAILY_REWARD    = 'daily_reward',    'Daily Reward'
        NEW_FOLLOWER    = 'new_follower',    'New Follower'
        STREAK_BROKEN   = 'streak_broken',   'Streak Lost'
        STREAK_SHIELD   = 'streak_shield',   'Shield Used'
        SYSTEM          = 'system',          'System'
        NEW_BLOG_POST   = 'new_blog_post',  'New Blog Post'
        BLOG_COMMENT    = 'blog_comment',    'Blog Comment'
        FORUM_REPLY     = 'forum_reply',     'Forum Reply'
        FORUM_MENTION   = 'forum_mention',   'Forum Mention'
        ORDER_UPDATE    = 'order_update',    'Order Update'
        AD_STATUS       = 'ad_status',       'Ad Status'
        NEW_REVIEW      = 'new_review',      'New Review'
        MISSION_ASSIGNED = 'mission_assigned', 'Mission Assigned'
        REVIEW_SUBMITTED = 'review_submitted', 'Content submitted for review'

    class Priority(models.TextChoices):
        LOW    = 'low',    'Low'
        NORMAL = 'normal', 'Normal'
        HIGH   = 'high',   'High'

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notif_type = models.CharField(max_length=30, choices=NotifType.choices)
    title      = models.CharField(max_length=150)
    message    = models.CharField(max_length=300)
    action_url = models.CharField(max_length=300, blank=True)
    priority   = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    is_read    = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]

    def __str__(self):
        return f"{self.user.username} — {self.notif_type} ({'read' if self.is_read else 'unread'})"


class NotificationPreference(models.Model):
    """Notification preferences for a user."""

    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notif_preferences')

    # Enabled/disabled per type
    friend_requests = models.BooleanField(default=True)
    messages        = models.BooleanField(default=True)
    level_ups       = models.BooleanField(default=True)
    achievements    = models.BooleanField(default=True)
    followers       = models.BooleanField(default=True)
    system          = models.BooleanField(default=True)
    blog            = models.BooleanField(default=True)
    forum           = models.BooleanField(default=True)
    orders          = models.BooleanField(default=True)
    advertisements  = models.BooleanField(default=True)
    moderation      = models.BooleanField(default=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences of {self.user.username}"
