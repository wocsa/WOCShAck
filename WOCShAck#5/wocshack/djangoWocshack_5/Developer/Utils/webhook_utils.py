"""
Webhook signing and delivery utilities.
"""
import hmac
import hashlib
import json
import logging
import urllib.request
import urllib.error

from django.utils import timezone

logger = logging.getLogger(__name__)


def sign_payload(secret, payload):
    """Create HMAC-SHA256 signature for a webhook payload."""
    if isinstance(payload, dict):
        payload = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def verify_signature(secret, payload, signature):
    """Validate an incoming webhook signature."""
    expected = sign_payload(secret, payload)
    return hmac.compare_digest(expected, signature)


def deliver_webhook(webhook, event_type, data, max_attempts=3):
    """
    Deliver a webhook payload via HTTP POST with retry logic.
    Returns the WebhookDelivery record.
    """
    from Developer.models import WebhookDelivery

    payload = {
        'event': event_type,
        'data': data,
        'timestamp': timezone.now().isoformat(),
        'webhook_id': str(webhook.id),
    }
    payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    signature = sign_payload(webhook.secret, payload_bytes)

    delivery = WebhookDelivery.objects.create(
        webhook=webhook,
        event_type=event_type,
        payload=payload,
    )

    for attempt in range(1, max_attempts + 1):
        delivery.attempts = attempt
        try:
            req = urllib.request.Request(
                webhook.url,
                data=payload_bytes,
                headers={
                    'Content-Type': 'application/json',
                    'X-Webhook-Signature': signature,
                    'X-Webhook-Event': event_type,
                    'User-Agent': 'VRC-Developer-Webhooks/1.0',
                },
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                delivery.status_code = response.getcode()
                delivery.response_body = response.read().decode('utf-8', errors='replace')[:2000]
                delivery.delivered_at = timezone.now()
                delivery.save()

                webhook.last_triggered_at = timezone.now()
                webhook.failure_count = 0
                webhook.save(update_fields=['last_triggered_at', 'failure_count'])
                return delivery

        except urllib.error.HTTPError as e:
            delivery.status_code = e.code
            delivery.response_body = e.read().decode('utf-8', errors='replace')[:2000]
            logger.warning(f"Webhook delivery HTTP error: {webhook.url} - {e.code}")

        except Exception as e:
            delivery.response_body = str(e)[:2000]
            logger.warning(f"Webhook delivery failed: {webhook.url} - {e}")

    # All attempts exhausted
    delivery.save()
    webhook.failure_count += 1
    webhook.save(update_fields=['failure_count'])

    # Disable webhook after 10 consecutive failures
    if webhook.failure_count >= 10:
        webhook.is_active = False
        webhook.save(update_fields=['is_active'])
        logger.warning(f"Webhook disabled after {webhook.failure_count} failures: {webhook.url}")

    return delivery
