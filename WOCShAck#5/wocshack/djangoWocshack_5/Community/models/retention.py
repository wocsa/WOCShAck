import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

INACTIVITY_DAYS = [(3, '3 days'), (7, '7 days'), (14, '14 days'), (30, '30 days'), (60, '60 days')]


class InactivityTrigger(models.Model):

    class ActionType(models.TextChoices):
        EMAIL        = 'email',        'Send Email'
        PUSH         = 'push',         'Send Push Notification'
        NOTIFICATION = 'notification', 'In-app Notification'

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    days_inactive  = models.IntegerField(choices=INACTIVITY_DAYS)
    action_type    = models.CharField(max_length=15, choices=ActionType.choices)
    campaign       = models.ForeignKey(
        'EmailCampaign', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inactivity_triggers',
    )
    is_active      = models.BooleanField(default=True)

    class Meta:
        ordering = ['days_inactive']

    def __str__(self):
        return f"{self.days_inactive}d inactive → {self.get_action_type_display()}"


class ReengagementAction(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reengagement_actions')
    trigger      = models.ForeignKey(InactivityTrigger, on_delete=models.CASCADE, related_name='actions')
    action_taken = models.DateTimeField(auto_now_add=True)
    was_effective = models.BooleanField(null=True, blank=True, help_text='True if user returned within 7 days')

    class Meta:
        ordering = ['-action_taken']

    def __str__(self):
        return f"{self.user.username} — {self.trigger} ({self.action_taken.date()})"
