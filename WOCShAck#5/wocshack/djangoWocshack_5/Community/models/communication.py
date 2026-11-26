# CommunityEngagement/models/communication.py
import uuid
from django.contrib.auth.models import User
from django.db import models


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="conversation_user1"
    )
    user2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="conversation_user2"
    )

    is_group           = models.BooleanField(default=False)
    group_name         = models.CharField(max_length=100, blank=True)
    group_participants = models.ManyToManyField(User, blank=True, related_name='group_conversations')
    is_archived_by     = models.ManyToManyField(User, blank=True, related_name='archived_conversations')
    created_at         = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.is_group:
            return f"Group: {self.group_name or str(self.id)}"
        return f"Conversation {self.id}"


class Message(models.Model):

    class MessageType(models.TextChoices):
        TEXT   = 'text',   'Text'
        IMAGE  = 'image',  'Image'
        FILE   = 'file',   'File'
        SYSTEM = 'system', 'System'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages"
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    content      = models.TextField(max_length=500)
    message_type = models.CharField(max_length=10, choices=MessageType.choices, default=MessageType.TEXT)
    file_url     = models.CharField(max_length=500, blank=True)
    timestamp    = models.DateTimeField(auto_now_add=True)
    is_reported  = models.BooleanField(default=False)
    is_deleted   = models.BooleanField(default=False)
    is_edited    = models.BooleanField(default=False)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["conversation", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.sender} - {self.timestamp}"
    
class MessageReport(models.Model):

    STATUS = (
        ("pending", "Pending"),
        ("reviewed", "Reviewed"),
        ("resolved", "Resolved"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE
    )

    reason = models.TextField(
        max_length=500
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default="pending"
    )

    created_at = models.DateTimeField(auto_now_add=True)


class MessageRead(models.Model):
    """Suivi de lecture des messages par utilisateur (read receipts)."""

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message    = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reads')
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_reads')
    read_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user')
        ordering = ['-read_at']

    def __str__(self):
        return f"{self.user.username} read {self.message_id} at {self.read_at}"


class UserBlock(models.Model):
    """Dedicated user-blocking model independent of the Friendship table."""
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blocker    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocks_given')
    blocked    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocks_received')
    reason     = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('blocker', 'blocked')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked.username}"