import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class PushSubscription(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint     = models.TextField(unique=True)
    p256dh_key   = models.CharField(max_length=200)
    auth_key     = models.CharField(max_length=100)
    user_agent   = models.CharField(max_length=300, blank=True)
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} push sub ({self.user_agent[:40] or 'unknown'})"


class PushNotification(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_notifications')
    title        = models.CharField(max_length=200)
    body         = models.TextField()
    icon         = models.CharField(max_length=300, blank=True)
    action_url   = models.CharField(max_length=300, blank=True)
    sent_at      = models.DateTimeField(auto_now_add=True)
    is_delivered = models.BooleanField(default=False)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.user.username}: {self.title}"
