"""
Forum module models for community discussion.
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from django.core.validators import MinLengthValidator, MaxLengthValidator
from django.urls import reverse


class Category(models.Model):
    """
    Forum category/board model.
    Categories organize topics into logical groups.
    Supports private categories with role-based access control.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        unique=True,
        validators=[MinLengthValidator(3)]
    )
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(
        max_length=500,
        blank=True,
        help_text="Brief description of the category"
    )
    icon = models.CharField(
        max_length=50,
        default='chat-bubble-left-right',
        help_text="Heroicon name for the category"
    )
    order = models.PositiveIntegerField(default=0, help_text="Display order")
    is_active = models.BooleanField(default=True)

    # Private category settings
    is_private = models.BooleanField(
        default=False,
        help_text="Private categories are only visible to allowed users"
    )
    staff_only = models.BooleanField(
        default=False,
        help_text="Only staff members can access this category"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('forum_category', kwargs={'slug': self.slug})

    def get_topic_count(self):
        return self.topics.count()

    def get_post_count(self):
        return Post.objects.filter(topic__category=self).count()

    def get_latest_post(self):
        return Post.objects.filter(topic__category=self).order_by('-created_at').first()

    def user_can_access(self, user):
        """
        Check if user can access this category.
        Public categories are accessible to all.
        Private categories check staff status.
        Staff-only categories require is_staff.
        """
        # Public categories are accessible to everyone
        if not self.is_private and not self.staff_only:
            return True

        # Anonymous users cannot access private categories
        if not user or not user.is_authenticated:
            return False

        # Staff-only categories
        if self.staff_only:
            return user.is_staff

        # Private categories - for now, allow all authenticated users
        # Can be extended to check groups/permissions
        if self.is_private:
            return user.is_authenticated

        return True

    def user_can_post(self, user):
        """
        Check if user can create posts in this category.
        Must have access to the category first.
        """
        if not self.user_can_access(user):
            return False

        if not user or not user.is_authenticated:
            return False

        # Staff-only categories require staff status for posting
        if self.staff_only:
            return user.is_staff

        return True


class Topic(models.Model):
    """
    Forum topic/thread model.
    Topics are discussion threads within a category.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='topics'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_topics'
    )
    title = models.CharField(
        max_length=200,
        validators=[MinLengthValidator(5), MaxLengthValidator(200)]
    )
    slug = models.SlugField(max_length=220, blank=True)

    # Topic status flags
    is_pinned = models.BooleanField(default=False, help_text="Pin topic to top of category")
    is_locked = models.BooleanField(default=False, help_text="Prevent new replies")

    # Statistics
    view_count = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-is_pinned', '-last_activity']
        indexes = [
            models.Index(fields=['category', '-last_activity']),
            models.Index(fields=['author', '-created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:200]
            self.slug = f"{base_slug}-{str(self.id)[:8]}" if self.id else base_slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('forum_topic', kwargs={'topic_id': self.id})

    def get_reply_count(self):
        """Get number of replies (excluding the original post)"""
        return max(0, self.posts.count() - 1)

    def get_first_post(self):
        """Get the original post of the topic"""
        return self.posts.order_by('created_at').first()

    def get_last_post(self):
        """Get the most recent post"""
        return self.posts.order_by('-created_at').first()

    def increment_view_count(self):
        """Increment view count atomically"""
        Topic.objects.filter(pk=self.pk).update(view_count=models.F('view_count') + 1)

    def update_last_activity(self):
        """Update last activity timestamp"""
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])


class Post(models.Model):
    """
    Forum post/reply model.
    Posts are individual messages within a topic.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name='posts'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_posts'
    )
    content = models.TextField(
        validators=[MinLengthValidator(1), MaxLengthValidator(50000)],
        help_text="Post content (Markdown supported)"
    )

    # Edit tracking
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    edit_reason = models.CharField(max_length=200, blank=True)

    # Moderation
    is_hidden = models.BooleanField(default=False, help_text="Hide post from public view")
    hidden_reason = models.CharField(max_length=200, blank=True)
    hidden_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hidden_posts'
    )

    # IP logging for moderation (educational: shows importance of logging)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, max_length=500)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['topic', 'created_at']),
            models.Index(fields=['author', '-created_at']),
        ]

    def __str__(self):
        return f"Post by {self.author.username} in {self.topic.title}"

    def get_absolute_url(self):
        return f"{self.topic.get_absolute_url()}#post-{self.id}"

    def mark_edited(self, reason=''):
        """Mark post as edited with optional reason"""
        self.is_edited = True
        self.edited_at = timezone.now()
        self.edit_reason = reason[:200] if reason else ''
        self.save(update_fields=['is_edited', 'edited_at', 'edit_reason', 'updated_at'])

    def get_like_count(self):
        return self.likes.count()

    def is_liked_by(self, user):
        if not user.is_authenticated:
            return False
        return self.likes.filter(user=user).exists()


