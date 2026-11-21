"""
Forum admin configuration.
Provides admin interface for managing forum content and moderation.
"""
from django.contrib import admin
from .models import (
    Category, Topic, Post, PostLike, UserReputation,
    UserWarning, UserMute, Report, DeletedContent,
    PostEditHistory, StaffNote, ModerationLog,
    Tag, TopicTag, PostBookmark, Mention,
    UserBlock, StickyPost, ForumImage, ForumRole,
    ForumNotification, ReputationDecayLog
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order', 'is_active', 'is_private', 'staff_only', 'topic_count', 'created_at')
    list_filter = ('is_active', 'is_private', 'staff_only')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('order', 'name')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'icon', 'order')
        }),
        ('Access Control', {
            'fields': ('is_private', 'staff_only')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )

    def topic_count(self, obj):
        return obj.topics.count()
    topic_count.short_description = 'Topics'


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'author', 'is_pinned', 'is_locked', 'view_count', 'reply_count', 'created_at')
    list_filter = ('category', 'is_pinned', 'is_locked', 'created_at')
    search_fields = ('title', 'author__username')
    raw_id_fields = ('author', 'category')
    date_hierarchy = 'created_at'

    def reply_count(self, obj):
        return obj.posts.count() - 1  # Exclude the original post
    reply_count.short_description = 'Replies'


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'topic', 'author', 'is_edited', 'is_hidden', 'like_count', 'created_at')
    list_filter = ('is_edited', 'is_hidden', 'created_at')
    search_fields = ('content', 'author__username', 'topic__title')
    raw_id_fields = ('author', 'topic', 'hidden_by')
    date_hierarchy = 'created_at'

    def like_count(self, obj):
        return obj.likes.count()
    like_count.short_description = 'Likes'


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'created_at')
    list_filter = ('created_at',)
    raw_id_fields = ('user', 'post')


@admin.register(UserReputation)
class UserReputationAdmin(admin.ModelAdmin):
    list_display = ('user', 'reputation_points', 'posts_count', 'topics_count', 'likes_received')
    search_fields = ('user__username',)
    raw_id_fields = ('user',)


# =============================================================================
# MODERATION ADMIN
# =============================================================================

