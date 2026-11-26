from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class ActivityFeedItem(models.Model):
    """Record of a user action for the activity feed."""

    class ActionType(models.TextChoices):
        FRIEND_ADDED         = 'friend_added',         'Friend Added'
        FOLLOWER_GAINED      = 'follower_gained',      'New Follower'
        BLOG_POST_CREATED    = 'blog_post_created',    'Article publié'
        FORUM_TOPIC_CREATED  = 'forum_topic_created',  'Sujet forum créé'
        FORUM_POST_CREATED   = 'forum_post_created',   'Message forum posté'
        SHOWCASE_ADDED       = 'showcase_added',       'Showcase ajouté'
        TUTORIAL_PUBLISHED   = 'tutorial_published',   'Tutoriel publié'
        CSS_PUBLISHED        = 'css_published',        'CSS publié'
        REVIEW_POSTED        = 'review_posted',        'Avis posté'
        EVENT_JOINED         = 'event_joined',         'Événement rejoint'

    class Visibility(models.TextChoices):
        PUBLIC    = 'public',    'Public'
        FOLLOWERS = 'followers', 'Followers'
        PRIVATE   = 'private',   'Private'

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feed_items')
    action_type = models.CharField(max_length=30, choices=ActionType.choices)  # 30 chars is sufficient for all values
    title       = models.CharField(max_length=200)
    description = models.CharField(max_length=400, blank=True)
    icon        = models.CharField(max_length=10, default='📌')
    # Optional FK for detail context
    related_user        = models.ForeignKey(User, on_delete=models.SET_NULL,
                                             null=True, blank=True, related_name='mentioned_in_feed')
    related_object_id   = models.CharField(max_length=100, blank=True)  # UUID or int as string
    visibility  = models.CharField(max_length=12, choices=Visibility.choices, default=Visibility.PUBLIC)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'created_at'])]

    def __str__(self):
        return f"{self.user.username} — {self.action_type}"


class FeedPreferences(models.Model):
    """Activity feed preferences for a user."""

    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='feed_prefs')

    show_friends         = models.BooleanField(default=True)
    show_blog_posts      = models.BooleanField(default=True)
    show_forum_posts     = models.BooleanField(default=True)
    show_showcases       = models.BooleanField(default=True)
    show_tutorials       = models.BooleanField(default=True)
    show_css             = models.BooleanField(default=True)
    show_reviews         = models.BooleanField(default=True)
    show_events          = models.BooleanField(default=True)
    default_visibility   = models.CharField(
        max_length=12,
        choices=ActivityFeedItem.Visibility.choices,
        default=ActivityFeedItem.Visibility.PUBLIC
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Feed prefs of {self.user.username}"
