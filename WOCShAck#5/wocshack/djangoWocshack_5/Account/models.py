"""
Account module models.
This module contains models for user profiles, login history, 2FA backup codes, and session management.
"""
import secrets
import hashlib
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone


class UserProfile(models.Model):
    """
    Extended user profile with additional fields.
    Links to Django's built-in User model via OneToOneField.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bid = models.IntegerField(
        validators=[MinValueValidator(1000000000), MaxValueValidator(9999999999)],
        blank=True, null=True, unique=True
    )
    totp_key = models.CharField(max_length=32, blank=True, null=True)
    email_2fa_enabled = models.BooleanField(default=False)
    cart = models.TextField(null=True)
    biography = models.TextField(blank=True)
    picture_path = models.CharField(max_length=255, blank=True, default='default.png')
    is_activated = models.BooleanField(default=False)
    has_claimed_bonus = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile for {self.user.username}"

    def get_profile_completion(self):
        """
        Calculate profile completion percentage.
        Returns a dict with percentage and missing fields.
        """
        fields = {
            'email': bool(self.user.email),
            'first_name': bool(self.user.first_name),
            'last_name': bool(self.user.last_name),
            'biography': bool(self.biography),
            'picture': self.picture_path != 'default.png',
            'activated': self.is_activated,
            '2fa_enabled': bool(self.totp_key),
        }
        completed = sum(1 for v in fields.values() if v)
        total = len(fields)
        missing = [k for k, v in fields.items() if not v]
        return {
            'percentage': int((completed / total) * 100),
            'completed': completed,
            'total': total,
            'missing': missing
        }

    def get_user_role(self):
        """
        Get the user's primary role.
        Returns role name and badge color for display.
        """
        if self.user.is_superuser:
            return {'name': 'Admin', 'color': '#dc2626', 'icon': 'shield-check'}  # Red
        elif self.user.is_staff:
            return {'name': 'Staff', 'color': '#ea580c', 'icon': 'shield-exclamation'}  # Orange
        else:
            return {'name': 'User', 'color': '#0891b2', 'icon': 'user'}  # Cyan

    def get_forum_badge(self):
        """
        Get forum activity badge based on reputation.
        Returns None if user has no forum activity, otherwise returns badge info.
        """
        try:
            # Import here to avoid circular import
            from Forum.models import UserReputation
            reputation = UserReputation.objects.get(user=self.user)
            rank = reputation.get_rank()

            # Map ranks to colors
            badge_colors = {
                'Expert': '#7c3aed',      # Purple
                'Advanced': '#2563eb',    # Blue
                'Member': '#059669',      # Green
                'Newcomer': '#0891b2',    # Cyan
                'New User': '#64748b',    # Slate
            }

            return {
                'name': rank,
                'color': badge_colors.get(rank, '#64748b'),
                'points': reputation.reputation_points,
                'icon': 'star'
            }
        except:
            return None

    def get_seller_badge(self):
        """
        Get seller verification badge based on sales volume.
        Returns None if user is not a seller, otherwise returns badge info.
        """
        try:
            # Import here to avoid circular import
            from Api.models import Css
            from Shopping.models import Review
            from django.db.models import Avg, Count

            # Check if user has CSS files
            css_count = Css.objects.filter(creator=self.user).count()

            if css_count == 0:
                return None

            # Get review statistics
            review_stats = Review.objects.filter(
                css_file__creator=self.user,
                is_approved=True
            ).aggregate(
                avg_rating=Avg('rating'),
                total_reviews=Count('id')
            )

            avg_rating = review_stats['avg_rating'] or 0
            total_reviews = review_stats['total_reviews'] or 0

            # Determine badge level based on criteria
            if css_count >= 10 and avg_rating >= 4.5 and total_reviews >= 20:
                return {
                    'name': 'Top Seller',
                    'color': '#f59e0b',  # Amber
                    'icon': 'sparkles',
                    'css_count': css_count,
                    'avg_rating': avg_rating
                }
            elif css_count >= 5 and total_reviews >= 10:
                return {
                    'name': 'Verified Seller',
                    'color': '#8b5cf6',  # Violet
                    'icon': 'check-badge',
                    'css_count': css_count,
                    'avg_rating': avg_rating
                }
            else:
                return {
                    'name': 'Seller',
                    'color': '#667eea',  # Indigo
                    'icon': 'shopping-bag',
                    'css_count': css_count,
                    'avg_rating': avg_rating
                }
        except:
            return None

    def get_all_badges(self):
        """
        Get all badges for this user.
        Returns a list of badge dictionaries for display on profile.
        Includes both earned badges and purchased premium badges.
        """
        badges = []

        # Always show role badge
        if self.user.is_superuser or self.user.is_staff:
            role_badge = self.get_user_role()
            badges.append(role_badge)
        elif PurchasedFeature.has_feature(self.user, PurchasedFeature.FEATURE_DEVELOPER_ROLE):
            badges.append({
                'name': 'Developer',
                'color': '#8b5cf6',  # Violet
                'icon': 'code-bracket'
            })
        else:
            role_badge = self.get_user_role()
            badges.append(role_badge)

        # Purchased Verified badge
        if PurchasedFeature.has_feature(self.user, PurchasedFeature.FEATURE_VERIFIED_BADGE):
            badges.append({
                'name': 'Verified',
                'color': '#3b82f6',  # Blue
                'icon': 'check-badge'
            })

        # Email verification badge
        if self.is_activated:
            badges.append({
                'name': 'Email Verified',
                'color': '#10b981',  # Green
                'icon': 'envelope-open'
            })

        # Forum activity badge
        forum_badge = self.get_forum_badge()
        if forum_badge:
            badges.append(forum_badge)

        # Seller badge
        seller_badge = self.get_seller_badge()
        if seller_badge:
            badges.append(seller_badge)

        return badges


