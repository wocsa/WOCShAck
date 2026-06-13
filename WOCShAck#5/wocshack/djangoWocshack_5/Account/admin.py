"""
Admin configuration for Account module.
"""
from django.contrib import admin
from .models import UserProfile, LoginHistory, BackupCode, UserSession, PasswordResetToken, PasswordResetRateLimit, PurchasedFeature, ProfileTheme


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'bid', 'is_activated', 'has_2fa')
    list_filter = ('is_activated',)
    search_fields = ('user__username', 'user__email', 'bid')
    readonly_fields = ('bid',)

    def has_2fa(self, obj):
        return bool(obj.totp_key)
    has_2fa.boolean = True
    has_2fa.short_description = '2FA Enabled'


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'timestamp', 'status', 'ip_address', 'device_type')
    list_filter = ('status', 'device_type', 'timestamp')
    search_fields = ('user__username', 'ip_address')
    date_hierarchy = 'timestamp'
    readonly_fields = ('user', 'timestamp', 'ip_address', 'user_agent', 'status', 'device_type')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BackupCode)
class BackupCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'is_used', 'used_at')
    list_filter = ('is_used', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('user', 'code_hash', 'created_at', 'used_at', 'is_used')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'device_type', 'ip_address', 'last_activity', 'is_active', 'is_current')
    list_filter = ('is_active', 'device_type', 'last_activity')
    search_fields = ('user__username', 'ip_address')
    readonly_fields = ('user', 'session_key', 'created_at', 'last_activity', 'ip_address', 'user_agent', 'device_type')

    def has_add_permission(self, request):
        return False


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'is_used', 'ip_address')
    list_filter = ('is_used', 'created_at')
    search_fields = ('user__username', 'user__email', 'ip_address')
    readonly_fields = ('user', 'token', 'created_at', 'expires_at', 'is_used', 'used_at', 'ip_address')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PasswordResetRateLimit)
class PasswordResetRateLimitAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'email', 'requested_at')
    list_filter = ('requested_at',)
    search_fields = ('ip_address', 'email')
    readonly_fields = ('ip_address', 'email', 'requested_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PurchasedFeature)
class PurchasedFeatureAdmin(admin.ModelAdmin):
    list_display = ('user', 'feature_type', 'price_paid', 'purchased_at', 'is_active')
    list_filter = ('feature_type', 'is_active', 'purchased_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user', 'feature_type', 'price_paid', 'purchased_at')
    date_hierarchy = 'purchased_at'

    def has_add_permission(self, request):
        return False


@admin.register(ProfileTheme)
class ProfileThemeAdmin(admin.ModelAdmin):
    list_display = ('user', 'primary_color', 'secondary_color', 'bio_background_color')
    search_fields = ('user__username',)
