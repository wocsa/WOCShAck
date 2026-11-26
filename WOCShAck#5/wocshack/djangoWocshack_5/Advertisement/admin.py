"""
Advertisement module admin configuration.
"""
from django.contrib import admin
from django.utils import timezone

from .models import Advertisement, AdImpression, AdClick, AdvertisementImage


class AdImpressionInline(admin.TabularInline):
    model = AdImpression
    extra = 0
    readonly_fields = ('user', 'ip_address', 'zone', 'timestamp')
    can_delete = False
    max_num = 0
    show_change_link = False


class AdClickInline(admin.TabularInline):
    model = AdClick
    extra = 0
    readonly_fields = ('user', 'ip_address', 'timestamp')
    can_delete = False
    max_num = 0
    show_change_link = False


class AdvertisementImageInline(admin.TabularInline):
    model = AdvertisementImage
    extra = 1
    fields = ('image', 'order', 'alt_text')


@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'advertiser', 'placement_zone', 'status',
        'start_date', 'end_date', 'cost_neuros', 'impression_count', 'click_count',
    )
    list_filter = ('status', 'placement_zone', 'start_date')
    list_editable = ('status',)
    search_fields = ('title', 'body', 'advertiser__username')
    readonly_fields = (
        'id', 'body_html', 'created_at', 'updated_at', 'reviewed_by', 'reviewed_at',
        'impression_count', 'click_count',
    )
    fieldsets = (
        ('Ad Content', {
            'fields': ('title', 'body', 'body_html', 'image_url', 'target_url'),
        }),
        ('Placement & Schedule', {
            'fields': ('placement_zone', 'start_date', 'end_date'),
        }),
        ('Budget & Billing', {
            'fields': ('budget_neuros', 'spent_neuros', 'cost_neuros', 'payment_tx_ref'),
        }),
        ('Workflow', {
            'fields': ('status', 'advertiser', 'reviewed_by', 'reviewed_at', 'rejection_reason'),
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'impression_count', 'click_count'),
            'classes': ('collapse',),
        }),
    )
    inlines = [AdvertisementImageInline, AdImpressionInline, AdClickInline]

    def impression_count(self, obj):
        return obj.impressions.count()
    impression_count.short_description = 'Impressions'

    def click_count(self, obj):
        return obj.clicks.count()
    click_count.short_description = 'Clicks'

    def save_model(self, request, obj, form, change):
        if 'status' in form.changed_data and obj.status in (
            Advertisement.Status.APPROVED,
            Advertisement.Status.REJECTED,
            Advertisement.Status.ACTIVE,
        ):
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(AdImpression)
class AdImpressionAdmin(admin.ModelAdmin):
    list_display = ('advertisement', 'user', 'ip_address', 'zone', 'timestamp')
    list_filter = ('timestamp', 'zone')
    search_fields = ('advertisement__title', 'user__username', 'ip_address')
    readonly_fields = ('id', 'advertisement', 'user', 'ip_address', 'zone', 'timestamp')


@admin.register(AdClick)
class AdClickAdmin(admin.ModelAdmin):
    list_display = ('advertisement', 'user', 'ip_address', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('advertisement__title', 'user__username', 'ip_address')
    readonly_fields = ('id', 'advertisement', 'user', 'ip_address', 'timestamp')


@admin.register(AdvertisementImage)
class AdvertisementImageAdmin(admin.ModelAdmin):
    list_display = ('advertisement', 'order', 'alt_text', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('advertisement__title', 'alt_text')
    readonly_fields = ('id', 'uploaded_at')
