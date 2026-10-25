"""
Advertisement module models for the V.R.C ad platform.

All models follow secure coding practices with UUID PKs,
TextChoices for status fields, and proper FK relationships.
"""
import uuid
import random
import os
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# ---------------------------------------------------------------------------
# Rate table: Neuros per day per placement zone
# ---------------------------------------------------------------------------
ZONE_RATE_PER_DAY = {
    'shop_sidebar': 10,
    'forum_banner': 15,
    'homepage_banner': 20,
    'all': 40,
}


def advertisement_image_upload_path(instance, filename):
    """ Store uploaded images under media/advertisement_images/<ad_id>/"""
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    return os.path.join('advertisement_images', str(instance.advertisement_id), safe_name)


class Advertisement(models.Model):
    """
    Core advertisement model.
    Tracks ad content, budget, placement zone, and approval workflow.
    """

    class PlacementZone(models.TextChoices):
        SHOP_SIDEBAR = 'shop_sidebar', 'Shop Sidebar'
        FORUM_BANNER = 'forum_banner', 'Forum Banner'
        HOMEPAGE_BANNER = 'homepage_banner', 'Homepage Banner'
        ALL = 'all', 'All Zones'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)

    # the sanitized rendered HTML (cached). Rendering happens in save().
    body = models.TextField(
        max_length=2000,
        help_text='Supports markdown formatting (bold, italic, lists, links). Max 2000 characters.'
    )
    body_html = models.TextField(
        blank=True,
        editable=False,
        help_text='Auto-generated sanitized HTML from body markdown. Do not edit directly.'
    )

    image_url = models.URLField(
        max_length=500,
        blank=True,
        help_text='Optional primary image URL for the ad banner.'
    )
    target_url = models.URLField(
        max_length=500,
        help_text='URL to redirect users to when they click the ad.'
    )
    advertiser = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='advertisements'
    )

    # Budget tracking (in Neuros)
    budget_neuros = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Total budget allocated for this ad in Neuros.'
    )
    spent_neuros = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Amount spent so far in Neuros.'
    )

    # Billing fields (set on activation)
    cost_neuros = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Computed campaign cost in Neuros (rate_per_day × days). Set on activation.'
    )
    payment_tx_ref = models.CharField(
        max_length=100,
        blank=True,
        help_text='VRC Banking transaction reference for the ad payment.'
    )

    placement_zone = models.CharField(
        max_length=30,
        choices=PlacementZone.choices,
        default=PlacementZone.SHOP_SIDEBAR,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Required for billing. Leave blank for no expiry (billing will not apply).'
    )

    # Review workflow
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ads_reviewed'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(
        max_length=1000,
        blank=True,
        help_text='Reason for rejection (staff only).'
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Advertisement'
        verbose_name_plural = 'Advertisements'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['advertiser', '-created_at']),
            models.Index(fields=['placement_zone', 'status']),
            models.Index(fields=['status', 'start_date', 'end_date']),
        ]

    def __str__(self):
        return f'{self.title} ({self.get_status_display()}) — {self.advertiser.username}'

    # ------------------------------------------------------------------
    # Markdown rendering
    # ------------------------------------------------------------------

    def _render_body_html(self):
        """
        Render self.body markdown to sanitized HTML using the same
        renderer as the Forum module (Forum.Utils.markdown_utils.render_markdown).
        """
        from Forum.Utils.markdown_utils import render_markdown
        return str(render_markdown(self.body))

    def save(self, *args, **kwargs):
        # Regenerate cached HTML whenever body changes
        self.body_html = self._render_body_html()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Billing helpers
    # ------------------------------------------------------------------

    def compute_cost(self):
        """
        Calculate campaign cost in Neuros.
        Returns (cost: Decimal, days: int) or (None, None) if end_date is unset.
        """
        if not self.end_date:
            return None, None
        import decimal
        rate = ZONE_RATE_PER_DAY.get(self.placement_zone, 10)
        start = self.start_date if self.start_date else timezone.now()
        delta = self.end_date - start
        days = max(delta.days, 1)  # Minimum 1 day
        cost = decimal.Decimal(rate) * decimal.Decimal(days)
        return cost, days

    # ------------------------------------------------------------------
    # Serving helpers
    # ------------------------------------------------------------------

    def is_currently_active(self):
        """Check if the ad should be served right now."""
        if self.status != self.Status.ACTIVE:
            return False
        now = timezone.now()
        if now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True

    @classmethod
    def get_all_active_for_zone(cls, zone):
        """
        Return all active ads for the given placement zone (including 'all' zone ads).
        Used to feed multi-ad carousels.
        """
        now = timezone.now()
        return list(
            cls.objects.filter(
                models.Q(placement_zone=zone) | models.Q(placement_zone=cls.PlacementZone.ALL),
                status=cls.Status.ACTIVE,
                start_date__lte=now,
            ).filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gt=now)
            ).prefetch_related('images')
        )

    @classmethod
    def get_active_for_zone(cls, zone):
        """Return one random active ad for the zone, or None."""
        ads = cls.get_all_active_for_zone(zone)
        return random.choice(ads) if ads else None

    @classmethod
    def get_all_active(cls):
        """Return all currently active ads regardless of placement zone."""
        now = timezone.now()
        return list(
            cls.objects.filter(
                status=cls.Status.ACTIVE,
                start_date__lte=now,
            ).filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gt=now)
            ).prefetch_related('images')
        )


class AdImpression(models.Model):
    """
    Tracks each time an ad is displayed to a visitor.
    Includes the zone slug so impressions for "All Zones" ads remain accurate
    per-zone.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    advertisement = models.ForeignKey(
        Advertisement,
        on_delete=models.CASCADE,
        related_name='impressions'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ad_impressions'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    # zone slug (e.g. 'shop_sidebar') of where this impression was rendered
    zone = models.CharField(max_length=30, blank=True, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Ad Impression'
        verbose_name_plural = 'Ad Impressions'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['advertisement', '-timestamp']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else 'anonymous'
        return f'Impression on "{self.advertisement.title}" by {user_str}'


class AdClick(models.Model):
    """
    Tracks each click on an ad.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    advertisement = models.ForeignKey(
        Advertisement,
        on_delete=models.CASCADE,
        related_name='clicks'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ad_clicks'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Ad Click'
        verbose_name_plural = 'Ad Clicks'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['advertisement', '-timestamp']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else 'anonymous'
        return f'Click on "{self.advertisement.title}" by {user_str}'


class AdvertisementImage(models.Model):
    """
    Additional images for carousel display on an advertisement.
    Images are stored under media/advertisement_images/<ad_id>/.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    advertisement = models.ForeignKey(
        Advertisement,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(
        upload_to=advertisement_image_upload_path,
        help_text='JPG, PNG or GIF. Max 5 MB.'
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text='Display order (lower numbers appear first).'
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        help_text='Accessible alt text for this image.'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Advertisement Image'
        verbose_name_plural = 'Advertisement Images'
        ordering = ['order', 'uploaded_at']

    def __str__(self):
        return f'Image #{self.order} for "{self.advertisement.title}"'
