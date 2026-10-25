"""
Admin configuration for Shopping module.
"""
from django.contrib import admin
from .models import Order, OrderItem, Cart, CartItem, Review, Wishlist, Coupon, CouponUsage


class OrderItemInline(admin.TabularInline):
    """Inline display of order items within an order"""
    model = OrderItem
    extra = 0
    readonly_fields = ('css_file', 'css_name', 'css_author', 'price_at_purchase', 'quantity')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin configuration for Order model"""
    list_display = ('id', 'user', 'status', 'total_amount', 'discount_amount', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'user__username', 'billing_email', 'coupon_code')
    readonly_fields = ('id', 'created_at', 'updated_at', 'completed_at')
    ordering = ('-created_at',)
    inlines = [OrderItemInline]

    fieldsets = (
        ('Order Info', {
            'fields': ('id', 'user', 'status')
        }),
        ('Amounts', {
            'fields': ('total_amount', 'discount_amount', 'coupon_code')
        }),
        ('Billing Details', {
            'fields': ('billing_first_name', 'billing_last_name', 'billing_email', 'billing_phone')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Admin configuration for OrderItem model"""
    list_display = ('css_name', 'order', 'quantity', 'price_at_purchase')
    list_filter = ('order__status',)
    search_fields = ('css_name', 'order__id')
    readonly_fields = ('id',)


class CartItemInline(admin.TabularInline):
    """Inline display of cart items within a cart"""
    model = CartItem
    extra = 0
    readonly_fields = ('added_at',)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Admin configuration for Cart model"""
    list_display = ('id', 'user', 'session_key', 'item_count', 'total', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__username', 'session_key')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [CartItemInline]

    def item_count(self, obj):
        return obj.get_item_count()
    item_count.short_description = 'Items'

    def total(self, obj):
        return f"{obj.get_total()} Neuros"
    total.short_description = 'Total'


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """Admin configuration for CartItem model"""
    list_display = ('css_file', 'cart', 'quantity', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('css_file__name', 'cart__user__username')
    readonly_fields = ('id', 'added_at')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Admin configuration for Review model"""
    list_display = ('css_file', 'user', 'rating', 'title', 'is_approved', 'is_verified_purchase', 'created_at')
    list_filter = ('rating', 'is_approved', 'is_verified_purchase', 'created_at')
    search_fields = ('css_file__name', 'user__username', 'title', 'content')
    readonly_fields = ('id', 'created_at', 'updated_at')
    list_editable = ('is_approved',)
    ordering = ('-created_at',)

    fieldsets = (
        ('Review Details', {
            'fields': ('css_file', 'user', 'rating', 'title', 'content')
        }),
        ('Moderation', {
            'fields': ('is_approved', 'is_verified_purchase')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    """Admin configuration for Wishlist model"""
    list_display = ('user', 'css_file', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('user__username', 'css_file__name')
    readonly_fields = ('id', 'added_at')
    ordering = ('-added_at',)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    """Admin configuration for Coupon model"""
    list_display = ('code', 'developer', 'discount_type', 'discount_value', 'current_uses', 'max_uses', 'is_active', 'valid_until')
    list_filter = ('discount_type', 'is_active', 'valid_from', 'valid_until')
    search_fields = ('code', 'description', 'developer__username')
    readonly_fields = ('id', 'current_uses', 'created_at')
    list_editable = ('is_active',)
    ordering = ('-created_at',)

    fieldsets = (
        ('Coupon Info', {
            'fields': ('code', 'description', 'developer')
        }),
        ('Discount', {
            'fields': ('discount_type', 'discount_value', 'minimum_order_amount')
        }),
        ('Usage Limits', {
            'fields': ('max_uses', 'current_uses', 'max_uses_per_user')
        }),
        ('Validity', {
            'fields': ('is_active', 'valid_from', 'valid_until')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    """Admin configuration for CouponUsage model"""
    list_display = ('coupon', 'user', 'order', 'used_at')
    list_filter = ('used_at',)
    search_fields = ('coupon__code', 'user__username')
    readonly_fields = ('id', 'used_at')
    ordering = ('-used_at',)