class PostLike(models.Model):
    """
    Post like/upvote model.
    Tracks user likes on posts.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_likes'
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} likes post {self.post_id}"


class UserReputation(models.Model):
    """
    User reputation/karma model.
    Tracks user reputation based on forum activity.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='forum_reputation',
        primary_key=True
    )
    reputation_points = models.IntegerField(default=0)
    posts_count = models.PositiveIntegerField(default=0)
    topics_count = models.PositiveIntegerField(default=0)
    likes_received = models.PositiveIntegerField(default=0)
    likes_given = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-reputation_points']

    def __str__(self):
        return f"{self.user.username}: {self.reputation_points} points"

    def get_rank(self):
        """Get user rank based on reputation"""
        if self.reputation_points >= 1000:
            return 'Expert'
        elif self.reputation_points >= 500:
            return 'Advanced'
        elif self.reputation_points >= 100:
            return 'Member'
        elif self.reputation_points >= 10:
            return 'Newcomer'
        else:
            return 'New User'

    def add_points(self, points, reason=''):
        """Add reputation points"""
        self.reputation_points += points
        self.save(update_fields=['reputation_points', 'updated_at'])

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create reputation record for a user"""
        reputation, created = cls.objects.get_or_create(user=user)
        return reputation


# =============================================================================
# MODERATION MODELS
# =============================================================================

class UserWarning(models.Model):
    """
    User warning model for moderation.
    Tracks warnings issued to users for rule violations with full audit trail.
    """
    SEVERITY_CHOICES = [
        ('notice', 'Notice'),
        ('warning', 'Warning'),
        ('final_warning', 'Final Warning'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_warnings'
    )
    issued_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='issued_warnings'
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default='warning'
    )
    reason = models.TextField(
        max_length=1000,
        validators=[MinLengthValidator(10)],
        help_text="Detailed reason for the warning"
    )
    rule_violated = models.CharField(
        max_length=200,
        blank=True,
        help_text="Specific rule or guideline violated"
    )

    # Link to related content (optional)
    related_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='warnings'
    )
    related_topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='warnings'
    )

    # Warning status
    is_acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    is_expired = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Points for severity tracking (optional gamification)
    points = models.PositiveIntegerField(default=1, help_text="Warning severity points")

    # Audit trail
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['issued_by', '-created_at']),
        ]

    def __str__(self):
        return f"Warning to {self.user.username} by {self.issued_by.username if self.issued_by else 'System'}"

    def acknowledge(self):
        """Mark warning as acknowledged by user"""
        self.is_acknowledged = True
        self.acknowledged_at = timezone.now()
        self.save(update_fields=['is_acknowledged', 'acknowledged_at', 'updated_at'])

    def is_active(self):
        """Check if warning is still active (not expired)"""
        if self.is_expired:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    @classmethod
    def get_active_warnings(cls, user):
        """Get all active warnings for a user"""
        return cls.objects.filter(
            user=user,
            is_expired=False
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
        )

    @classmethod
    def get_warning_count(cls, user):
        """Get count of active warnings for a user"""
        return cls.get_active_warnings(user).count()

    @classmethod
    def get_warning_points(cls, user):
        """Get total warning points for a user"""
        return cls.get_active_warnings(user).aggregate(
            total=models.Sum('points')
        )['total'] or 0


class UserMute(models.Model):
    """
    User mute model for temporary posting restrictions.
    Prevents specific users from posting for a set duration.
    """
    MUTE_REASONS = [
        ('spam', 'Spam'),
        ('harassment', 'Harassment'),
        ('inappropriate', 'Inappropriate Content'),
        ('off_topic', 'Persistent Off-topic Posting'),
        ('violation', 'Rule Violation'),
        ('cooldown', 'Cooling Off Period'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_mutes'
    )
    muted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='issued_mutes'
    )
    reason_type = models.CharField(
        max_length=20,
        choices=MUTE_REASONS,
        default='other'
    )
    reason = models.TextField(
        max_length=1000,
        validators=[MinLengthValidator(10)],
        help_text="Detailed reason for the mute"
    )

    # Duration
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(help_text="When the mute expires")
    is_permanent = models.BooleanField(default=False, help_text="Permanent mute (requires admin to remove)")

    # Scope
    mute_posts = models.BooleanField(default=True, help_text="Prevent creating new posts")
    mute_topics = models.BooleanField(default=True, help_text="Prevent creating new topics")
    mute_likes = models.BooleanField(default=False, help_text="Prevent liking posts")

    # Status
    is_active = models.BooleanField(default=True)
    revoked = models.BooleanField(default=False)
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revoked_mutes'
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=500, blank=True)

    # Related warning (optional)
    related_warning = models.ForeignKey(
        UserWarning,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mutes'
    )

    # Audit trail
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'is_active', 'ends_at']),
        ]

    def __str__(self):
        status = "permanent" if self.is_permanent else f"until {self.ends_at}"
        return f"Mute on {self.user.username} {status}"

    def is_currently_active(self):
        """Check if mute is currently in effect"""
        if not self.is_active or self.revoked:
            return False
        if self.is_permanent:
            return True
        now = timezone.now()
        return self.starts_at <= now <= self.ends_at

    def revoke(self, revoked_by, reason=''):
        """Revoke this mute early"""
        self.revoked = True
        self.revoked_by = revoked_by
        self.revoked_at = timezone.now()
        self.revoke_reason = reason[:500]
        self.is_active = False
        self.save()

    def get_remaining_duration(self):
        """Get remaining mute duration in seconds"""
        if self.is_permanent or not self.is_currently_active():
            return None
        return max(0, (self.ends_at - timezone.now()).total_seconds())

    @classmethod
    def get_active_mute(cls, user):
        """Get currently active mute for a user (if any)"""
        now = timezone.now()
        return cls.objects.filter(
            user=user,
            is_active=True,
            revoked=False
        ).filter(
            models.Q(is_permanent=True) |
            (models.Q(starts_at__lte=now) & models.Q(ends_at__gt=now))
        ).first()

    @classmethod
    def is_user_muted(cls, user, check_posts=True, check_topics=True, check_likes=False):
        """Check if user is currently muted for specific actions"""
        mute = cls.get_active_mute(user)
        if not mute:
            return False
        if check_posts and mute.mute_posts:
            return True
        if check_topics and mute.mute_topics:
            return True
        if check_likes and mute.mute_likes:
            return True
        return False


class Report(models.Model):
    """
    Report/Flag model for content moderation.
    Allows users to report inappropriate content for moderator review.
    """
    REPORT_TYPES = [
        ('spam', 'Spam'),
        ('harassment', 'Harassment or Bullying'),
        ('hate_speech', 'Hate Speech'),
        ('inappropriate', 'Inappropriate Content'),
        ('misinformation', 'Misinformation'),
        ('copyright', 'Copyright Violation'),
        ('personal_info', 'Personal Information Exposure'),
        ('off_topic', 'Off-topic'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('under_review', 'Under Review'),
        ('action_taken', 'Action Taken'),
        ('dismissed', 'Dismissed'),
        ('escalated', 'Escalated'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Reporter
    reporter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='forum_reports_filed'
    )

    # Reported content (one of these should be set)
    reported_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports'
    )
    reported_topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports'
    )
    reported_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='forum_reports_against'
    )

    # Report details
    report_type = models.CharField(
        max_length=20,
        choices=REPORT_TYPES,
        default='other'
    )
    description = models.TextField(
        max_length=2000,
        validators=[MinLengthValidator(10)],
        help_text="Detailed description of the issue"
    )

    # Snapshot of reported content (for audit if original is deleted)
    content_snapshot = models.TextField(
        blank=True,
        help_text="Snapshot of the reported content at time of report"
    )

    # Status and assignment
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_reports'
    )
    priority = models.PositiveSmallIntegerField(
        default=1,
        help_text="Priority level (1=low, 5=critical)"
    )

    # Resolution
    resolution_notes = models.TextField(
        max_length=2000,
        blank=True,
        help_text="Moderator notes on resolution"
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_reports'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Actions taken
    action_warning_issued = models.BooleanField(default=False)
    action_content_hidden = models.BooleanField(default=False)
    action_content_deleted = models.BooleanField(default=False)
    action_user_muted = models.BooleanField(default=False)

    # Reporter feedback
    reporter_notified = models.BooleanField(default=False)
    reporter_feedback = models.CharField(max_length=500, blank=True)
    report_valid = models.BooleanField(null=True, help_text="Whether the report was valid")

    # Audit trail
    reporter_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['reporter', '-created_at']),
            models.Index(fields=['reported_user', '-created_at']),
        ]

    def __str__(self):
        target = "post" if self.reported_post else "topic" if self.reported_topic else "user"
        return f"Report #{str(self.id)[:8]} - {self.report_type} ({target})"

    def get_reported_content_author(self):
        """Get the author of the reported content"""
        if self.reported_post:
            return self.reported_post.author
        if self.reported_topic:
            return self.reported_topic.author
        return self.reported_user

    def assign(self, moderator):
        """Assign report to a moderator"""
        self.assigned_to = moderator
        self.status = 'under_review'
        self.save(update_fields=['assigned_to', 'status', 'updated_at'])

    def resolve(self, resolved_by, notes='', valid=None):
        """Mark report as resolved"""
        self.resolved_by = resolved_by
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.report_valid = valid
        if self.status not in ['dismissed', 'escalated']:
            self.status = 'action_taken' if valid else 'dismissed'
        self.save()

    def escalate(self, notes=''):
        """Escalate report to higher authority"""
        self.status = 'escalated'
        self.priority = min(5, self.priority + 1)
        if notes:
            self.resolution_notes = f"ESCALATED: {notes}\n\n{self.resolution_notes}"
        self.save()

    @classmethod
    def get_pending_count(cls):
        """Get count of pending reports"""
        return cls.objects.filter(status='pending').count()

    @classmethod
    def get_user_report_count(cls, user, days=30):
        """Get count of reports filed by a user in last N days"""
        since = timezone.now() - timezone.timedelta(days=days)
        return cls.objects.filter(reporter=user, created_at__gte=since).count()


class DeletedContent(models.Model):
    """
    Soft delete model for content recovery.
    Stores deleted content with full metadata for audit and recovery.
    """
    CONTENT_TYPES = [
        ('post', 'Post'),
        ('topic', 'Topic'),
    ]

    DELETION_REASONS = [
        ('user_request', 'User Request'),
        ('spam', 'Spam'),
        ('harassment', 'Harassment'),
        ('inappropriate', 'Inappropriate Content'),
        ('violation', 'Rule Violation'),
        ('duplicate', 'Duplicate Content'),
        ('moderation', 'Moderation Decision'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Original content identifiers
    original_id = models.UUIDField(help_text="Original content UUID")
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPES)

    # Original author
    original_author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='deleted_forum_content'
    )
    original_author_username = models.CharField(max_length=150, blank=True)

    # Content snapshot
    title = models.CharField(max_length=200, blank=True)  # For topics
    content = models.TextField(help_text="Full content at time of deletion")
    content_html = models.TextField(blank=True, help_text="Rendered HTML at time of deletion")

    # Context
    category_name = models.CharField(max_length=100, blank=True)
    topic_id = models.UUIDField(null=True, blank=True)
    topic_title = models.CharField(max_length=200, blank=True)

    # Deletion info
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='forum_content_deletions'
    )
    deleted_by_username = models.CharField(max_length=150, blank=True)
    deletion_reason = models.CharField(
        max_length=20,
        choices=DELETION_REASONS,
        default='other'
    )
    deletion_notes = models.TextField(
        max_length=1000,
        blank=True,
        help_text="Additional notes about the deletion"
    )

    # Related report (if deleted due to report)
    related_report = models.ForeignKey(
        Report,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_content'
    )

    # Recovery
    is_recoverable = models.BooleanField(default=True)
    recovered = models.BooleanField(default=False)
    recovered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='forum_content_recoveries'
    )
    recovered_at = models.DateTimeField(null=True, blank=True)

    # Metadata from original
    original_created_at = models.DateTimeField()
    original_updated_at = models.DateTimeField()
    original_ip_address = models.GenericIPAddressField(null=True, blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name_plural = 'Deleted Content'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', '-created_at']),
            models.Index(fields=['original_author', '-created_at']),
            models.Index(fields=['deleted_by', '-created_at']),
        ]

    def __str__(self):
        return f"Deleted {self.content_type}: {self.title or str(self.original_id)[:8]}"

    @classmethod
    def create_from_post(cls, post, deleted_by, reason='moderation', notes='', report=None):
        """Create a DeletedContent record from a Post"""
        from .Utils.markdown_utils import render_markdown

        return cls.objects.create(
            original_id=post.id,
            content_type='post',
            original_author=post.author,
            original_author_username=post.author.username,
            content=post.content,
            content_html=render_markdown(post.content),
            topic_id=post.topic.id,
            topic_title=post.topic.title,
            category_name=post.topic.category.name,
            deleted_by=deleted_by,
            deleted_by_username=deleted_by.username,
            deletion_reason=reason,
            deletion_notes=notes,
            related_report=report,
            original_created_at=post.created_at,
            original_updated_at=post.updated_at,
            original_ip_address=post.ip_address,
        )

    @classmethod
    def create_from_topic(cls, topic, deleted_by, reason='moderation', notes='', report=None):
        """Create a DeletedContent record from a Topic"""
        first_post = topic.get_first_post()
        content = first_post.content if first_post else ''

        from .Utils.markdown_utils import render_markdown

        return cls.objects.create(
            original_id=topic.id,
            content_type='topic',
            original_author=topic.author,
            original_author_username=topic.author.username,
            title=topic.title,
            content=content,
            content_html=render_markdown(content) if content else '',
            category_name=topic.category.name,
            deleted_by=deleted_by,
            deleted_by_username=deleted_by.username,
            deletion_reason=reason,
            deletion_notes=notes,
            related_report=report,
            original_created_at=topic.created_at,
            original_updated_at=topic.updated_at,
            original_ip_address=first_post.ip_address if first_post else None,
        )


class PostEditHistory(models.Model):
    """
    Edit history model for post revisions.
    Tracks all edits with ability to view and restore previous versions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='edit_history'
    )

    # Editor info
    edited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='forum_edits_made'
    )
    edited_by_username = models.CharField(max_length=150)

    # Content versions
    content_before = models.TextField(help_text="Content before this edit")
    content_after = models.TextField(help_text="Content after this edit")

    # Edit metadata
    edit_reason = models.CharField(max_length=200, blank=True)
    version_number = models.PositiveIntegerField(default=1)

    # Change tracking
    is_minor_edit = models.BooleanField(default=False)
    characters_added = models.IntegerField(default=0)
    characters_removed = models.IntegerField(default=0)

    # Audit
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['post', '-created_at']),
            models.Index(fields=['edited_by', '-created_at']),
        ]

    def __str__(self):
        return f"Edit v{self.version_number} of post {self.post_id}"

    @classmethod
    def create_revision(cls, post, edited_by, content_before, content_after, reason='', ip_address=None, user_agent=''):
        """Create a new edit history entry"""
        # Get the latest version number
        latest = cls.objects.filter(post=post).order_by('-version_number').first()
        version = (latest.version_number + 1) if latest else 1

        # Calculate changes
        chars_added = max(0, len(content_after) - len(content_before))
        chars_removed = max(0, len(content_before) - len(content_after))
        is_minor = abs(len(content_after) - len(content_before)) < 50

        return cls.objects.create(
            post=post,
            edited_by=edited_by,
            edited_by_username=edited_by.username,
            content_before=content_before,
            content_after=content_after,
            edit_reason=reason[:200],
            version_number=version,
            is_minor_edit=is_minor,
            characters_added=chars_added,
            characters_removed=chars_removed,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else '',
        )


