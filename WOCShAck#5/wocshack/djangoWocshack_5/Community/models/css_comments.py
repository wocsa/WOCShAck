import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class CssComment(models.Model):
    """Discussion comment on a CSS product from the Shopping module."""

    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    css_item_id   = models.IntegerField(db_index=True, help_text='PK of the CSS item from Shopping module')
    author        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='css_comments')
    content       = models.TextField(max_length=1000)
    is_question   = models.BooleanField(default=False)
    seller_answer = models.TextField(blank=True)
    answered_at   = models.DateTimeField(null=True, blank=True)
    status        = models.CharField(max_length=10, choices=Status.choices, default=Status.APPROVED)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['css_item_id', 'status']),
        ]

    def __str__(self):
        author_name = self.author.username if self.author else 'deleted'
        return f"{author_name} on item {self.css_item_id}"


class CommentReply(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comment    = models.ForeignKey(CssComment, on_delete=models.CASCADE, related_name='replies')
    author     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='comment_replies')
    content    = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        author_name = self.author.username if self.author else 'deleted'
        return f"{author_name} replying to comment {self.comment_id}"
