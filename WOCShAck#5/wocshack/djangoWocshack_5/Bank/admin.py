from django.contrib import admin, messages
from .models import PaymentSession, BankCard, Transaction


@admin.register(PaymentSession)
class PaymentSessionAdmin(admin.ModelAdmin):
    list_display = ('sid', '_from', 'to', 'amount')
    search_fields = ('sid', '_from', 'to')


@admin.action(description="Unlock PIN (reset failed attempts)")
def unlock_pin(modeladmin, request, queryset):
    from .Utils import client
    success_users, failed_users = [], []
    for card in queryset.select_related('user'):
        cli, sid = client.make_connection()
        if not cli or not sid:
            failed_users.append(card.user.username)
            continue
        try:
            cli.reset_attempts(sid, card.user.id)
            success_users.append(card.user.username)
        finally:
            try:
                cli.close_session(sid)
                cli.close()
            except Exception:
                pass
    if success_users:
        modeladmin.message_user(request, f"PIN unlocked for: {', '.join(success_users)}", messages.SUCCESS)
    if failed_users:
        modeladmin.message_user(request, f"Failed (banking server unreachable) for: {', '.join(failed_users)}", messages.ERROR)


@admin.register(BankCard)
class BankCardAdmin(admin.ModelAdmin):
    list_display = ('user', 'card_type', 'status', 'payment_number', 'created_at')
    list_filter = ('card_type', 'status')
    search_fields = ('user__username', 'payment_number')
    readonly_fields = ('created_at', 'updated_at')
    actions = [unlock_pin]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction_type', 'amount', 'status', 'created_at')
    list_filter = ('transaction_type', 'status')
    search_fields = ('user__username', 'counterpart_payment_number', 'note')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