class LoginHistory(models.Model):
    """
    Track login attempts for security monitoring.
    Stores IP address, user agent, and login status for audit purposes.
    """
    LOGIN_SUCCESS = 'success'
    LOGIN_FAILED = 'failed'
    LOGIN_2FA_REQUIRED = '2fa_required'
    LOGIN_LOCKED = 'locked'
    LOGIN_STATUS_CHOICES = [
        (LOGIN_SUCCESS, 'Success'),
        (LOGIN_FAILED, 'Failed'),
        (LOGIN_2FA_REQUIRED, '2FA Required'),
        (LOGIN_LOCKED, 'Account Locked'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_history')
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=LOGIN_STATUS_CHOICES, default=LOGIN_SUCCESS)
    location = models.CharField(max_length=255, blank=True)  # Optional: city/country from IP
    device_type = models.CharField(max_length=50, blank=True)  # mobile, desktop, tablet

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Login histories'

    def __str__(self):
        return f"{self.user.username} - {self.status} at {self.timestamp}"

    @classmethod
    def log_attempt(cls, user, request, status):
        """
        Log a login attempt with request details.
        Extracts IP and user agent from the request object securely.
        """
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
        if ip_address:
            # Take the first IP in case of proxied requests
            ip_address = ip_address.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]  # Limit length

        # Determine device type from user agent
        device_type = 'unknown'
        ua_lower = user_agent.lower()
        if 'mobile' in ua_lower or 'android' in ua_lower or 'iphone' in ua_lower:
            device_type = 'mobile'
        elif 'tablet' in ua_lower or 'ipad' in ua_lower:
            device_type = 'tablet'
        elif user_agent:
            device_type = 'desktop'

        return cls.objects.create(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            device_type=device_type
        )