@admin.register(UserWarning)
class UserWarningAdmin(admin.ModelAdmin):
    list_display = ('user', 'severity', 'issued_by', 'rule_violated', 'is_acknowledged', 'is_expired', 'created_at')
    list_filter = ('severity', 'is_acknowledged', 'is_expired', 'created_at')
    search_fields = ('user__username', 'issued_by__username', 'reason', 'rule_violated')
    raw_id_fields = ('user', 'issued_by', 'related_post', 'related_topic')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at', 'acknowledged_at')

    fieldsets = (
        ('Warning Details', {
            'fields': ('user', 'issued_by', 'severity', 'reason', 'rule_violated', 'points')
        }),
        ('Related Content', {
            'fields': ('related_post', 'related_topic'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_acknowledged', 'acknowledged_at', 'is_expired', 'expires_at')
        }),
        ('Audit', {
            'fields': ('ip_address', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserMute)
class UserMuteAdmin(admin.ModelAdmin):
    list_display = ('user', 'reason_type', 'muted_by', 'starts_at', 'ends_at', 'is_permanent', 'is_active', 'revoked')
    list_filter = ('reason_type', 'is_permanent', 'is_active', 'revoked', 'created_at')
    search_fields = ('user__username', 'muted_by__username', 'reason')
    raw_id_fields = ('user', 'muted_by', 'revoked_by', 'related_warning')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at', 'revoked_at')

    fieldsets = (
        ('Mute Details', {
            'fields': ('user', 'muted_by', 'reason_type', 'reason')
        }),
        ('Duration', {
            'fields': ('starts_at', 'ends_at', 'is_permanent')
        }),
        ('Scope', {
            'fields': ('mute_posts', 'mute_topics', 'mute_likes')
        }),
        ('Status', {
            'fields': ('is_active', 'revoked', 'revoked_by', 'revoked_at', 'revoke_reason')
        }),
        ('Related', {
            'fields': ('related_warning',),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'report_type', 'status', 'priority', 'reporter', 'assigned_to', 'created_at')
    list_filter = ('report_type', 'status', 'priority', 'created_at')
    search_fields = ('reporter__username', 'assigned_to__username', 'description')
    raw_id_fields = ('reporter', 'reported_post', 'reported_topic', 'reported_user', 'assigned_to', 'resolved_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at', 'resolved_at', 'content_snapshot')

    fieldsets = (
        ('Report Details', {
            'fields': ('reporter', 'report_type', 'description', 'priority')
        }),
        ('Reported Content', {
            'fields': ('reported_post', 'reported_topic', 'reported_user', 'content_snapshot')
        }),
        ('Status & Assignment', {
            'fields': ('status', 'assigned_to')
        }),
        ('Resolution', {
            'fields': ('resolution_notes', 'resolved_by', 'resolved_at', 'report_valid')
        }),
        ('Actions Taken', {
            'fields': ('action_warning_issued', 'action_content_hidden', 'action_content_deleted', 'action_user_muted')
        }),
        ('Reporter Feedback', {
            'fields': ('reporter_notified', 'reporter_feedback'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('reporter_ip', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DeletedContent)
class DeletedContentAdmin(admin.ModelAdmin):
    list_display = ('content_type', 'title', 'original_author_username', 'deleted_by_username', 'deletion_reason', 'is_recoverable', 'recovered', 'created_at')
    list_filter = ('content_type', 'deletion_reason', 'is_recoverable', 'recovered', 'created_at')
    search_fields = ('title', 'content', 'original_author_username', 'deleted_by_username')
    raw_id_fields = ('original_author', 'deleted_by', 'recovered_by', 'related_report')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'recovered_at', 'original_id', 'original_created_at', 'original_updated_at')

    fieldsets = (
        ('Original Content', {
            'fields': ('original_id', 'content_type', 'original_author', 'original_author_username', 'title', 'content')
        }),
        ('Context', {
            'fields': ('category_name', 'topic_id', 'topic_title')
        }),
        ('Deletion Info', {
            'fields': ('deleted_by', 'deleted_by_username', 'deletion_reason', 'deletion_notes', 'related_report')
        }),
        ('Recovery', {
            'fields': ('is_recoverable', 'recovered', 'recovered_by', 'recovered_at')
        }),
        ('Original Metadata', {
            'fields': ('original_created_at', 'original_updated_at', 'original_ip_address'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PostEditHistory)
class PostEditHistoryAdmin(admin.ModelAdmin):
    list_display = ('post', 'edited_by_username', 'version_number', 'is_minor_edit', 'characters_added', 'characters_removed', 'created_at')
    list_filter = ('is_minor_edit', 'created_at')
    search_fields = ('post__topic__title', 'edited_by_username', 'edit_reason')
    raw_id_fields = ('post', 'edited_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'version_number', 'characters_added', 'characters_removed')


@admin.register(StaffNote)
class StaffNoteAdmin(admin.ModelAdmin):
    list_display = ('user', 'note_type', 'created_by', 'is_pinned', 'is_important', 'created_at')
    list_filter = ('note_type', 'is_pinned', 'is_important', 'created_at')
    search_fields = ('user__username', 'created_by__username', 'content')
    raw_id_fields = ('user', 'created_by', 'related_warning', 'related_report')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ModerationLog)
class ModerationLogAdmin(admin.ModelAdmin):
    list_display = ('action_type', 'moderator_username', 'target_user_username', 'created_at')
    list_filter = ('action_type', 'created_at')
    search_fields = ('moderator_username', 'target_user_username', 'description')
    raw_id_fields = ('moderator', 'target_user', 'related_warning', 'related_mute', 'related_report')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)


# =============================================================================
# TAG SYSTEM ADMIN
# =============================================================================

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'usage_count', 'color', 'created_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    raw_id_fields = ('created_by',)
    readonly_fields = ('usage_count', 'created_at')


@admin.register(TopicTag)
class TopicTagAdmin(admin.ModelAdmin):
    list_display = ('topic', 'tag', 'added_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('topic__title', 'tag__name')
    raw_id_fields = ('topic', 'tag', 'added_by')
    readonly_fields = ('created_at',)


# =============================================================================
# BOOKMARK ADMIN
# =============================================================================

@admin.register(PostBookmark)
class PostBookmarkAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'note', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'post__topic__title', 'note')
    raw_id_fields = ('user', 'post')
    readonly_fields = ('created_at',)


# =============================================================================
# MENTION ADMIN
# =============================================================================

@admin.register(Mention)
class MentionAdmin(admin.ModelAdmin):
    list_display = ('mentioned_user', 'mentioned_by', 'post', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('mentioned_user__username', 'mentioned_by__username', 'post__topic__title')
    raw_id_fields = ('mentioned_user', 'mentioned_by', 'post')
    readonly_fields = ('created_at',)


# =============================================================================
# USER BLOCK ADMIN
# =============================================================================

@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = ('blocker', 'blocked', 'reason', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('blocker__username', 'blocked__username', 'reason')
    raw_id_fields = ('blocker', 'blocked')
    readonly_fields = ('created_at',)


# =============================================================================
# STICKY POST ADMIN
# =============================================================================

@admin.register(StickyPost)
class StickyPostAdmin(admin.ModelAdmin):
    list_display = ('post', 'pinned_by', 'reason', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('post__topic__title', 'pinned_by__username', 'reason')
    raw_id_fields = ('post', 'pinned_by')
    readonly_fields = ('created_at',)


# =============================================================================
# FORUM IMAGE ADMIN
# =============================================================================

@admin.register(ForumImage)
class ForumImageAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'uploaded_by', 'file_size', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('original_filename', 'uploaded_by__username')
    raw_id_fields = ('uploaded_by', 'post', 'reviewed_by')
    readonly_fields = ('created_at',)


# =============================================================================
# FORUM ROLE ADMIN
# =============================================================================

@admin.register(ForumRole)
class ForumRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'assigned_by', 'assigned_at')
    list_filter = ('role', 'assigned_at')
    search_fields = ('user__username', 'assigned_by__username')
    raw_id_fields = ('user', 'assigned_by')
    readonly_fields = ('assigned_at',)


# =============================================================================
# NOTIFICATION ADMIN
# =============================================================================

@admin.register(ForumNotification)
class ForumNotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'sender', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'sender__username', 'message')
    raw_id_fields = ('recipient', 'sender', 'related_post', 'related_topic')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'read_at')


# =============================================================================
# REPUTATION DECAY LOG ADMIN
# =============================================================================

@admin.register(ReputationDecayLog)
class ReputationDecayLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'points_decayed', 'reason', 'decay_date')
    list_filter = ('decay_date',)
    search_fields = ('user__username', 'reason')
    raw_id_fields = ('user',)
    date_hierarchy = 'decay_date'
    readonly_fields = ('decay_date',)
