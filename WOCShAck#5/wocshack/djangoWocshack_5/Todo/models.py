from django.db import models
from django.conf import settings


class Mission(models.Model):
    """
    Mission Board item — replaces the old TodoItem model.
    Each mission belongs to a user and tracks status, priority, due date, and category.
    Staff can create shared missions visible to all authenticated users.
    """

    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        CRITICAL = 'critical', 'Critical'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='missions',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    category = models.CharField(max_length=100, blank=True, default='')
    due_date = models.DateTimeField(null=True, blank=True)
    is_staff_shared = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        """Check if mission is past its due date and not completed/cancelled."""
        if self.due_date and self.status not in (self.Status.COMPLETED, self.Status.CANCELLED):
            from django.utils import timezone
            return self.due_date < timezone.now()
        return False
