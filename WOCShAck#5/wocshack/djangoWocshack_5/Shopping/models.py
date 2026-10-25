"""
Shopping module models for order management, cart persistence, reviews, and coupons.
All models follow secure coding practices with proper validation.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from Api.models import Css


class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'
    REFUNDED = 'refunded', 'Refunded'


class Order(models.Model):
    """
    Order model for tracking customer purchases.
    Uses UUID for non-sequential IDs to prevent enumeration attacks.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='shopping_orders'
    )
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    coupon_code = models.CharField(max_length=50, blank=True, null=True)

    # Customer details at time of order (stored for record keeping)
    billing_first_name = models.CharField(max_length=100)
    billing_last_name = models.CharField(max_length=100)
    billing_email = models.EmailField()
    billing_phone = models.CharField(max_length=20, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Order {self.id} - {self.user.username} - {self.status}"

    def get_final_total(self):
        """Calculate final total after discount"""
        return self.total_amount - self.discount_amount

    def mark_completed(self):
        """Mark order as completed with timestamp"""
        self.status = OrderStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save()


class OrderItem(models.Model):
    """
    Individual items within an order.
    Stores price at time of purchase to maintain historical accuracy.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    css_file = models.ForeignKey(
        Css,
        on_delete=models.SET_NULL,
        null=True,
        related_name='order_items'
    )
    # This prevents issues if the CSS file is deleted or modified
    css_name = models.CharField(max_length=100)
    css_author = models.CharField(max_length=150)
    price_at_purchase = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )

    class Meta:
        ordering = ['order', 'css_name']

    def __str__(self):
        return f"{self.css_name} x{self.quantity} in Order {self.order_id}"

    def get_total(self):
        """Calculate line item total"""
        return self.price_at_purchase * self.quantity


class Cart(models.Model):
    """
    Persistent shopping cart model.
    Each user has one cart; anonymous users use session-based cart.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='shopping_cart',
        null=True,
        blank=True
    )
    # For anonymous users, store session key
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, session_key__isnull=True) |
                    models.Q(user__isnull=True, session_key__isnull=False)
                ),
                name='cart_user_or_session'
            )
        ]

    def __str__(self):
        if self.user:
            return f"Cart for {self.user.username}"
        return f"Cart (Session: {self.session_key[:8]}...)"

    def get_total(self):
        """Calculate cart total from current CSS prices"""
        total = Decimal('0.00')
        for item in self.cart_items.select_related('css_file'):
            if item.css_file:
                total += item.css_file.price * item.quantity
        return total

    def get_item_count(self):
        """Get total number of items in cart"""
        return sum(item.quantity for item in self.cart_items.all())

    def clear(self):
        """Remove all items from cart"""
        self.cart_items.all().delete()

    @classmethod
    def get_or_create_for_request(cls, request):
        """
        Get or create cart for the current request.
        Handles both authenticated and anonymous users securely.
        """
        if request.user.is_authenticated:
            cart, created = cls.objects.get_or_create(user=request.user)
            return cart
        else:
            # For anonymous users, use session
            if not request.session.session_key:
                request.session.create()
            session_key = request.session.session_key
            cart, created = cls.objects.get_or_create(session_key=session_key)
            return cart


class CartItem(models.Model):
    """
    Individual items in a shopping cart.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    css_file = models.ForeignKey(
        Css,
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('cart', 'css_file')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.css_file.name} x{self.quantity}"

    def get_total(self):
        """Calculate item total at current price"""
        return self.css_file.price * self.quantity


class Review(models.Model):
    """
    Product reviews with moderation support.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    css_file = models.ForeignKey(
        Css,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='css_reviews'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=200)
    content = models.TextField(max_length=5000)

    # Moderation fields
    is_approved = models.BooleanField(default=True)  # Auto-approve by default
    is_verified_purchase = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('css_file', 'user')  # One review per user per product
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['css_file', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"Review by {self.user.username} for {self.css_file.name}"


class Wishlist(models.Model):
    """
    User wishlist for saving items for later.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='wishlist_items'
    )
    css_file = models.ForeignKey(
        Css,
        on_delete=models.CASCADE,
        related_name='wishlisted_by'
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'css_file')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.user.username} - {self.css_file.name}"


class Coupon(models.Model):
    """
    Discount coupon system with validation.
    """
    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage'
        FIXED = 'fixed', 'Fixed Amount'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.CharField(max_length=200, blank=True)

    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    # For percentage discounts, max is 100%
    # For fixed discounts, this is the amount off

    # Usage limits
    max_uses = models.PositiveIntegerField(default=0)  # 0 = unlimited
    current_uses = models.PositiveIntegerField(default=0)
    max_uses_per_user = models.PositiveIntegerField(default=1)

    minimum_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    # Validity period
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    developer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='developer_coupons',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} - {self.discount_value}{'%' if self.discount_type == self.DiscountType.PERCENTAGE else ' Neuros'}"

    def is_valid(self, order_total=None, user=None):
        """
        Validate coupon with comprehensive checks.
        """
        now = timezone.now()

        # Check if active
        if not self.is_active:
            return False, "This coupon is no longer active."

        # Check validity period
        if now < self.valid_from:
            return False, "This coupon is not yet valid."

        if self.valid_until and now > self.valid_until:
            return False, "This coupon has expired."

        # Check max uses
        if self.max_uses > 0 and self.current_uses >= self.max_uses:
            return False, "This coupon has reached its usage limit."

        # Check minimum order amount
        if order_total is not None and order_total < self.minimum_order_amount:
            return False, f"Minimum order amount of {self.minimum_order_amount} Neuros required."

        # Check per-user limit
        if user and self.max_uses_per_user > 0:
            user_uses = CouponUsage.objects.filter(coupon=self, user=user).count()
            if user_uses >= self.max_uses_per_user:
                return False, "You have already used this coupon the maximum number of times."

        return True, "Coupon is valid."

    def calculate_discount(self, order_total):
        """
        Calculate discount amount with bounds checking.
        """
        if self.discount_type == self.DiscountType.PERCENTAGE:
            # Cap percentage at 100%
            percentage = min(self.discount_value, Decimal('100'))
            discount = (order_total * percentage) / 100
        else:
            # Fixed discount cannot exceed order total
            discount = min(self.discount_value, order_total)

        return discount.quantize(Decimal('0.01'))

    def get_applicable_total(self, cart_items):
        """Return cart subtotal this coupon applies to.
        If developer-scoped, only sums items created by that developer.
        """
        if self.developer_id is None:
            return sum(
                (item.css_file.price * item.quantity for item in cart_items if item.css_file),
                Decimal('0.00')
            )
        return sum(
            (item.css_file.price * item.quantity
             for item in cart_items
             if item.css_file and item.css_file.creator_id == self.developer_id),
            Decimal('0.00')
        )


class CouponUsage(models.Model):
    """
    Track coupon usage per user for limit enforcement.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.CASCADE,
        related_name='usage_records'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='coupon_usage'
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        related_name='coupon_usage'
    )
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-used_at']
        indexes = [
            models.Index(fields=['coupon', 'user']),
        ]

    def __str__(self):
        return f"{self.user.username} used {self.coupon.code}"
