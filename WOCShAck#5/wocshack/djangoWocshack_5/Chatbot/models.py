"""
Chatbot module models for chat messaging, knowledge base, and moderation.

All models follow secure coding practices with proper
validation, access control patterns, and audit trail support.
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinLengthValidator, MaxLengthValidator


class ChatMessage(models.Model):
    """
    Stores chat messages for history functionality.
    Each message is linked to a session_id for anonymous users
    or to a User for authenticated users.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chat_messages'
    )
    session_id = models.CharField(max_length=255, null=True, blank=True)
    message = models.TextField()
    response = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        user_info = self.user.username if self.user else f"Session: {self.session_id[:8]}..."
        return f"Chat by {user_info} at {self.timestamp}"


class KnowledgeBase(models.Model):
    """
    Database-backed knowledge base entries.
    Primary knowledge comes from JSON file, but this allows
    admins to add dynamic Q&A pairs.
    """
    question = models.TextField()
    answer = models.TextField()
    category = models.CharField(max_length=100, default='general')
    keywords = models.TextField(help_text="Comma-separated keywords for matching")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Knowledge Base Entries"

    def __str__(self):
        return f"[{self.category}] {self.question[:50]}..."


# =============================================================================
# CHATBOT MODERATION MODELS
# =============================================================================

class ChatbotResponseFlag(models.Model):
    """
    Tracks user and staff flags on chatbot responses.
    Allows users to report problematic chatbot responses for staff review.
    """
    FLAG_REASONS = [
        ('inaccurate', 'Inaccurate Information'),
        ('inappropriate', 'Inappropriate Content'),
        ('unhelpful', 'Unhelpful Response'),
        ('offensive', 'Offensive Language'),
        ('misleading', 'Misleading Information'),
        ('security_concern', 'Security Concern'),
        ('other', 'Other'),
    ]

    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('under_review', 'Under Review'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The flagged chat message
    chat_message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name='flags'
    )

    # Who flagged it
    flagged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chatbot_flags_filed'
    )
    flagged_by_session = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Session ID for anonymous flaggers"
    )

    # Flag details
    reason = models.CharField(
        max_length=20,
        choices=FLAG_REASONS,
        default='other'
    )
    description = models.TextField(
        max_length=2000,
        blank=True,
        validators=[MaxLengthValidator(2000)],
        help_text="Additional details about the issue"
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default='medium'
    )

    # Review status
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='pending'
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chatbot_flags_assigned'
    )

    # Resolution
    resolution_notes = models.TextField(
        max_length=2000,
        blank=True,
        help_text="Staff notes on how the flag was resolved"
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chatbot_flags_resolved'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Audit trail
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['severity', 'status']),
            models.Index(fields=['assigned_to', 'status']),
        ]

    def __str__(self):
        return f"Flag #{str(self.id)[:8]} - {self.get_reason_display()} ({self.get_status_display()})"

    def assign(self, moderator):
        """Assign flag to a moderator for review."""
        self.assigned_to = moderator
        self.status = 'under_review'
        self.save(update_fields=['assigned_to', 'status', 'updated_at'])

    def resolve(self, resolved_by, notes='', dismiss=False):
        """Mark flag as resolved or dismissed."""
        self.resolved_by = resolved_by
        self.resolved_at = timezone.now()
        self.resolution_notes = notes[:2000]
        self.status = 'dismissed' if dismiss else 'resolved'
        self.save()

    @classmethod
    def get_pending_count(cls):
        """Get count of pending flags."""
        return cls.objects.filter(status='pending').count()

    @classmethod
    def get_pending_by_severity(cls):
        """Get pending flags grouped by severity."""
        from django.db.models import Count
        return cls.objects.filter(
            status='pending'
        ).values('severity').annotate(
            count=Count('id')
        ).order_by('-count')


class ChatbotResponseEdit(models.Model):
    """
    Tracks staff edits to chatbot responses.
    Maintains a full audit trail of all modifications for accountability.
    """
    APPROVAL_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The edited chat message
    chat_message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name='edits'
    )

    # Edit content
    original_response = models.TextField(help_text="Original chatbot response before edit")
    edited_response = models.TextField(help_text="Edited response content")
    edit_reason = models.CharField(
        max_length=500,
        validators=[MinLengthValidator(5)],
        help_text="Reason for editing the response"
    )

    # Editor info
    edited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='chatbot_edits_made'
    )

    # Approval workflow
    approval_status = models.CharField(
        max_length=10,
        choices=APPROVAL_CHOICES,
        default='pending'
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chatbot_edits_reviewed'
    )
    review_notes = models.TextField(max_length=1000, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Related flag (optional)
    related_flag = models.ForeignKey(
        ChatbotResponseFlag,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='edits'
    )

    # Audit
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['chat_message', '-created_at']),
            models.Index(fields=['approval_status', '-created_at']),
            models.Index(fields=['edited_by', '-created_at']),
        ]

    def __str__(self):
        return f"Edit by {self.edited_by.username if self.edited_by else 'Unknown'} on message #{self.chat_message_id}"

    def approve(self, reviewer, notes=''):
        """Approve the edit and apply it to the original message."""
        self.approval_status = 'approved'
        self.reviewed_by = reviewer
        self.review_notes = notes[:1000]
        self.reviewed_at = timezone.now()
        self.save()

        # Apply the edit to the actual chat message
        self.chat_message.response = self.edited_response
        self.chat_message.save(update_fields=['response'])

    def reject(self, reviewer, notes=''):
        """Reject the edit."""
        self.approval_status = 'rejected'
        self.reviewed_by = reviewer
        self.review_notes = notes[:1000]
        self.reviewed_at = timezone.now()
        self.save()


class ChatbotKnowledgeModeration(models.Model):
    """
    Staff knowledge base management with version tracking.
    Tracks all moderation actions on knowledge base entries for audit purposes.
    """
    ACTION_CHOICES = [
        ('created', 'Entry Created'),
        ('updated', 'Entry Updated'),
        ('activated', 'Entry Activated'),
        ('deactivated', 'Entry Deactivated'),
        ('deleted', 'Entry Deleted'),
        ('reviewed', 'Entry Reviewed'),
    ]

    APPROVAL_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The knowledge base entry
    knowledge_entry = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_history'
    )

    # Action taken
    action = models.CharField(max_length=15, choices=ACTION_CHOICES)
    moderator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='chatbot_kb_actions'
    )
    reason = models.TextField(
        max_length=1000,
        blank=True,
        help_text="Reason for the moderation action"
    )

    # Content snapshots for version tracking
    previous_question = models.TextField(blank=True)
    previous_answer = models.TextField(blank=True)
    new_question = models.TextField(blank=True)
    new_answer = models.TextField(blank=True)
    previous_category = models.CharField(max_length=100, blank=True)
    new_category = models.CharField(max_length=100, blank=True)

    # Approval workflow
    approval_status = models.CharField(
        max_length=10,
        choices=APPROVAL_CHOICES,
        default='approved'
    )

    # Audit
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Knowledge Base Moderation Entries"
        indexes = [
            models.Index(fields=['knowledge_entry', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['moderator', '-created_at']),
        ]

    def __str__(self):
        entry_info = f"KB #{self.knowledge_entry_id}" if self.knowledge_entry_id else "Deleted entry"
        return f"{self.get_action_display()} on {entry_info} by {self.moderator.username if self.moderator else 'System'}"


class ChatbotModerationAction(models.Model):
    """
    Comprehensive audit log for all chatbot moderation actions.
    Provides accountability and traceability for all staff actions.
    """
    ACTION_TYPES = [
        ('flag_created', 'Response Flagged'),
        ('flag_assigned', 'Flag Assigned'),
        ('flag_resolved', 'Flag Resolved'),
        ('flag_dismissed', 'Flag Dismissed'),
        ('response_edited', 'Response Edited'),
        ('edit_approved', 'Edit Approved'),
        ('edit_rejected', 'Edit Rejected'),
        ('kb_entry_created', 'Knowledge Entry Created'),
        ('kb_entry_updated', 'Knowledge Entry Updated'),
        ('kb_entry_deleted', 'Knowledge Entry Deleted'),
        ('kb_entry_toggled', 'Knowledge Entry Toggled'),
        ('quality_scored', 'Quality Score Assigned'),
        ('bulk_action', 'Bulk Action Performed'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who performed the action
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='chatbot_mod_actions'
    )
    actor_username = models.CharField(max_length=150)

    # What action was taken
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    description = models.TextField(max_length=2000, blank=True)

    # Target references (optional, depending on action)
    target_message = models.ForeignKey(
        ChatMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_actions'
    )
    target_flag = models.ForeignKey(
        ChatbotResponseFlag,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_actions'
    )
    target_knowledge_entry = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_actions'
    )

    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional action metadata"
    )

    # Audit
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['action_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_action_type_display()} by {self.actor_username} at {self.created_at}"

    @classmethod
    def log_action(cls, actor, action_type, description='', target_message=None,
                   target_flag=None, target_knowledge_entry=None,
                   ip_address=None, metadata=None):
        """Create a new moderation action log entry."""
        return cls.objects.create(
            actor=actor,
            actor_username=actor.username,
            action_type=action_type,
            description=description,
            target_message=target_message,
            target_flag=target_flag,
            target_knowledge_entry=target_knowledge_entry,
            ip_address=ip_address,
            metadata=metadata or {},
        )


class ChatbotQualityScore(models.Model):
    """
    Response quality tracking for staff evaluation.
    Helps measure and improve chatbot response quality over time.
    """
    QUALITY_CHOICES = [
        (1, 'Very Poor'),
        (2, 'Poor'),
        (3, 'Acceptable'),
        (4, 'Good'),
        (5, 'Excellent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The scored chat message
    chat_message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name='quality_scores'
    )

    # Quality metrics
    accuracy_score = models.PositiveSmallIntegerField(
        choices=QUALITY_CHOICES,
        help_text="How accurate is the response?"
    )
    helpfulness_score = models.PositiveSmallIntegerField(
        choices=QUALITY_CHOICES,
        help_text="How helpful is the response?"
    )
    tone_score = models.PositiveSmallIntegerField(
        choices=QUALITY_CHOICES,
        help_text="How appropriate is the tone?"
    )
    overall_score = models.PositiveSmallIntegerField(
        choices=QUALITY_CHOICES,
        help_text="Overall quality rating"
    )

    # Staff feedback
    scored_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='chatbot_quality_scores_given'
    )
    notes = models.TextField(
        max_length=1000,
        blank=True,
        help_text="Additional quality notes"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # Ensure one score per user per message
        unique_together = ('chat_message', 'scored_by')
        indexes = [
            models.Index(fields=['chat_message', '-created_at']),
            models.Index(fields=['scored_by', '-created_at']),
        ]

    def __str__(self):
        return f"Quality score {self.overall_score}/5 for message #{self.chat_message_id}"

    def get_average_score(self):
        """Calculate average across all quality dimensions."""
        scores = [self.accuracy_score, self.helpfulness_score, self.tone_score, self.overall_score]
        return round(sum(scores) / len(scores), 1)
