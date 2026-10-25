"""
API module admin configuration.
Provides admin interface for CSS marketplace management.
"""
from django.contrib import admin
from .models import Css, Purchase, CssCategory, DownloadLog, ApiKey, ApiKeyUsage


@admin.register(CssCategory)
class CssCategoryAdmin(admin.ModelAdmin):
    """Admin interface for CSS categories."""
    list_display = ('name', 'slug', 'css_count', 'created_at')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'created_at')
    ordering = ('name',)

    def css_count(self, obj):
        return obj.css_files.count()
    css_count.short_description = 'CSS Files'


@admin.register(Css)
class CssAdmin(admin.ModelAdmin):
    """Admin interface for CSS files."""
    list_display = ('name', 'author', 'creator', 'category', 'price', 'has_preview', 'purchase_count', 'created_at', 'updated_at')
    list_filter = ('created_at', 'price', 'creator', 'category')
    search_fields = ('name', 'author', 'creator__username', 'css_content')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    autocomplete_fields = ['creator', 'category']
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'author', 'description', 'category')
        }),
        ('Content', {
            'fields': ('css_content',),
            'classes': ('collapse',)
        }),
        ('Preview', {
            'fields': ('preview_gif',),
            'description': 'GIF preview image displayed in the shop instead of live CSS code.'
        }),
        ('Pricing & Ownership', {
            'fields': ('price', 'creator')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_preview(self, obj):
        """Show whether a GIF preview has been generated."""
        return bool(obj.preview_gif)
    has_preview.short_description = 'GIF Preview'
    has_preview.boolean = True

    def purchase_count(self, obj):
        return obj.purchases.count()
    purchase_count.short_description = 'Purchases'


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    """Admin interface for purchase records."""
    list_display = ('user', 'get_css_display', 'price_paid', 'purchased_at')
    list_filter = ('purchased_at',)
    search_fields = ('user__username', 'css_file__name', 'css_name')
    readonly_fields = ('id', 'purchased_at', 'css_name')
    ordering = ('-purchased_at',)
    autocomplete_fields = ['user', 'css_file']
    list_per_page = 50

    fieldsets = (
        ('Purchase Details', {
            'fields': ('id', 'user', 'css_file', 'css_name', 'price_paid')
        }),
        ('Timestamp', {
            'fields': ('purchased_at',)
        }),
    )

    def get_css_display(self, obj):
        """Display CSS file name or stored name if deleted."""
        if obj.css_file:
            return obj.css_file.name
        return f"{obj.css_name} (deleted)" if obj.css_name else "(deleted)"
    get_css_display.short_description = 'CSS File'


@admin.register(DownloadLog)
class DownloadLogAdmin(admin.ModelAdmin):
    """Admin interface for download logs (analytics)."""
    list_display = ('user', 'get_css_display', 'downloaded_at', 'ip_address')
    list_filter = ('downloaded_at',)
    search_fields = ('user__username', 'css_file__name', 'css_name')
    readonly_fields = ('id', 'downloaded_at', 'css_name')
    ordering = ('-downloaded_at',)
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    fieldsets = (
        ('Download Details', {
            'fields': ('id', 'user', 'css_file', 'css_name', 'downloaded_at', 'ip_address')
        }),
    )

    def get_css_display(self, obj):
        """Display CSS file name or stored name if deleted."""
        if obj.css_file:
            return obj.css_file.name
        return f"{obj.css_name} (deleted)" if obj.css_name else "(deleted)"
    get_css_display.short_description = 'CSS File'


class ApiKeyUsageInline(admin.TabularInline):
    model = ApiKeyUsage
    extra = 0
    readonly_fields = ('id', 'endpoint', 'method', 'status_code', 'ip_address', 'response_time_ms', 'timestamp')
    max_num = 20

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    """Admin interface for API keys."""
    list_display = ('name', 'user', 'key_prefix', 'is_active', 'last_used_at', 'expires_at', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'user__username', 'key_prefix')
    readonly_fields = ('id', 'key_hash', 'key_prefix', 'created_at', 'last_used_at')
    ordering = ('-created_at',)
    inlines = [ApiKeyUsageInline]


@admin.register(ApiKeyUsage)
class ApiKeyUsageAdmin(admin.ModelAdmin):
    """Admin interface for API key usage logs."""
    list_display = ('api_key', 'endpoint', 'method', 'status_code', 'ip_address', 'response_time_ms', 'timestamp')
    list_filter = ('method', 'status_code')
    search_fields = ('api_key__name', 'endpoint', 'ip_address')
    readonly_fields = ('id', 'timestamp')
