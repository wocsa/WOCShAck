"""
Developer module admin configuration.
"""
from django.contrib import admin

from .models import (
    DeveloperPlan, DeveloperProfile, DeveloperSubscription,
    CssProject, CssVersion, CssTemplate,
    CssListing, PricingTier, Promotion,
    SaleAnalytics, CustomerAnalytics,
    Webhook, WebhookDelivery,
    DeveloperBalance, PayoutMethod, Payout,
)


# =============================================================================
# SUBSCRIPTION & PROFILE
# =============================================================================

@admin.register(DeveloperPlan)
class DeveloperPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'price_monthly', 'price_yearly', 'css_limit', 'api_calls_limit', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'created_at')


@admin.register(DeveloperProfile)
class DeveloperProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'commission_rate', 'is_verified', 'created_at')
    list_filter = ('is_verified',)
    search_fields = ('user__username', 'display_name')
    readonly_fields = ('id', 'created_at', 'updated_at', 'verified_at')
    fieldsets = (
        ('User', {'fields': ('id', 'user', 'display_name', 'tagline')}),
        ('Links', {'fields': ('website', 'github_url', 'twitter_url')}),
        ('Settings', {'fields': ('specialties', 'commission_rate', 'payout_method')}),
        ('Verification', {'fields': ('is_verified', 'verified_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(DeveloperSubscription)
class DeveloperSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'auto_renew', 'current_period_start', 'current_period_end')
    list_filter = ('status', 'auto_renew', 'plan')
    search_fields = ('user__username', 'payment_tx_ref')
    readonly_fields = ('id', 'created_at', 'updated_at')


# =============================================================================
# CSS PROJECTS & EDITOR
# =============================================================================

class CssVersionInline(admin.TabularInline):
    model = CssVersion
    extra = 0
    readonly_fields = ('id', 'created_at')
    fields = ('version_number', 'commit_message', 'is_current', 'created_at')


@admin.register(CssProject)
class CssProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'developer', 'status', 'created_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('name', 'developer__username')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [CssVersionInline]


@admin.register(CssVersion)
class CssVersionAdmin(admin.ModelAdmin):
    list_display = ('project', 'version_number', 'is_current', 'created_at')
    list_filter = ('is_current',)
    search_fields = ('project__name', 'version_number', 'commit_message')
    readonly_fields = ('id', 'created_at')


@admin.register(CssTemplate)
class CssTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'order', 'created_at')
    list_filter = ('category',)
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'created_at')


# =============================================================================
# PUBLISHING & MARKETPLACE
# =============================================================================

class PricingTierInline(admin.TabularInline):
    model = PricingTier
    extra = 0


@admin.register(CssListing)
class CssListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'developer', 'status', 'visibility', 'license_type', 'published_at')
    list_filter = ('status', 'visibility', 'license_type')
    search_fields = ('title', 'developer__username', 'tags')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [PricingTierInline]
    fieldsets = (
        ('Content', {'fields': ('id', 'project', 'developer', 'title', 'description', 'documentation')}),
        ('Media', {'fields': ('thumbnail', 'preview_gif', 'demo_url')}),
        ('Settings', {'fields': ('license_type', 'tags', 'visibility', 'browser_support')}),
        ('Status', {'fields': ('status', 'rejection_reason', 'featured_until', 'published_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(PricingTier)
class PricingTierAdmin(admin.ModelAdmin):
    list_display = ('listing', 'name', 'price', 'scope', 'includes_source', 'includes_support')
    list_filter = ('scope', 'includes_source', 'includes_support')
    search_fields = ('listing__title', 'name')
    readonly_fields = ('id',)


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('code', 'listing', 'discount_percent', 'discount_amount', 'usage_count', 'usage_limit', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'listing__title')
    readonly_fields = ('id', 'usage_count', 'created_at')


# =============================================================================
# ANALYTICS
# =============================================================================

@admin.register(SaleAnalytics)
class SaleAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('developer', 'date', 'revenue', 'sales_count', 'unique_customers', 'page_views', 'conversion_rate')
    list_filter = ('date',)
    search_fields = ('developer__username',)
    readonly_fields = ('id',)


@admin.register(CustomerAnalytics)
class CustomerAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('developer', 'customer', 'purchase_count', 'lifetime_value', 'first_purchase', 'last_purchase')
    search_fields = ('developer__username', 'customer__username')
    readonly_fields = ('id',)


# =============================================================================
# WEBHOOKS
# =============================================================================

class WebhookDeliveryInline(admin.TabularInline):
    model = WebhookDelivery
    extra = 0
    readonly_fields = ('event_type', 'status_code', 'attempts', 'delivered_at', 'created_at')
    can_delete = False
    max_num = 0


@admin.register(Webhook)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ('url', 'developer', 'is_active', 'failure_count', 'last_triggered_at', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('url', 'developer__username')
    readonly_fields = ('id', 'created_at', 'last_triggered_at')
    inlines = [WebhookDeliveryInline]


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ('webhook', 'event_type', 'status_code', 'attempts', 'delivered_at', 'created_at')
    list_filter = ('event_type', 'status_code')
    search_fields = ('webhook__url', 'event_type')
    readonly_fields = ('id', 'created_at')


# =============================================================================
# PAYOUTS
# =============================================================================

@admin.register(DeveloperBalance)
class DeveloperBalanceAdmin(admin.ModelAdmin):
    list_display = ('developer', 'available', 'pending', 'total_earned', 'total_paid', 'updated_at')
    search_fields = ('developer__username',)
    readonly_fields = ('id', 'updated_at')


@admin.register(PayoutMethod)
class PayoutMethodAdmin(admin.ModelAdmin):
    list_display = ('developer', 'method_type', 'is_primary', 'is_verified', 'created_at')
    list_filter = ('method_type', 'is_primary', 'is_verified')
    search_fields = ('developer__username',)
    readonly_fields = ('id', 'created_at')


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ('developer', 'amount', 'fee', 'net_amount', 'status', 'requested_at', 'processed_at')
    list_filter = ('status',)
    search_fields = ('developer__username', 'tx_ref')
    readonly_fields = ('id', 'requested_at')
    fieldsets = (
        ('Payout Details', {'fields': ('id', 'developer', 'amount', 'fee', 'net_amount', 'method')}),
        ('Status', {'fields': ('status', 'tx_ref', 'admin_notes')}),
        ('Timestamps', {'fields': ('requested_at', 'processed_at')}),
    )
