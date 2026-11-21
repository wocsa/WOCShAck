"""
Moderation admin configuration.
Provides admin interface for centralized moderation management.
"""
from django.contrib import admin
from .models import (
    ModerationQueue, ContentAction,
    Report, ReportNote,
    UserWarning, UserMute, UserBan, UserAppeal,
    AutoModRule, AutoModLog,
    AuditLog, AuditRetention,
    StaffRole, StaffAssignment, StaffMetrics,
)


# =============================================================================
# CONTENT MODERATION
# =============================================================================

@admin.register(ModerationQueue)
class ModerationQueueAdmin(admin.ModelAdmin):
    list_display = ('id', 'source_module', 'status', 'priority', 'auto_flagged', 'assigned_to', 'created_at', 'processed_at')
    list_filter = ('status', 'priority', 'source_module', 'auto_flagged', 'created_at')
    search_fields = ('auto_flag_reason', 'assigned_to__username')
    raw_id_fields = ('assigned_to',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Content Reference', {
            'fields': ('content_type', 'object_id', 'source_module')
        }),
        ('Status', {
            'fields': ('status', 'priority', 'assigned_to', 'processed_at')
        }),
        ('Auto-Flagging', {
            'fields': ('auto_flagged', 'auto_flag_reason'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(ContentAction)
class ContentActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'action_type', 'actor', 'is_reversed', 'created_at')
    list_filter = ('action_type', 'is_reversed', 'created_at')
    search_fields = ('actor__username', 'reason', 'internal_notes')
    raw_id_fields = ('actor',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Content Reference', {
            'fields': ('content_type', 'object_id')
        }),
        ('Action Details', {
            'fields': ('action_type', 'actor', 'reason', 'internal_notes')
        }),
        ('Content Snapshot', {
            'fields': ('original_content',),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_reversed',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


# =============================================================================
# REPORT MANAGEMENT
# =============================================================================

class ReportNoteInline(admin.TabularInline):
    model = ReportNote
    extra = 0
    raw_id_fields = ('author',)
    readonly_fields = ('created_at',)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'report_type', 'status', 'priority', 'reporter', 'assigned_to', 'is_valid', 'created_at')
    list_filter = ('report_type', 'status', 'priority', 'is_valid', 'created_at')
    search_fields = ('reporter__username', 'assigned_to__username', 'description', 'resolution_notes')
    raw_id_fields = ('reporter', 'assigned_to')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'resolved_at')
    inlines = [ReportNoteInline]

    fieldsets = (
        ('Report Details', {
            'fields': ('reporter', 'report_type', 'description', 'evidence', 'priority')
        }),
        ('Content Reference', {
            'fields': ('content_type', 'object_id')
        }),
        ('Status & Assignment', {
            'fields': ('status', 'assigned_to')
        }),
        ('Resolution', {
            'fields': ('resolution_type', 'resolution_notes', 'is_valid', 'feedback_sent', 'resolved_at')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(ReportNote)
class ReportNoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'report', 'author', 'visibility', 'created_at')
    list_filter = ('visibility', 'created_at')
    search_fields = ('author__username', 'content')
    raw_id_fields = ('report', 'author')
    readonly_fields = ('created_at',)


# =============================================================================
# USER SANCTIONS
# =============================================================================

@admin.register(UserWarning)
class UserWarningAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'warning_type', 'severity', 'points', 'issuer', 'acknowledged', 'is_expired', 'created_at')
    list_filter = ('warning_type', 'severity', 'acknowledged', 'created_at')
    search_fields = ('user__username', 'issuer__username', 'reason')
    raw_id_fields = ('user', 'issuer')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'acknowledged_at')

    fieldsets = (
        ('Warning Details', {
            'fields': ('user', 'issuer', 'warning_type', 'severity', 'points', 'reason', 'evidence')
        }),
        ('Status', {
            'fields': ('acknowledged', 'acknowledged_at', 'expires_at')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserMute)
class UserMuteAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'scope', 'issuer', 'is_permanent', 'is_active', 'expires_at', 'created_at')
    list_filter = ('scope', 'is_permanent', 'created_at')
    search_fields = ('user__username', 'issuer__username', 'reason')
    raw_id_fields = ('user', 'issuer', 'lifted_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Mute Details', {
            'fields': ('user', 'issuer', 'scope', 'reason')
        }),
        ('Duration', {
            'fields': ('duration', 'is_permanent', 'expires_at')
        }),
        ('Lift Info', {
            'fields': ('lifted_by', 'lifted_at', 'lift_reason'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserBan)
class UserBanAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'ban_type', 'issuer', 'is_active', 'allow_appeal', 'expires_at', 'created_at')
    list_filter = ('ban_type', 'allow_appeal', 'created_at')
    search_fields = ('user__username', 'issuer__username', 'reason')
    raw_id_fields = ('user', 'issuer', 'lifted_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Ban Details', {
            'fields': ('user', 'issuer', 'ban_type', 'reason', 'evidence')
        }),
        ('Duration & IP', {
            'fields': ('duration', 'expires_at', 'ip_addresses', 'allow_appeal')
        }),
        ('Lift Info', {
            'fields': ('lifted_by', 'lifted_at', 'lift_reason'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserAppeal)
class UserAppealAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'sanction_type', 'status', 'outcome', 'reviewer', 'created_at', 'reviewed_at')
    list_filter = ('sanction_type', 'status', 'outcome', 'created_at')
    search_fields = ('user__username', 'reviewer__username', 'appeal_text', 'decision_notes')
    raw_id_fields = ('user', 'reviewer')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Appeal Details', {
            'fields': ('user', 'sanction_type', 'sanction_id', 'appeal_text')
        }),
        ('Review', {
            'fields': ('status', 'reviewer', 'decision_notes', 'outcome', 'reviewed_at')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


# =============================================================================
# AUTOMATED MODERATION
# =============================================================================

@admin.register(AutoModRule)
class AutoModRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'trigger_type', 'action', 'is_active', 'priority', 'created_by', 'created_at')
    list_filter = ('trigger_type', 'action', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'trigger_value')
    raw_id_fields = ('created_by',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Rule Details', {
            'fields': ('name', 'description', 'is_active', 'priority')
        }),
        ('Trigger', {
            'fields': ('trigger_type', 'trigger_value')
        }),
        ('Action', {
            'fields': ('action', 'action_params', 'scope')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AutoModLog)
class AutoModLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'rule', 'user', 'action_taken', 'confidence_score', 'review_status', 'created_at')
    list_filter = ('review_status', 'action_taken', 'created_at')
    search_fields = ('user__username', 'trigger_match', 'action_taken')
    raw_id_fields = ('rule', 'user', 'reviewed_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Log Details', {
            'fields': ('rule', 'user', 'action_taken', 'trigger_match', 'confidence_score')
        }),
        ('Content Reference', {
            'fields': ('content_type', 'object_id')
        }),
        ('Review', {
            'fields': ('review_status', 'reviewed_by')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


# =============================================================================
# AUDIT LOGGING
# =============================================================================

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'actor', 'action_type', 'action_name', 'affected_user', 'result', 'ip_address', 'created_at')
    list_filter = ('action_type', 'result', 'created_at')
    search_fields = ('actor__username', 'affected_user__username', 'action_name', 'ip_address', 'session_id')
    raw_id_fields = ('actor', 'affected_user')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Action', {
            'fields': ('actor', 'action_type', 'action_name', 'result')
        }),
        ('Target', {
            'fields': ('target_type', 'target_id', 'affected_user')
        }),
        ('Details', {
            'fields': ('details',)
        }),
        ('Request Info', {
            'fields': ('ip_address', 'user_agent', 'session_id'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(AuditRetention)
class AuditRetentionAdmin(admin.ModelAdmin):
    list_display = ('category', 'retention_days', 'archive_after_days', 'delete_after_days')
    list_filter = ('category',)


# =============================================================================
# STAFF MANAGEMENT
# =============================================================================

@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'can_assign')
    search_fields = ('name', 'description')

    fieldsets = (
        ('Role Details', {
            'fields': ('name', 'description', 'permissions', 'can_assign')
        }),
    )


@admin.register(StaffAssignment)
class StaffAssignmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'assigned_by', 'start_date', 'end_date', 'is_active', 'daily_action_limit')
    list_filter = ('role', 'start_date', 'end_date')
    search_fields = ('user__username', 'assigned_by__username', 'notes')
    raw_id_fields = ('user', 'role', 'assigned_by')

    fieldsets = (
        ('Assignment', {
            'fields': ('user', 'role', 'assigned_by')
        }),
        ('Access', {
            'fields': ('module_access', 'daily_action_limit')
        }),
        ('Period', {
            'fields': ('start_date', 'end_date', 'notes')
        }),
    )


@admin.register(StaffMetrics)
class StaffMetricsAdmin(admin.ModelAdmin):
    list_display = ('staff', 'date', 'reports_handled', 'content_reviewed', 'warnings_issued', 'accuracy_rate', 'overturned_appeals')
    list_filter = ('date',)
    search_fields = ('staff__username',)
    raw_id_fields = ('staff',)
    date_hierarchy = 'date'

