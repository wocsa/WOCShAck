from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils.text import slugify
from decimal import Decimal
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model


class FriendRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_friend_requests"
    )
    receiver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_friend_requests"
    )

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("sender", "receiver")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sender} → {self.receiver} ({self.status})"


class Friendship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friendships_1")
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friendships_2")

    created_at = models.DateTimeField(auto_now_add=True)
    user1_blocked = models.BooleanField(default=False)
    user2_blocked = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user1", "user2")

    def __str__(self):
        return f"{self.user1} & {self.user2}"


class UserFollow(models.Model):
    """Unilateral follow — a user can follow a creator without reciprocity."""

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    follower   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')
    following  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    # Notification preferences for this specific follow
    notify_new_content = models.BooleanField(default=True)

    class Meta:
        unique_together = ('follower', 'following')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.follower.username} → {self.following.username}"