class BackupCode(models.Model):
    """
    2FA backup/recovery codes.
    Codes are stored as SHA-256 hashes for security.
    Each code can only be used once.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='backup_codes')
    code_hash = models.CharField(max_length=64)  # SHA-256 hash
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        status = "used" if self.is_used else "active"
        return f"Backup code for {self.user.username} ({status})"

    @staticmethod
    def generate_code():
        """
        Generate a cryptographically secure backup code.
        Returns an 8-character alphanumeric code.
        """
        # Use secrets module for cryptographic randomness
        return secrets.token_hex(4).upper()  # 8 hex characters

    @staticmethod
    def hash_code(code):
        """
        Hash a backup code using SHA-256.
        """
        return hashlib.sha256(code.encode('utf-8')).hexdigest()

    @classmethod
    def generate_codes_for_user(cls, user, count=10):
        """
        Generate a set of backup codes for a user.
        Invalidates existing unused codes before generating new ones.
        Returns the list of plaintext codes (only shown once to user).
        """
        # Delete any existing unused codes
        cls.objects.filter(user=user, is_used=False).delete()

        codes = []
        for _ in range(count):
            plain_code = cls.generate_code()
            codes.append(plain_code)
            cls.objects.create(
                user=user,
                code_hash=cls.hash_code(plain_code)
            )
        return codes

    @classmethod
    def verify_code(cls, user, code):
        """
        Verify a backup code and mark it as used.
        Returns True if valid, False otherwise.
        """
        code_hash = cls.hash_code(code.upper().replace('-', '').replace(' ', ''))
        try:
            backup_code = cls.objects.get(
                user=user,
                code_hash=code_hash,
                is_used=False
            )
            backup_code.is_used = True
            backup_code.used_at = timezone.now()
            backup_code.save()
            return True
        except cls.DoesNotExist:
            return False

    @classmethod
    def get_remaining_count(cls, user):
        """Get the count of remaining unused backup codes."""
        return cls.objects.filter(user=user, is_used=False).count()


class PasswordResetToken(models.Model):
    """
    Database-backed password reset tokens.
    Replaces the previous in-memory token storage for reliability and security.
    Tokens expire after 1 hour and are single-use.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        status = "used" if self.is_used else ("expired" if self.is_expired else "active")
        return f"Reset token for {self.user.username} ({status})"

    @property
    def is_expired(self):
        """Check if this token has expired."""
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        """Check if this token is valid (not used and not expired)."""
        return not self.is_used and not self.is_expired

    def consume(self):
        """
        Mark token as used so it cannot be reused.
        """
        self.is_used = True
        self.used_at = timezone.now()
        self.save()

    @classmethod
    def create_token(cls, user, request=None):
        """
        Generate a new password reset token for the user.
        Invalidates any existing unused tokens for the same user.
        Uses secrets.token_urlsafe for cryptographic randomness.
        """
        # Invalidate existing unused tokens for this user
        cls.objects.filter(user=user, is_used=False).update(is_used=True, used_at=timezone.now())

        # Get IP address from request if available
        ip_address = None
        if request:
            ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
            if ip_address:
                ip_address = ip_address.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')

        token_value = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timezone.timedelta(hours=1)

        return cls.objects.create(
            user=user,
            token=token_value,
            expires_at=expires_at,
            ip_address=ip_address
        )

    @classmethod
    def get_valid_token(cls, token_value):
        """
        Retrieve a valid (not used, not expired) token.
        Returns None if token is invalid.
        """
        try:
            token_obj = cls.objects.get(token=token_value, is_used=False)
            if token_obj.is_expired:
                return None
            return token_obj
        except cls.DoesNotExist:
            return None

    @classmethod
    def cleanup_expired(cls):
        """Remove tokens that have been expired for more than 24 hours."""
        cutoff = timezone.now() - timezone.timedelta(hours=24)
        cls.objects.filter(expires_at__lt=cutoff).delete()


class PasswordResetRateLimit(models.Model):
    """
    Track password reset requests for rate limiting.
    Prevents abuse by limiting requests per IP and per email.
    """
    ip_address = models.GenericIPAddressField(db_index=True)
    email = models.EmailField(db_index=True)
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-requested_at']

    @classmethod
    def is_rate_limited(cls, ip_address, email, max_per_ip=5, max_per_email=3, window_minutes=30):
        """
        Check if a password reset request should be rate limited.
        Limits: max_per_ip requests per IP and max_per_email requests per email within the window.
        """
        cutoff = timezone.now() - timezone.timedelta(minutes=window_minutes)

        ip_count = cls.objects.filter(
            ip_address=ip_address,
            requested_at__gte=cutoff
        ).count()

        email_count = cls.objects.filter(
            email=email,
            requested_at__gte=cutoff
        ).count()

        return ip_count >= max_per_ip or email_count >= max_per_email

    @classmethod
    def log_request(cls, ip_address, email):
        """Log a password reset request for rate limiting."""
        cls.objects.create(ip_address=ip_address, email=email)

    @classmethod
    def cleanup_old(cls):
        """Remove rate limit records older than 24 hours."""
        cutoff = timezone.now() - timezone.timedelta(hours=24)
        cls.objects.filter(requested_at__lt=cutoff).delete()


