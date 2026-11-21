"""
Developer module models.
Provides CSS creators a complete platform to build, publish, and monetize CSS files.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# =============================================================================
# SUBSCRIPTION & PROFILE
# =============================================================================

class DeveloperPlan(models.Model):
    """Subscription tiers for the developer platform."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2)
    css_limit = models.IntegerField(help_text="Max CSS projects. 0 = unlimited.")
    api_calls_limit = models.IntegerField(help_text="Max API calls per month. 0 = unlimited.")
    commission_rate = models.DecimalField(
        max_digits=4, decimal_places=2,
        default=Decimal('0.70'),
        help_text="Fraction of sale revenue paid to developer (e.g. 0.70 = 70%)."
    )
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['price_monthly']

    def __str__(self):
        return self.name

    @classmethod
    def get_free_plan(cls):
        """Return the active free-tier plan. Prefers slug='free'; falls back to price=0."""
        return (
            cls.objects.filter(slug='free', is_active=True).first()
            or cls.objects.filter(price_monthly=Decimal('0.00'), is_active=True).order_by('created_at').first()
        )


class DeveloperProfile(models.Model):
    """Extended profile for developers."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='developer_profile')
    display_name = models.CharField(max_length=150, blank=True)
    tagline = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    specialties = models.JSONField(default=list, blank=True)
    commission_rate = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('0.70'))
    payout_method = models.CharField(max_length=50, blank=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name or self.user.username


class DeveloperSubscription(models.Model):
    """Tracks developer plan subscriptions."""
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'
        TRIAL = 'trial', 'Trial'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='developer_subscriptions')
    plan = models.ForeignKey(DeveloperPlan, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    auto_renew = models.BooleanField(default=True)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True)
    payment_tx_ref = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.plan.name} ({self.status})"

    @property
    def is_active_subscription(self):
        return self.status in (self.Status.ACTIVE, self.Status.TRIAL)

    def _downgrade_to_free(self):
        """Cancel this subscription and move the user to the free plan."""
        self.status = self.Status.CANCELLED
        self.save(update_fields=['status'])
        free_plan = DeveloperPlan.get_free_plan()
        if not free_plan:
            return
        DeveloperSubscription.objects.create(
            user=self.user,
            plan=free_plan,
            status=self.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
        )
        try:
            profile = self.user.developer_profile
            if profile.commission_rate != free_plan.commission_rate:
                profile.commission_rate = free_plan.commission_rate
                profile.save(update_fields=['commission_rate'])
        except Exception:
            pass

    def attempt_renewal(self):
        """
        Attempts to renew this subscription by charging the user's bank account.
        Returns a tuple (success: bool, error_message: str).
        On payment failure the user is downgraded to the free plan.
        """
        from django.contrib.auth.models import User as DjangoUser
        from Bank.Utils import client as bank_client
        from Bank.models import Transaction as BankTransaction
        import time

        if self.status != self.Status.ACTIVE:
            return False, "Subscription is not active."

        if not self.auto_renew:
            self.status = self.Status.EXPIRED
            self.save(update_fields=['status'])
            return False, "Auto-renew is disabled."

        if self.plan.price_monthly == Decimal('0.00'):
            self.current_period_end = self.current_period_end + timezone.timedelta(days=30)
            self.save(update_fields=['current_period_end'])
            return True, ""

        admin_user = DjangoUser.objects.filter(is_superuser=True).first()
        admin_bank_id = admin_user.id if admin_user else 1

        cli, sid = bank_client.make_connection()
        if not cli or not sid:
            self._downgrade_to_free()
            return False, "Bank system unavailable."

        success = False
        error_msg = ""
        tx_ref = ""
        try:
            user_response = cli.get_user(sid, self.user.id)
            time.sleep(0.3)
            if isinstance(user_response, dict) and user_response.get('success'):
                user_data = user_response.get('user', {})
                balance = Decimal(str(user_data.get('balance', 0)))
                bank_user_id = user_data.get('id')

                if self.plan.price_monthly > balance:
                    error_msg = f"Insufficient funds. Balance: {balance} NE, required: {self.plan.price_monthly} NE."
                else:
                    result = cli.transaction(
                        sid=sid,
                        from_user=bank_user_id,
                        to_user=admin_bank_id,
                        amount=float(self.plan.price_monthly),
                    )
                    time.sleep(0.3)
                    if result and result.get('status') == 'success':
                        tx_ref = result.get('tx_id', '') or result.get('transaction_id', '')
                        success = True
                    else:
                        error_msg = result.get('message', 'Transaction failed.') if result else 'No response from bank.'
            else:
                error_msg = "Could not retrieve bank account."
        except Exception as e:
            error_msg = f"Payment error: {str(e)}"
        finally:
            if cli and sid:
                cli.close_session(sid)
            if cli:
                cli.close()

        if success:
            self.current_period_end = self.current_period_end + timezone.timedelta(days=30)
            self.payment_tx_ref = tx_ref
            self.save(update_fields=['current_period_end', 'payment_tx_ref'])

            BankTransaction.objects.create(
                user=self.user,
                transaction_type='payment',
                amount=self.plan.price_monthly,
                counterpart_label=f'Developer subscription renewal — {self.plan.name}',
                status='completed',
            )
            return True, ""
        else:
            self._downgrade_to_free()
            return False, error_msg


# =============================================================================
# CSS PROJECTS & EDITOR
# =============================================================================

class CssProject(models.Model):
    """A CSS project created by a developer."""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='css_projects')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.name

    @property
    def current_version(self):
        return self.versions.filter(is_current=True).first()


class CssVersion(models.Model):
    """Version history for a CSS project."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(CssProject, on_delete=models.CASCADE, related_name='versions')
    version_number = models.CharField(max_length=20)
    css_content = models.TextField(blank=True)
    html_template = models.TextField(blank=True)
    commit_message = models.CharField(max_length=500, blank=True)
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project.name} v{self.version_number}"


