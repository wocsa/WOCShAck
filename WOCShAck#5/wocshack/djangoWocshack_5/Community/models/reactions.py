import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


class ReactionType(models.Model):

    class Category(models.TextChoices):
        STANDARD     = 'standard',     'Standard'
        CSS_SPECIFIC = 'css_specific',  'CSS Specific'
        PREMIUM      = 'premium',       'Premium'

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name                = models.CharField(max_length=50)
    emoji               = models.CharField(max_length=10)
    category            = models.CharField(max_length=15, choices=Category.choices, default=Category.STANDARD)
    min_level_required  = models.IntegerField(default=0)
    is_active           = models.BooleanField(default=True)
    order               = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.emoji} {self.name} ({self.get_category_display()})"


class Reaction(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reactions')
    reaction_type  = models.ForeignKey(ReactionType, on_delete=models.CASCADE, related_name='reactions')
    content_type   = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id      = models.CharField(max_length=36)
    content_object = GenericForeignKey('content_type', 'object_id')
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'content_type', 'object_id', 'reaction_type')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.user.username} {self.reaction_type.emoji} on {self.content_type} {self.object_id}"


class ReactionSummary(models.Model):
    """Aggregated reaction counts per content object per reaction type."""
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_type   = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id      = models.CharField(max_length=36)
    content_object = GenericForeignKey('content_type', 'object_id')
    reaction_type  = models.ForeignKey(ReactionType, on_delete=models.CASCADE, related_name='summaries')
    count          = models.IntegerField(default=0)
    last_updated   = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('content_type', 'object_id', 'reaction_type')
        ordering = ['-count']

    def __str__(self):
        return f"{self.reaction_type.emoji} ×{self.count} on {self.content_type} {self.object_id}"
