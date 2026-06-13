import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class EngagementScore(models.Model):

    class RiskLevel(models.TextChoices):
        LOW      = 'low',      'Low'
        MEDIUM   = 'medium',   'Medium'
        HIGH     = 'high',     'High'
        CRITICAL = 'critical', 'Critical (churning)'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user             = models.OneToOneField(User, on_delete=models.CASCADE, related_name='engagement_score')
    activity_score   = models.IntegerField(default=0)
    social_score     = models.IntegerField(default=0)
    purchase_score   = models.IntegerField(default=0)
    content_score    = models.IntegerField(default=0)
    total_score      = models.IntegerField(default=0)
    risk_level       = models.CharField(max_length=10, choices=RiskLevel.choices, default=RiskLevel.LOW)
    computed_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-total_score']

    def __str__(self):
        return f"{self.user.username}: score {self.total_score} ({self.risk_level})"

    def recalculate(self):
        self.total_score = self.activity_score + self.social_score + self.purchase_score + self.content_score
        if self.total_score < 10:
            self.risk_level = self.RiskLevel.CRITICAL
        elif self.total_score < 50:
            self.risk_level = self.RiskLevel.HIGH
        elif self.total_score < 150:
            self.risk_level = self.RiskLevel.MEDIUM
        else:
            self.risk_level = self.RiskLevel.LOW
        self.save()


class ScoreComponent(models.Model):
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    engagement_score = models.ForeignKey(EngagementScore, on_delete=models.CASCADE, related_name='components')
    component_type   = models.CharField(max_length=50)
    value            = models.IntegerField()
    computed_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-computed_at']

    def __str__(self):
        return f"{self.engagement_score.user.username} — {self.component_type}: {self.value}"


class ActivityMetric(models.Model):
    """Daily aggregate metrics for admin analytics dashboard."""
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date           = models.DateField(unique=True)
    dau_count      = models.IntegerField(default=0, help_text='Daily active users')
    mau_count      = models.IntegerField(default=0, help_text='Monthly active users')
    new_users      = models.IntegerField(default=0)
    retention_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.date}: DAU={self.dau_count}, MAU={self.mau_count}"


class EngagementFunnel(models.Model):
    """Conversion funnel tracking for a given date and funnel stage."""
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name            = models.CharField(max_length=100)
    stage           = models.IntegerField()
    user_count      = models.IntegerField(default=0)
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    date            = models.DateField()

    class Meta:
        ordering = ['-date', 'stage']

    def __str__(self):
        return f"{self.name} stage {self.stage} on {self.date}: {self.conversion_rate}%"
