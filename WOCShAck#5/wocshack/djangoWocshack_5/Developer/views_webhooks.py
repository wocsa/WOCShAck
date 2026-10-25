"""
Developer module views — webhook management.
"""
import secrets
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.utils.html import escape
from django.views.decorators.http import require_POST

from .views import developer_required
from .models import Webhook, WebhookDelivery
from .Utils.webhook_utils import deliver_webhook


WEBHOOK_EVENT_CHOICES = [
    'sale.completed',
    'sale.refunded',
    'listing.published',
    'listing.rejected',
    'review.created',
    'payout.completed',
    'subscription.renewed',
    'subscription.cancelled',
]


@developer_required
def webhook_list(request):
    """List all webhooks."""
    webhooks = Webhook.objects.filter(developer=request.user)
    context = {'webhooks': webhooks, 'event_choices': WEBHOOK_EVENT_CHOICES}
    return render(request, 'developer/webhooks.html', context)


@developer_required
def create_webhook(request):
    """Create a new webhook."""
    if request.method == 'POST':
        url = request.POST.get('url', '')[:200]
        events = request.POST.getlist('events')

        if not url:
            messages.error(request, 'Webhook URL is required.')
            return redirect('developer_webhooks')

        # Validate events
        events = [e for e in events if e in WEBHOOK_EVENT_CHOICES]
        if not events:
            messages.error(request, 'Select at least one event.')
            return redirect('developer_webhooks')

        secret = secrets.token_hex(32)

        webhook = Webhook.objects.create(
            developer=request.user,
            url=url,
            secret=secret,
            events=events,
        )

        messages.success(request, f'Webhook created. Signing secret: {secret}')
        return redirect('developer_webhooks')

    context = {'event_choices': WEBHOOK_EVENT_CHOICES}
    return render(request, 'developer/webhooks.html', context)


@developer_required
def edit_webhook(request, webhook_id):
    """Edit a webhook."""
    webhook = get_object_or_404(Webhook, id=webhook_id, developer=request.user)

    if request.method == 'POST':
        webhook.url = request.POST.get('url', webhook.url)[:200]
        events = request.POST.getlist('events')
        webhook.events = [e for e in events if e in WEBHOOK_EVENT_CHOICES]
        webhook.is_active = request.POST.get('is_active') == 'on'
        webhook.save()
        messages.success(request, 'Webhook updated.')
        return redirect('developer_webhooks')

    context = {
        'webhook': webhook,
        'event_choices': WEBHOOK_EVENT_CHOICES,
    }
    return render(request, 'developer/edit_webhook.html', context)


@developer_required
@require_POST
def delete_webhook(request, webhook_id):
    """Delete a webhook."""
    webhook = get_object_or_404(Webhook, id=webhook_id, developer=request.user)
    webhook.delete()
    messages.success(request, 'Webhook deleted.')
    return redirect('developer_webhooks')


@developer_required
def webhook_logs(request, webhook_id):
    """View delivery history for a webhook."""
    webhook = get_object_or_404(Webhook, id=webhook_id, developer=request.user)
    deliveries = WebhookDelivery.objects.filter(webhook=webhook)[:50]
    context = {'webhook': webhook, 'deliveries': deliveries}
    return render(request, 'developer/webhook_logs.html', context)


@developer_required
@require_POST
def test_webhook(request, webhook_id):
    """Send a test webhook delivery."""
    webhook = get_object_or_404(Webhook, id=webhook_id, developer=request.user)

    test_data = {
        'test': True,
        'message': 'This is a test webhook delivery from VRC Developer Portal.',
    }

    delivery = deliver_webhook(webhook, 'test.ping', test_data)

    if delivery.delivered_at:
        messages.success(request, f'Test webhook delivered successfully (HTTP {delivery.status_code}).')
    else:
        messages.error(request, f'Test webhook failed after {delivery.attempts} attempts.')

    return redirect('developer_webhook_logs', webhook_id=webhook.id)
