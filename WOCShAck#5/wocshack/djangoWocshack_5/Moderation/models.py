"""
Moderation module models for centralized content moderation, user sanctions,
automated moderation, audit logging, and staff management.

All models follow secure coding practices with UUID PKs.
Designed to eventually centralize moderation features currently spread across
Forum and Chatbot modules without breaking existing models.
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


# =============================================================================
# CONTENT MODERATION
# =============================================================================

class ModerationQueue(models.Model):
    """
    Content review queue.
    Items flagged for moderation review from any module.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    SOURCE_MODULE_CHOICES = [
        ('forum', 'Forum'),
        ('shopping', 'Shopping'),
        ('chatbot', 'Chatbot'),
        ('community', 'Community'),
        ('developer', 'Developer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Generic FK to any content
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name='moderation_queue_items'
    )
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    source_module = models.CharField(max_length=20, choices=SOURCE_MODULE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')

    auto_flagged = models.BooleanField(default=False)
    auto_flag_reason = models.TextField(blank=True, default='')

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_queue_assignments'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Moderation Queue Item'
        verbose_name_plural = 'Moderation Queue'

    def __str__(self):
        return f"[{self.get_priority_display()}] {self.source_module} — {self.get_status_display()}"


class ContentAction(models.Model):
    """
    Moderation actions taken on content.
    Tracks every action taken by a moderator on any piece of content.
    """
    ACTION_TYPE_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('hide', 'Hide'),
        ('delete', 'Delete'),
        ('edit', 'Edit'),
        ('lock', 'Lock'),
        ('feature', 'Feature'),
        ('unfeature', 'Unfeature'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Generic FK to any content
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name='mod_content_actions'
    )
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    action_type = models.CharField(max_length=15, choices=ACTION_TYPE_CHOICES)
    reason = models.TextField(blank=True, default='')
    internal_notes = models.TextField(blank=True, default='')
    original_content = models.TextField(
        blank=True,
        default='',
        help_text="Snapshot of content before edit/deletion"
    )

    is_reversed = models.BooleanField(default=False)

    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_content_actions'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Content Action'
        verbose_name_plural = 'Content Actions'

    def __str__(self):
        return f"{self.actor.username} — {self.get_action_type_display()}"


# =============================================================================
# REPORT MANAGEMENT
# =============================================================================

class Report(models.Model):
    """
    User reports for any content across modules.
    Centralized report management replacing per-module reports.
    """
    REPORT_TYPE_CHOICES = [
        ('spam', 'Spam'),
        ('inappropriate', 'Inappropriate Content'),
        ('misleading', 'Misleading'),
        ('harassment', 'Harassment'),
        ('bullying', 'Bullying'),
        ('threats', 'Threats'),
        ('copyright', 'Copyright Violation'),
        ('trademark', 'Trademark Violation'),
        ('illegal', 'Illegal Content'),
        ('malware', 'Malware'),
        ('phishing', 'Phishing'),
        ('scam', 'Scam'),
        ('bug', 'Bug Report'),
        ('wrong_category', 'Wrong Category'),
        ('miscellaneous', 'Miscellaneous'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    RESOLUTION_TYPE_CHOICES = [
        ('action_taken', 'Action Taken'),
        ('warning_issued', 'Warning Issued'),
        ('user_banned', 'User Banned'),
        ('content_removed', 'Content Removed'),
        ('no_violation', 'No Violation Found'),
        ('duplicate', 'Duplicate Report'),
        ('insufficient_info', 'Insufficient Information'),
        ('dismissed', 'Dismissed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_reports_filed'
    )

    # Generic FK to reported content
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name='mod_reports'
    )
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    description = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_reports_assigned'
    )

    resolution_type = models.CharField(
        max_length=20,
        choices=RESOLUTION_TYPE_CHOICES,
        null=True,
        blank=True
    )
    resolution_notes = models.TextField(blank=True, default='')
    feedback_sent = models.BooleanField(default=False)
    is_valid = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Report'
        verbose_name_plural = 'Reports'

    def __str__(self):
        return f"Report #{str(self.id)[:8]} — {self.get_report_type_display()} ({self.get_status_display()})"


class ReportNote(models.Model):
    """
    Internal notes attached to reports.
    Supports both internal-only and external-visible notes.
    """
    VISIBILITY_CHOICES = [
        ('internal', 'Internal'),
        ('external', 'External'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name='notes'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_report_notes'
    )
    content = models.TextField()
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='internal')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Report Note'
        verbose_name_plural = 'Report Notes'

    def __str__(self):
        return f"Note on Report #{str(self.report_id)[:8]} by {self.author.username}"


# =============================================================================
# USER SANCTIONS
# =============================================================================

class UserWarning(models.Model):
    """
    Centralized warning system.
    Uses 'moderation_warnings' related_name to avoid clash with Forum.UserWarning.
    """
    WARNING_TYPE_CHOICES = [
        ('notice', 'Notice'),
        ('warning', 'Warning'),
        ('final_warning', 'Final Warning'),
        ('strike', 'Strike'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='moderation_warnings'
    )
    issuer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_warnings_issued'
    )

    warning_type = models.CharField(max_length=15, choices=WARNING_TYPE_CHOICES)
    severity = models.IntegerField(
        default=1,
        help_text="Severity from 1 (lowest) to 10 (highest)"
    )
    points = models.IntegerField(
        default=0,
        help_text="Warning points accumulated"
    )
    reason = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)

    expires_at = models.DateTimeField(null=True, blank=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'User Warning'
        verbose_name_plural = 'User Warnings'

    def __str__(self):
        return f"{self.get_warning_type_display()} for {self.user.username} — severity {self.severity}"

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at


class UserMute(models.Model):
    """
    Centralized muting system.
    Uses 'moderation_mutes' related_name to avoid clash with Forum.UserMute.
    """
    SCOPE_CHOICES = [
        ('posts', 'Posts'),
        ('topics', 'Topics'),
        ('likes', 'Likes'),
        ('messages', 'Messages'),
        ('reviews', 'Reviews'),
        ('showcase', 'Showcase'),
        ('all', 'All'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='moderation_mutes'
    )
    issuer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_mutes_issued'
    )

    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default='all')
    reason = models.TextField()
    duration = models.DurationField(
        null=True,
        blank=True,
        help_text="Duration of mute. Null for permanent."
    )
    is_permanent = models.BooleanField(default=False)

    lifted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_mutes_lifted'
    )
    lifted_at = models.DateTimeField(null=True, blank=True)
    lift_reason = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'User Mute'
        verbose_name_plural = 'User Mutes'

    def __str__(self):
        scope_label = self.get_scope_display()
        if self.is_permanent:
            return f"Permanent mute ({scope_label}) — {self.user.username}"
        return f"Mute ({scope_label}) — {self.user.username} until {self.expires_at}"

    @property
    def is_active(self):
        if self.lifted_at is not None:
            return False
        if self.is_permanent:
            return True
        if self.expires_at is None:
            return True
        return timezone.now() < self.expires_at


class UserBan(models.Model):
    """
    Centralized ban system.
    Supports temporary, permanent, and shadow bans with optional IP tracking.
    """
    BAN_TYPE_CHOICES = [
        ('temporary', 'Temporary'),
        ('permanent', 'Permanent'),
        ('shadow', 'Shadow Ban'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='moderation_bans'
    )
    issuer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_bans_issued'
    )

    ban_type = models.CharField(max_length=10, choices=BAN_TYPE_CHOICES)
    reason = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)
    duration = models.DurationField(
        null=True,
        blank=True,
        help_text="Duration of ban. Null for permanent."
    )
    ip_addresses = models.JSONField(
        default=list,
        blank=True,
        help_text="List of IP addresses associated with ban"
    )

    allow_appeal = models.BooleanField(default=True)

    lifted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_bans_lifted'
    )
    lifted_at = models.DateTimeField(null=True, blank=True)
    lift_reason = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'User Ban'
        verbose_name_plural = 'User Bans'

    def __str__(self):
        return f"{self.get_ban_type_display()} ban — {self.user.username}"

    @property
    def is_active(self):
        if self.lifted_at is not None:
            return False
        if self.ban_type == 'permanent':
            return True
        if self.expires_at is None:
            return True
        return timezone.now() < self.expires_at


class UserAppeal(models.Model):
    """
    Appeal system for sanctions.
    Users can appeal warnings, mutes, and bans.
    """
    SANCTION_TYPE_CHOICES = [
        ('warning', 'Warning'),
        ('mute', 'Mute'),
        ('ban', 'Ban'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('under_review', 'Under Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    OUTCOME_CHOICES = [
        ('upheld', 'Sanction Upheld'),
        ('reduced', 'Sanction Reduced'),
        ('overturned', 'Sanction Overturned'),
        ('modified', 'Sanction Modified'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_appeals'
    )
    sanction_type = models.CharField(max_length=10, choices=SANCTION_TYPE_CHOICES)
    sanction_id = models.UUIDField(help_text="UUID of the warning, mute, or ban being appealed")

    appeal_text = models.TextField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')

    reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_appeals_reviewed'
    )
    decision_notes = models.TextField(blank=True, default='')
    outcome = models.CharField(
        max_length=15,
        choices=OUTCOME_CHOICES,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'User Appeal'
        verbose_name_plural = 'User Appeals'

    def __str__(self):
        return f"Appeal by {self.user.username} — {self.get_sanction_type_display()} ({self.get_status_display()})"


# =============================================================================
# AUTOMATED MODERATION
# =============================================================================

class AutoModRule(models.Model):
    """
    Auto-moderation rule configuration.
    Defines triggers and actions for automated content moderation.
    """
    TRIGGER_TYPE_CHOICES = [
        ('word_exact', 'Exact Word Match'),
        ('word_fuzzy', 'Fuzzy Word Match'),
        ('regex', 'Regular Expression'),
        ('link_domain', 'Link Domain'),
        ('similarity', 'Content Similarity'),
        ('ai_toxicity', 'AI Toxicity Detection'),
        ('ai_spam', 'AI Spam Detection'),
        ('rate_limit', 'Rate Limit'),
        ('new_user', 'New User Restriction'),
        ('reputation', 'Reputation Threshold'),
    ]
    ACTION_CHOICES = [
        ('flag', 'Flag for Review'),
        ('hide', 'Hide Content'),
        ('reject', 'Reject Content'),
        ('warn', 'Warn User'),
        ('mute', 'Mute User'),
        ('notify', 'Notify Moderators'),
        ('log', 'Log Only'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')

    trigger_type = models.CharField(max_length=15, choices=TRIGGER_TYPE_CHOICES)
    trigger_value = models.TextField(help_text="Pattern, word list, threshold, or config JSON")

    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    action_params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional parameters for the action"
    )

    scope = models.JSONField(
        default=list,
        blank=True,
        help_text="List of modules/areas where this rule applies"
    )

    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(
        default=0,
        help_text="Higher priority rules are evaluated first"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_automod_rules_created'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', '-created_at']
        verbose_name = 'Auto-Mod Rule'
        verbose_name_plural = 'Auto-Mod Rules'

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"[{status}] {self.name} — {self.get_trigger_type_display()}"


class AutoModLog(models.Model):
    """
    Auto-moderation action history.
    Logs every action taken by the automated moderation system.
    """
    REVIEW_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('overturned', 'Overturned'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    rule = models.ForeignKey(
        AutoModRule,
        on_delete=models.CASCADE,
        related_name='logs'
    )

    # Generic FK to flagged content
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name='automod_logs'
    )
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_automod_logs'
    )

    action_taken = models.CharField(max_length=50)
    trigger_match = models.TextField(help_text="What triggered the rule")
    confidence_score = models.FloatField(
        default=1.0,
        help_text="Confidence score 0.0–1.0"
    )

    review_status = models.CharField(
        max_length=15,
        choices=REVIEW_STATUS_CHOICES,
        default='pending'
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_automod_reviews'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Auto-Mod Log'
        verbose_name_plural = 'Auto-Mod Logs'

    def __str__(self):
        return f"AutoMod: {self.rule.name} — {self.action_taken} ({self.user.username})"


# =============================================================================
# AUDIT LOGGING
# =============================================================================

class AuditLog(models.Model):
    """
    Comprehensive action audit logging.
    Tracks all moderation and admin actions across the platform.
    """
    RESULT_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('partial', 'Partial'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_audit_logs'
    )

    action_type = models.CharField(max_length=50, help_text="Category of action (e.g. moderation, admin, auth)")
    action_name = models.CharField(max_length=100, help_text="Specific action name (e.g. ban_user, approve_content)")

    target_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_audit_targets'
    )
    target_id = models.UUIDField(null=True, blank=True)

    affected_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_audit_affected'
    )

    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    session_id = models.CharField(max_length=255, blank=True, default='')

    result = models.CharField(max_length=10, choices=RESULT_CHOICES, default='success')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        return f"{self.actor.username} — {self.action_name} ({self.get_result_display()})"


class AuditRetention(models.Model):
    """
    Audit log retention policies.
    Defines how long different categories of audit logs are kept.
    """
    CATEGORY_CHOICES = [
        ('auth', 'Authentication'),
        ('moderation', 'Moderation'),
        ('admin', 'Administration'),
        ('financial', 'Financial'),
        ('security', 'Security'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, unique=True)
    retention_days = models.IntegerField(help_text="Days to keep logs in active storage")
    archive_after_days = models.IntegerField(
        null=True,
        blank=True,
        help_text="Days after which to archive logs"
    )
    delete_after_days = models.IntegerField(
        null=True,
        blank=True,
        help_text="Days after which to permanently delete logs"
    )

    class Meta:
        ordering = ['category']
        verbose_name = 'Audit Retention Policy'
        verbose_name_plural = 'Audit Retention Policies'

    def __str__(self):
        return f"{self.get_category_display()} — retain {self.retention_days}d"


# =============================================================================
# STAFF MANAGEMENT
# =============================================================================

class StaffRole(models.Model):
    """
    Staff role definitions.
    Defines moderation roles and their permissions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, default='')
    permissions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Permission map, e.g. {'can_ban': true, 'can_delete': true}"
    )
    can_assign = models.BooleanField(
        default=False,
        help_text="Whether holders of this role can assign roles to others"
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Staff Role'
        verbose_name_plural = 'Staff Roles'

    def __str__(self):
        return self.name


class StaffAssignment(models.Model):
    """
    Role assignments for staff members.
    Tracks who has what role, when it was assigned, and module access.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_staff_assignments'
    )
    role = models.ForeignKey(
        StaffRole,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_staff_assigned_by'
    )

    module_access = models.JSONField(
        default=list,
        blank=True,
        help_text="List of modules this assignment grants access to"
    )
    daily_action_limit = models.IntegerField(
        null=True,
        blank=True,
        help_text="Max actions per day. Null for unlimited."
    )

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-start_date']
        verbose_name = 'Staff Assignment'
        verbose_name_plural = 'Staff Assignments'

    def __str__(self):
        return f"{self.user.username} — {self.role.name}"

    @property
    def is_active(self):
        today = timezone.now().date()
        if self.end_date and today > self.end_date:
            return False
        return today >= self.start_date


class StaffMetrics(models.Model):
    """
    Staff performance tracking.
    Daily metrics for moderator activity and effectiveness.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    staff = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mod_staff_metrics'
    )
    date = models.DateField()

    reports_handled = models.IntegerField(default=0)
    content_reviewed = models.IntegerField(default=0)
    warnings_issued = models.IntegerField(default=0)
    avg_response_time = models.DurationField(null=True, blank=True)
    accuracy_rate = models.FloatField(
        null=True,
        blank=True,
        help_text="Accuracy rate 0.0–1.0"
    )
    overturned_appeals = models.IntegerField(default=0)

    class Meta:
        ordering = ['-date']
        unique_together = [['staff', 'date']]
        verbose_name = 'Staff Metrics'
        verbose_name_plural = 'Staff Metrics'

    def __str__(self):
        return f"{self.staff.username} — {self.date}"