class CssTemplate(models.Model):
    """Starter templates for new CSS projects."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    css_content = models.TextField(blank=True)
    html_template = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to='developer/templates/', blank=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


# =============================================================================
# PUBLISHING & MARKETPLACE
# =============================================================================

class CssListing(models.Model):
    """A published CSS project available in the marketplace."""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        REVIEW = 'review', 'In Review'
        PENDING = 'pending', 'Pending'
        PUBLISHED = 'published', 'Published'
        REJECTED = 'rejected', 'Rejected'
        ARCHIVED = 'archived', 'Archived'

    class Visibility(models.TextChoices):
        PUBLIC = 'public', 'Public'
        UNLISTED = 'unlisted', 'Unlisted'
        PRIVATE = 'private', 'Private'

    class LicenseType(models.TextChoices):
        PERSONAL = 'personal', 'Personal'
        COMMERCIAL = 'commercial', 'Commercial'
        EXTENDED = 'extended', 'Extended'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(CssProject, on_delete=models.CASCADE, related_name='listings')
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='css_listings')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to='developer/listings/thumbnails/', blank=True)
    preview_gif = models.ImageField(upload_to='developer/listings/previews/', blank=True)
    demo_url = models.URLField(blank=True)
    documentation = models.TextField(blank=True)
    browser_support = models.JSONField(default=dict, blank=True)
    license_type = models.CharField(max_length=20, choices=LicenseType.choices, default=LicenseType.PERSONAL)
    tags = models.CharField(max_length=500, blank=True)
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PUBLISHED)
    rejection_reason = models.TextField(blank=True)
    featured_until = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title


class PricingTier(models.Model):
    """Pricing options for a CSS listing."""
    class Scope(models.TextChoices):
        PERSONAL = 'personal', 'Personal'
        COMMERCIAL = 'commercial', 'Commercial'
        EXTENDED = 'extended', 'Extended'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(CssListing, on_delete=models.CASCADE, related_name='pricing_tiers')
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.PERSONAL)
    includes_source = models.BooleanField(default=False)
    includes_support = models.BooleanField(default=False)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f"{self.listing.title} - {self.name} ({self.price} NE)"


class Promotion(models.Model):
    """Discount codes for CSS listings."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(CssListing, on_delete=models.CASCADE, related_name='promotions', null=True, blank=True)
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    usage_limit = models.IntegerField(default=0, help_text="0 = unlimited")
    usage_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.start_date or now > self.end_date:
            return False
        if self.usage_limit > 0 and self.usage_count >= self.usage_limit:
            return False
        return True


# =============================================================================
# ANALYTICS
# =============================================================================

class SaleAnalytics(models.Model):
    """Daily sales analytics aggregated per developer."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sale_analytics')
    date = models.DateField()
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sales_count = models.IntegerField(default=0)
    unique_customers = models.IntegerField(default=0)
    page_views = models.IntegerField(default=0)
    cart_additions = models.IntegerField(default=0)
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    avg_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        unique_together = ('developer', 'date')
        ordering = ['-date']
        verbose_name_plural = 'Sale analytics'

    def __str__(self):
        return f"{self.developer.username} - {self.date}"


class CustomerAnalytics(models.Model):
    """Per-customer analytics for a developer."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_analytics')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='developer_customer_records')
    purchase_count = models.IntegerField(default=0)
    lifetime_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    first_purchase = models.DateTimeField(null=True, blank=True)
    last_purchase = models.DateTimeField(null=True, blank=True)
    favorite_category = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ('developer', 'customer')
        verbose_name_plural = 'Customer analytics'

    def __str__(self):
        return f"{self.developer.username} -> {self.customer.username}"


# =============================================================================
# WEBHOOKS
# =============================================================================

class Webhook(models.Model):
    """Webhook endpoints for developer notifications."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='developer_webhooks')
    url = models.URLField()
    secret = models.CharField(max_length=255)
    events = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    failure_count = models.IntegerField(default=0)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.url} ({'active' if self.is_active else 'inactive'})"


class WebhookDelivery(models.Model):
    """Log of webhook delivery attempts."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name='deliveries')
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    attempts = models.IntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Webhook deliveries'

    def __str__(self):
        return f"{self.webhook.url} - {self.event_type}"


# =============================================================================
# PAYOUTS
# =============================================================================

class DeveloperBalance(models.Model):
    """Developer earnings balance."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    developer = models.OneToOneField(User, on_delete=models.CASCADE, related_name='developer_balance')
    available = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    pending = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_earned = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Developer balances'

    def __str__(self):
        return f"{self.developer.username} - {self.available} NE available"


class PayoutMethod(models.Model):
    """Payout method configuration."""
    class MethodType(models.TextChoices):
        PAYPAL = 'paypal', 'PayPal'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        STRIPE = 'stripe', 'Stripe'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payout_methods')
    method_type = models.CharField(max_length=20, choices=MethodType.choices)
    details_text = models.TextField(blank=True, help_text="Payout method details (e.g. email, account number).")
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', '-created_at']

    def __str__(self):
        return f"{self.developer.username} - {self.get_method_type_display()}"


class Payout(models.Model):
    """Payout request records."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='developer_payouts')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.ForeignKey(PayoutMethod, on_delete=models.SET_NULL, null=True, related_name='payouts')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    tx_ref = models.CharField(max_length=255, blank=True)
    admin_notes = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.developer.username} - {self.amount} NE ({self.status})"
