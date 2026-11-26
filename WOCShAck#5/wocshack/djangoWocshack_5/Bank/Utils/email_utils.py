"""
Bank email notification utilities.

Sends transaction notifications and spending limit alerts via the internal
webmail service at 172.28.0.4, following the same pattern used by the
Account and Forum modules.

Email failures are always suppressed so they never disrupt the banking flow.
"""
import logging
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger('bank')

BANK_EMAIL_SOURCE = 'V.R.C Banking'


def _send_webmail(destination, subject, content, timeout=8):
    """
    Send email via the internal webmail HTTP service.

    Args:
        destination: Recipient email address.
        subject: Email subject line.
        content: HTML email body.
        timeout: HTTP request timeout in seconds.

    Returns:
        dict with result or None on failure.
    """
    if not destination:
        return None
    query_data = {
        'source': BANK_EMAIL_SOURCE,
        'destination': destination,
        'subject': subject,
        'content': content,
    }
    url = f'http://{settings.WEBMAIL_HOST}/send?' + urllib.parse.urlencode(query_data)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'wocshack-bank-notifier/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read().decode('utf-8', errors='replace')
            return {'url': url, 'status': status, 'body': body}
    except Exception as e:
        logger.warning(
            "Bank webmail send failed: destination=%s subject=%s error=%s",
            destination, subject, str(e)
        )
        return {'url': url, 'error': str(e)}


def send_transfer_notification(user, amount, recipient_number, note, balance_after, direction='out'):
    """
    Notify a user about a completed transfer.

    Args:
        user: Django User object (sender or receiver).
        amount: Decimal transfer amount.
        recipient_number: Counterpart account number (16-digit string).
        note: Optional transfer note.
        balance_after: Decimal balance after transaction (may be None).
        direction: 'out' for sent transfer, 'in' for received transfer.
    """
    try:
        email = user.email
        if not email:
            return None

        display_name = user.get_full_name() or user.username
        masked = f"**** **** **** {recipient_number[-4:]}" if len(recipient_number) >= 4 else recipient_number

        if direction == 'out':
            subject = f"Transfer Sent - {amount:.2f} NE | V.R.C Banking"
            action_label = "sent to"
            color = '#ef4444'
            icon = '&#x2B06;'
            sign = '-'
        else:
            subject = f"Transfer Received - {amount:.2f} NE | V.R.C Banking"
            action_label = "received from"
            color = '#22c55e'
            icon = '&#x2B07;'
            sign = '+'

        balance_row = ''
        if balance_after is not None:
            balance_row = (
                f'<tr>'
                f'<td style="padding:8px 12px;color:#888;">Updated Balance</td>'
                f'<td style="padding:8px 12px;font-weight:bold;color:#333;">{balance_after:.2f} NE</td>'
                f'</tr>'
            )

        note_row = ''
        if note:
            # Escape note to prevent HTML injection in email
            import html
            safe_note = html.escape(str(note)[:500])
            note_row = (
                f'<tr>'
                f'<td style="padding:8px 12px;color:#888;">Note</td>'
                f'<td style="padding:8px 12px;color:#555;">{safe_note}</td>'
                f'</tr>'
            )

        content = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#333;">
    <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:24px;border-radius:8px 8px 0 0;">
        <h1 style="color:white;margin:0;font-size:22px;">
            {icon} Transfer {direction.capitalize()}
        </h1>
        <p style="color:rgba(255,255,255,0.85);margin:6px 0 0 0;font-size:14px;">
            Hello {display_name}, a transfer was {action_label} account {masked}.
        </p>
    </div>

    <div style="padding:24px;background:#fff;border:1px solid #eee;">
        <div style="text-align:center;margin-bottom:20px;">
            <span style="font-size:36px;font-weight:900;color:{color};">
                {sign}{amount:.2f} NE
            </span>
        </div>

        <table style="width:100%;border-collapse:collapse;font-size:14px;border:1px solid #eee;border-radius:8px;overflow:hidden;">
            <tr style="background:#f8f9ff;">
                <td style="padding:8px 12px;color:#888;">Account</td>
                <td style="padding:8px 12px;font-weight:bold;color:#333;">{masked}</td>
            </tr>
            {balance_row}
            {note_row}
        </table>

        <p style="margin-top:16px;font-size:13px;color:#888;">
            If you did not authorize this transaction, please contact support immediately
            and lock your card from the banking dashboard.
        </p>
    </div>

    <div style="padding:12px 24px;background:#fafafa;border:1px solid #eee;border-top:none;
                border-radius:0 0 8px 8px;text-align:center;">
        <p style="color:#aaa;font-size:12px;margin:0;">
            V.R.C Banking &mdash; Automated notification. Do not reply.
        </p>
    </div>
</div>
"""
        return _send_webmail(email, subject, content)
    except Exception as e:
        logger.error("send_transfer_notification error for user %s: %s", user.id, str(e))
        return None

