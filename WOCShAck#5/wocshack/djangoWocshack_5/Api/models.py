"""
API module models for CSS marketplace.
All models follow secure coding practices with proper validation and UUIDs for non-sequential IDs.
"""
import uuid
import secrets
import hashlib
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils.text import slugify
from decimal import Decimal


class CssCategory(models.Model):
    """
    Category model for organizing CSS files.
    Uses UUID primary key and slugs for URL-safe identification.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'CSS Category'
        verbose_name_plural = 'CSS Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Css(models.Model):
    """
    CSS file model - core product for the marketplace.
    Uses UUID for non-sequential IDs to prevent enumeration attacks.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True, default='')
    css_content = models.TextField()
    author = models.CharField(max_length=150)
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='css_files'
    )
    price = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    category = models.ForeignKey(
        CssCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='css_files'
    )
    # This prevents CSS source code scraping from the shop frontend.
    # GIF previews are generated server-side via the generate_gif_previews management command.
    preview_gif = models.ImageField(
        upload_to='css_previews/',
        null=True,
        blank=True,
        help_text='Animated GIF preview of the CSS loader, generated server-side to prevent source code scraping.'
    )
    html_template = models.TextField(
        blank=True,
        default='<div class="loader"></div>',
        help_text="Custom HTML structure for rendering the preview"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'CSS File'
        verbose_name_plural = 'CSS Files'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['creator', '-created_at']),
            models.Index(fields=['category', '-created_at']),
            models.Index(fields=['price']),
        ]

    def __str__(self):
        return self.name


class Purchase(models.Model):
    """
    Purchase record model.
    Tracks who purchased what CSS file and at what price.
    Uses UUID for non-sequential IDs.
    Note: Uses SET_NULL to preserve purchase history even if CSS is deleted.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='css_purchases'
    )
    css_file = models.ForeignKey(
        Css,
        on_delete=models.SET_NULL,
        null=True,
        related_name='purchases'
    )
    # Store CSS name for audit trail even if CSS is deleted
    css_name = models.CharField(max_length=100, blank=True, default='')
    price_paid = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Purchase'
        verbose_name_plural = 'Purchases'
        unique_together = ('user', 'css_file')
        ordering = ['-purchased_at']
        indexes = [
            models.Index(fields=['user', '-purchased_at']),
            models.Index(fields=['css_file', '-purchased_at']),
        ]

    def __str__(self):
        return f"{self.user.username} purchased {self.css_file.name}"


class DownloadLog(models.Model):
    """
    Download tracking model for analytics.
    Logs each download of a CSS file for seller analytics.
    Note: Uses SET_NULL to preserve download history even if CSS is deleted.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='css_downloads'
    )
    css_file = models.ForeignKey(
        Css,
        on_delete=models.SET_NULL,
        null=True,
        related_name='download_logs'
    )
    # Store CSS name for audit trail even if CSS is deleted
    css_name = models.CharField(max_length=100, blank=True, default='')
    downloaded_at = models.DateTimeField(auto_now_add=True)
    # Note: IP is truncated/anonymized for privacy
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = 'Download Log'
        verbose_name_plural = 'Download Logs'
        ordering = ['-downloaded_at']
        indexes = [
            models.Index(fields=['user', '-downloaded_at']),
            models.Index(fields=['css_file', '-downloaded_at']),
        ]

    def __str__(self):
        return f"{self.user.username} downloaded {self.css_file.name}"


class ApiKey(models.Model):
    """
    API key model for programmatic access to the CSS API.
    Keys are stored as SHA256 hashes for security. Users can have multiple keys
    with configurable scopes, rate limits, and expiration.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='api_keys'
    )
    name = models.CharField(max_length=200, default='Default')
    key_hash = models.CharField(max_length=64, db_index=True, default='')
    key_prefix = models.CharField(max_length=8, default='')
    scopes = models.JSONField(default=list, blank=True)
    rate_limit_per_minute = models.IntegerField(default=60)
    rate_limit_per_day = models.IntegerField(default=5000)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'API Key'
        verbose_name_plural = 'API Keys'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.key_prefix}...)"

    @staticmethod
    def generate_key():
        return 'vrc_' + secrets.token_hex(32)

    @staticmethod
    def hash_key(raw_key):
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()


class ApiKeyUsage(models.Model):
    """Usage log for API key requests."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name='usage_logs')
    endpoint = models.CharField(max_length=500)
    method = models.CharField(max_length=10)
    status_code = models.IntegerField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    response_time_ms = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'API Key Usage'
        verbose_name_plural = 'API Key Usage'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.api_key.key_prefix}... - {self.endpoint} ({self.status_code})"
