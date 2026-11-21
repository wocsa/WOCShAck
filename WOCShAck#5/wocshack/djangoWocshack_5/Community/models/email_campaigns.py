import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class EmailCampaign(models.Model):

    class CampaignType(models.TextChoices):
        WELCOME       = 'welcome',       'Welcome'
        RE_ENGAGEMENT = 're_engagement', 'Re-engagement'
        MILESTONE     = 'milestone',     'Milestone'

    id                     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name                   = models.CharField(max_length=100)
    campaign_type          = models.CharField(max_length=15, choices=CampaignType.choices)
    trigger_days_inactive  = models.IntegerField(null=True, blank=True, help_text='Days of inactivity to trigger (re-engagement only)')
    is_active              = models.BooleanField(default=True)
    created_at             = models.DateTimeField(auto_now_add=True)
   

    class Meta:
        ordering = ['campaign_type']

    def __str__(self):
        return f"{self.name} ({self.get_campaign_type_display()})"


class EmailTemplate(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign   = models.ForeignKey(EmailCampaign, on_delete=models.CASCADE, related_name='templates')
    subject    = models.CharField(max_length=200)
    html_body  = models.TextField()
    text_body  = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.campaign.name}: {self.subject}"


class EmailSend(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_sends')
    campaign   = models.ForeignKey(EmailCampaign, on_delete=models.CASCADE, related_name='sends')
    template   = models.ForeignKey(EmailTemplate, on_delete=models.CASCADE, related_name='sends')
    sent_at    = models.DateTimeField(auto_now_add=True)
    opened_at  = models.DateTimeField(null=True, blank=True)
    is_bounced = models.BooleanField(default=False)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.user.username} — {self.campaign.name} ({self.sent_at.date()})"








#### M3 a tester :D 