class StaffNote(models.Model):
    """
    Staff-only notes on user profiles.
    Private annotations visible only to staff members.
    """
    NOTE_TYPES = [
        ('general', 'General Note'),
        ('warning', 'Warning Related'),
        ('behavior', 'Behavior Pattern'),
        ('positive', 'Positive Note'),
        ('context', 'Context/Background'),
        ('watch', 'Under Watch'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_staff_notes'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='forum_staff_notes_created'
    )

    # Note content
    note_type = models.CharField(
        max_length=20,
        choices=NOTE_TYPES,
        default='general'
    )
    content = models.TextField(
        max_length=5000,
        validators=[MinLengthValidator(5)],
        help_text="Private note content (only visible to staff)"
    )

    # Importance
    is_pinned = models.BooleanField(default=False, help_text="Pin to top of notes")
    is_important = models.BooleanField(default=False, help_text="Mark as important")

    # Related items (optional)
    related_warning = models.ForeignKey(
        UserWarning,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_notes'
    )
    related_report = models.ForeignKey(
        Report,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_notes'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-is_important', '-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['created_by', '-created_at']),
        ]

    def __str__(self):
        return f"Note on {self.user.username} by {self.created_by.username if self.created_by else 'Unknown'}"


class ModerationLog(models.Model):
    """
    Comprehensive moderation action log.
    Tracks all moderation actions for accountability and audit.
    """
    ACTION_TYPES = [
        ('warning_issued', 'Warning Issued'),
        ('warning_acknowledged', 'Warning Acknowledged'),
        ('mute_applied', 'Mute Applied'),
        ('mute_revoked', 'Mute Revoked'),
        ('post_hidden', 'Post Hidden'),
        ('post_unhidden', 'Post Unhidden'),
        ('post_deleted', 'Post Deleted'),
        ('topic_locked', 'Topic Locked'),
        ('topic_unlocked', 'Topic Unlocked'),
        ('topic_pinned', 'Topic Pinned'),
        ('topic_unpinned', 'Topic Unpinned'),
        ('topic_deleted', 'Topic Deleted'),
        ('report_assigned', 'Report Assigned'),
        ('report_resolved', 'Report Resolved'),
        ('report_escalated', 'Report Escalated'),
        ('content_recovered', 'Content Recovered'),
        ('staff_note_added', 'Staff Note Added'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who performed the action
    moderator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='moderation_actions'
    )
    moderator_username = models.CharField(max_length=150)

    # What action was taken
    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    description = models.TextField(max_length=2000, blank=True)

    # Target of action
    target_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_actions_received'
    )
    target_user_username = models.CharField(max_length=150, blank=True)
    target_post_id = models.UUIDField(null=True, blank=True)
    target_topic_id = models.UUIDField(null=True, blank=True)

    # Related objects
    related_warning = models.ForeignKey(
        UserWarning,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    related_mute = models.ForeignKey(
        UserMute,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    related_report = models.ForeignKey(
        Report,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Audit
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['moderator', '-created_at']),
            models.Index(fields=['action_type', '-created_at']),
            models.Index(fields=['target_user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.action_type} by {self.moderator_username} at {self.created_at}"

    @classmethod
    def log_action(cls, moderator, action_type, description='', target_user=None,
                   target_post_id=None, target_topic_id=None, ip_address=None,
                   related_warning=None, related_mute=None, related_report=None):
        """Create a new moderation log entry"""
        return cls.objects.create(
            moderator=moderator,
            moderator_username=moderator.username,
            action_type=action_type,
            description=description,
            target_user=target_user,
            target_user_username=target_user.username if target_user else '',
            target_post_id=target_post_id,
            target_topic_id=target_topic_id,
            ip_address=ip_address,
            related_warning=related_warning,
            related_mute=related_mute,
            related_report=related_report,
        )


# =============================================================================
# TAG SYSTEM MODELS
# =============================================================================

class Tag(models.Model):
    """
    Tag model for topic categorization.
    Tags allow users to add keywords to topics for better organization and filtering.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=50,
        unique=True,
        validators=[MinLengthValidator(2), MaxLengthValidator(50)],
        help_text="Tag name (lowercase, alphanumeric with hyphens)"
    )
    slug = models.SlugField(max_length=60, unique=True)
    description = models.CharField(max_length=200, blank=True)
    color = models.CharField(
        max_length=7,
        default='#667eea',
        help_text="Hex color for the tag badge"
    )
    usage_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='forum_tags_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-usage_count', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.name.lower().strip()
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def update_usage_count(self):
        """Update the cached usage count atomically"""
        Tag.objects.filter(pk=self.pk).update(
            usage_count=models.Subquery(
                TopicTag.objects.filter(tag=self).values('tag').annotate(
                    cnt=models.Count('id')
                ).values('cnt')[:1]
            )
        )


class TopicTag(models.Model):
    """
    Many-to-many relationship between topics and tags.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name='topic_tags'
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name='tagged_topics'
    )
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='forum_tags_added'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('topic', 'tag')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tag.name} on {self.topic.title}"


# =============================================================================
# POST BOOKMARKS MODEL
# =============================================================================

class PostBookmark(models.Model):
    """
    Bookmark model for saving posts for later reading.
    Users can bookmark posts and manage them from a dedicated page.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_bookmarks'
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='bookmarks'
    )
    note = models.CharField(
        max_length=500,
        blank=True,
        help_text="Optional personal note about this bookmark"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ('user', 'post')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} bookmarked post in {self.post.topic.title}"


# =============================================================================
# MENTION MODEL
# =============================================================================

class Mention(models.Model):
    """
    @Mention model for user notifications.
    Tracks when a user is mentioned in a post using @username syntax.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='mentions'
    )
    mentioned_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_mentions'
    )
    mentioned_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_mentions_made'
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['mentioned_user', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"@{self.mentioned_user.username} by {self.mentioned_by.username}"

    def mark_read(self):
        """Mark mention as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


# =============================================================================
# USER BLOCKING MODEL
# =============================================================================

class UserBlock(models.Model):
    """
    User blocking model for privacy controls.
    When a user blocks another, the blocked user's posts are hidden from them.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blocker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_blocking'
    )
    blocked = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_blocked_by'
    )
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ('blocker', 'blocked')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked.username}"

    @classmethod
    def is_blocked(cls, blocker, blocked_user):
        """Check if blocker has blocked blocked_user"""
        return cls.objects.filter(blocker=blocker, blocked=blocked_user).exists()

    @classmethod
    def get_blocked_user_ids(cls, user):
        """Get set of user IDs that the user has blocked"""
        return set(
            cls.objects.filter(blocker=user).values_list('blocked_id', flat=True)
        )