class PurchasedFeature(models.Model):
    """
    Track premium features purchased by users.
    Records one-time purchases of badges, roles, and profile customizations.
    All payments are processed through the bank transfer system to admin (user ID 1).
    """
    FEATURE_VERIFIED_BADGE = 'verified_badge'
    FEATURE_DEVELOPER_ROLE = 'developer_role'
    FEATURE_CUSTOM_THEME = 'custom_theme'
    FEATURE_CHOICES = [
        (FEATURE_VERIFIED_BADGE, 'Verified Badge'),
        (FEATURE_DEVELOPER_ROLE, 'Developer Role'),
        (FEATURE_CUSTOM_THEME, 'Custom Profile Theme'),
    ]

    FEATURE_PRICES = {
        FEATURE_VERIFIED_BADGE: 50,
        FEATURE_DEVELOPER_ROLE: 99,
        FEATURE_CUSTOM_THEME: 25,
    }

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchased_features')
    feature_type = models.CharField(max_length=30, choices=FEATURE_CHOICES)
    purchased_at = models.DateTimeField(auto_now_add=True)
    price_paid = models.IntegerField()  # Price at the time of purchase
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-purchased_at']
        unique_together = ['user', 'feature_type']

    def __str__(self):
        return f"{self.user.username} - {self.get_feature_type_display()}"

    @classmethod
    def get_price(cls, feature_type):
        """Get the current price for a feature type."""
        return cls.FEATURE_PRICES.get(feature_type)

    @classmethod
    def has_feature(cls, user, feature_type):
        """Check if a user has purchased and has an active feature."""
        return cls.objects.filter(
            user=user,
            feature_type=feature_type,
            is_active=True
        ).exists()


class ProfileTheme(models.Model):
    """
    Custom profile theme settings for users who purchased the theme feature.
    Stores color preferences for the user's public profile.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile_theme')
    primary_color = models.CharField(max_length=7, default='#667eea')  # Hex color
    secondary_color = models.CharField(max_length=7, default='#764ba2')  # Hex color
    bio_background_color = models.CharField(max_length=7, default='#f0f0ff')  # Hex color

    def __str__(self):
        return f"Theme for {self.user.username}"

    def clean(self):
        """ Validate hex color format."""
        import re
        hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')
        for field_name in ['primary_color', 'secondary_color', 'bio_background_color']:
            value = getattr(self, field_name)
            if not hex_pattern.match(value):
                from django.core.exceptions import ValidationError
                raise ValidationError({field_name: 'Invalid hex color format. Use #RRGGBB.'})


class UserSession(models.Model):
    """
    Track active user sessions for session management.
    Allows users to view and revoke their active sessions.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_sessions')
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=50, blank=True)
    is_current = models.BooleanField(default=False)  # Marks the current session
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-last_activity']

    def __str__(self):
        return f"Session for {self.user.username} from {self.ip_address}"

    @classmethod
    def create_or_update_session(cls, user, request):
        """
        Create or update a session record.
        """
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key

        # Get IP address securely
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
        if ip_address:
            ip_address = ip_address.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

        # Determine device type
        device_type = 'unknown'
        ua_lower = user_agent.lower()
        if 'mobile' in ua_lower or 'android' in ua_lower or 'iphone' in ua_lower:
            device_type = 'mobile'
        elif 'tablet' in ua_lower or 'ipad' in ua_lower:
            device_type = 'tablet'
        elif user_agent:
            device_type = 'desktop'

        # Mark all other sessions as not current
        cls.objects.filter(user=user, is_current=True).update(is_current=False)

        session, created = cls.objects.update_or_create(
            session_key=session_key,
            defaults={
                'user': user,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'device_type': device_type,
                'is_current': True,
                'is_active': True,
                'last_activity': timezone.now()
            }
        )
        return session

    def revoke(self):
        """
        Revoke this session.
        """
        from django.contrib.sessions.models import Session
        try:
            Session.objects.get(session_key=self.session_key).delete()
        except Session.DoesNotExist:
            pass
        self.is_active = False
        self.save()

    def get_browser_info(self):
        """Parse user agent to get browser info."""
        ua = self.user_agent.lower()
        if 'chrome' in ua and 'edg' not in ua:
            return 'Chrome'
        elif 'firefox' in ua:
            return 'Firefox'
        elif 'safari' in ua and 'chrome' not in ua:
            return 'Safari'
        elif 'edg' in ua:
            return 'Edge'
        elif 'opera' in ua or 'opr' in ua:
            return 'Opera'
        return 'Unknown Browser'
