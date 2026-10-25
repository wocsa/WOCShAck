from django.core.management.base import BaseCommand
from django.utils import timezone
from Developer.models import DeveloperSubscription
from Community.services.notification_service import send_notification
from Community.models.notification import Notification

class Command(BaseCommand):
    help = 'Process auto-renewals for developer subscriptions.'

    def handle(self, *args, **options):
        self.stdout.write('Starting subscription processing...')
        now = timezone.now()

        # Query all active subscriptions that have reached or passed their end date
        due_subscriptions = DeveloperSubscription.objects.filter(
            status=DeveloperSubscription.Status.ACTIVE,
            current_period_end__lte=now
        ).select_related('user', 'plan')

        count_success = 0
        count_failed = 0

        for sub in due_subscriptions:
            if not sub.auto_renew:
                sub.status = DeveloperSubscription.Status.EXPIRED
                sub.save(update_fields=['status'])
                
                send_notification(
                    user=sub.user,
                    notif_type=Notification.NotifType.SYSTEM,
                    title="Subscription Expired",
                    message=f"Your {sub.plan.name} developer subscription has expired because auto-renew was disabled.",
                    action_url="/developer/subscription/",
                    priority="high"
                )
                count_failed += 1
                self.stdout.write(f"Expired {sub.user.username}'s {sub.plan.name} plan (auto-renew disabled).")
                continue

            success, error_msg = sub.attempt_renewal()
            
            if success:
                send_notification(
                    user=sub.user,
                    notif_type=Notification.NotifType.SYSTEM,
                    title="Subscription Renewed",
                    message=f"Your {sub.plan.name} developer subscription has been successfully renewed. {sub.plan.price_monthly} NE was charged to your bank account.",
                    action_url="/developer/subscription/",
                    priority="normal"
                )
                count_success += 1
                self.stdout.write(self.style.SUCCESS(f"Successfully renewed {sub.user.username}'s {sub.plan.name} plan."))
            else:
                send_notification(
                    user=sub.user,
                    notif_type=Notification.NotifType.SYSTEM,
                    title="Subscription Downgraded to Free Plan",
                    message=f"We could not renew your {sub.plan.name} developer subscription. Reason: {error_msg}. You have been moved to the Free plan.",
                    action_url="/developer/subscription/",
                    priority="high"
                )
                count_failed += 1
                self.stdout.write(self.style.ERROR(f"Failed to renew {sub.user.username}'s {sub.plan.name} plan: {error_msg} — downgraded to Free."))

        self.stdout.write(self.style.SUCCESS(f"Finished processing subscriptions. {count_success} successful, {count_failed} failed/expired."))
