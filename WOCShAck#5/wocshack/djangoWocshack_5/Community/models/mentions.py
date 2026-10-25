import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


class MentionPreferences(models.Model):

    class AllowMentions(models.TextChoices):
        ALL         = 'all',         'Everyone'
        FRIENDS     = 'friends',     'Friends only'
        NOBODY      = 'nobody',      'Nobody'

    user              = models.OneToOneField(User, on_delete=models.CASCADE, related_name='mention_prefs')
    allow_mentions    = models.CharField(max_length=10, choices=AllowMentions.choices, default=AllowMentions.ALL)
    notify_on_mention = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} mention prefs"


class Mention(models.Model):
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mentioned_user  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_mentions')
    mentioned_by    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_mentions')
    content_type    = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id       = models.CharField(max_length=36)
    content_object  = GenericForeignKey('content_type', 'object_id')
    is_notified     = models.BooleanField(default=False)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['mentioned_user', 'is_notified']),
        ]

    def __str__(self):
        return f"@{self.mentioned_user.username} by {self.mentioned_by.username}"