# =============================================================================
# STICKY POST MODEL
# =============================================================================

class StickyPost(models.Model):
    """
    Sticky/pinned post within a topic.
    Allows moderators to pin important replies to the top of a topic thread.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.OneToOneField(
        Post,
        on_delete=models.CASCADE,
        related_name='sticky'
    )
    pinned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='forum_posts_pinned'
    )
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Sticky: post by {self.post.author.username} in {self.post.topic.title}"


# =============================================================================
# IMAGE UPLOAD MODEL
# =============================================================================

class ForumImage(models.Model):
    """
    Image upload model for forum posts.
    Supports direct image uploads with moderation queue.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_images'
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='images'
    )
    image = models.ImageField(
        upload_to='forum/images/%Y/%m/',
        help_text="Uploaded image file"
    )
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(
        default=0,
        help_text="File size in bytes"
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Alternative text for accessibility"
    )

    # Moderation
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='approved'
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='forum_images_reviewed'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['uploaded_by', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"Image by {self.uploaded_by.username}: {self.original_filename}"

    def get_url(self):
        """Get the URL for the image"""
        if self.image:
            return self.image.url
        return ''


# =============================================================================
# FORUM ROLE MODEL
# =============================================================================

class ForumRole(models.Model):
    """
    Custom forum moderator role model.
    Provides granular permissions for different levels of moderators.
    """
    ROLE_LEVELS = [
        ('junior_mod', 'Junior Moderator'),
        ('moderator', 'Moderator'),
        ('senior_mod', 'Senior Moderator'),
        ('lead_mod', 'Lead Moderator'),
        ('admin', 'Administrator'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='forum_role'
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_LEVELS,
        default='junior_mod'
    )

    # Granular permissions
    can_hide_posts = models.BooleanField(default=True)
    can_delete_posts = models.BooleanField(default=False)
    can_lock_topics = models.BooleanField(default=True)
    can_pin_topics = models.BooleanField(default=False)
    can_issue_warnings = models.BooleanField(default=True)
    can_mute_users = models.BooleanField(default=False)
    can_manage_reports = models.BooleanField(default=True)
    can_manage_tags = models.BooleanField(default=True)
    can_review_images = models.BooleanField(default=True)
    can_manage_announcements = models.BooleanField(default=False)
    can_view_staff_notes = models.BooleanField(default=True)
    can_add_staff_notes = models.BooleanField(default=True)
    can_manage_roles = models.BooleanField(default=False)

    # Assignment info
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='forum_roles_assigned'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(max_length=500, blank=True)

    class Meta:
        ordering = ['role']

    def __str__(self):
        return f"{self.user.username}: {self.get_role_display()}"

    def get_role_color(self):
        """Get color for role badge display"""
        colors = {
            'junior_mod': '#10b981',
            'moderator': '#3b82f6',
            'senior_mod': '#8b5cf6',
            'lead_mod': '#f59e0b',
            'admin': '#ef4444',
        }
        return colors.get(self.role, '#6b7280')


# =============================================================================
# FORUM NOTIFICATION MODEL
# =============================================================================

class ForumNotification(models.Model):
    """
    Forum notification model.
    Handles notifications for replies, mentions, and moderation actions.
    """
    NOTIFICATION_TYPES = [
        ('mention', 'You were mentioned'),
        ('reply', 'New reply to your topic'),
        ('quote', 'Your post was quoted'),
        ('like', 'Your post was liked'),
        ('bookmark', 'Your post was bookmarked'),
        ('warning', 'You received a warning'),
        ('mute', 'You have been muted'),
        ('report_resolved', 'Your report has been resolved'),
        ('topic_locked', 'A topic you follow was locked'),
        ('moderation', 'Moderation action on your content'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_notifications'
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='forum_notifications_sent'
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES
    )
    message = models.CharField(max_length=500)
    link = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL to the relevant content"
    )

    # Related content (optional)
    related_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    related_topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )

    # Status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"Notification for {self.recipient.username}: {self.notification_type}"

    def mark_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    @classmethod
    def create_notification(cls, recipient, notification_type, message,
                            sender=None, link='', related_post=None,
                            related_topic=None):
        """Create a new notification for a user"""
        # Do not notify self
        if sender and recipient == sender:
            return None
        return cls.objects.create(
            recipient=recipient,
            sender=sender,
            notification_type=notification_type,
            message=message,
            link=link,
            related_post=related_post,
            related_topic=related_topic,
        )

    @classmethod
    def get_unread_count(cls, user):
        """Get count of unread notifications"""
        return cls.objects.filter(recipient=user, is_read=False).count()


# =============================================================================
# REPUTATION DECAY LOG MODEL
# =============================================================================

class ReputationDecayLog(models.Model):
    """
    Tracks reputation point decay for inactive users.
    Keeps rankings current by decaying points for users who are no longer active.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_reputation_decay_logs'
    )
    points_before = models.IntegerField()
    points_after = models.IntegerField()
    points_decayed = models.IntegerField()
    reason = models.CharField(max_length=200, default='Inactivity decay')
    decay_date = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-decay_date']
        indexes = [
            models.Index(fields=['user', '-decay_date']),
        ]

    def __str__(self):
        return f"Decay for {self.user.username}: -{self.points_decayed} points"
