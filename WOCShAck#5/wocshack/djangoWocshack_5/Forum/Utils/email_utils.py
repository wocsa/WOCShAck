"""
Forum email notification utilities.

Sends email notifications via the internal webmail service (Flask container at 172.28.0.4).
Uses the exact same HTTP-based email sending pattern as the Account module
(Account/views.py build_send_email_url).

Email notifications are sent for:
- Replies to a user's topic
- @mentions in a post
- Moderation actions (warnings, mutes)
"""
import os
import logging
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

FORUM_EMAIL_SOURCE = 'V.R.C Forum'


def build_send_email_url(destination, subject, content, source=FORUM_EMAIL_SOURCE, timeout=5):
    """
    Send an email via the internal webmail HTTP service.

    This function mirrors Account.views.build_send_email_url exactly, using the
    same Flask webmail container at 172.28.0.4 on port 80.

    Args:
        destination: Recipient email address.
        subject: Email subject line.
        content: HTML email body content.
        source: Sender display name (default: 'V.R.C Forum').
        timeout: HTTP request timeout in seconds (default: 5).

    Returns:
        dict with 'url' and either 'status'+'body' on success, or 'error' on failure.
    """
    query_data = {
        'source': source,
        'destination': destination,
        'subject': subject,
        'content': content,
    }
    url = f'http://{settings.WEBMAIL_HOST}/send?' + urllib.parse.urlencode(query_data)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'wocshack-email-sender/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read().decode('utf-8', errors='replace')
            return {'url': url, 'status': status, 'body': body}
    except Exception as e:
        logger.warning("Forum email send failed: destination=%s subject=%s error=%s",
                        destination, subject, str(e))
        return {'url': url, 'error': str(e)}


def send_forum_email(destination, subject, content):
    """
    High-level helper to send a forum notification email.

    Wraps build_send_email_url with logging and error suppression so that
    email failures never break the main forum workflow.

    Args:
        destination: Recipient email address.
        subject: Email subject line.
        content: HTML email body content.

    Returns:
        dict with send result, or None if email could not be sent.
    """
    if not destination:
        logger.debug("Forum email skipped: no destination address")
        return None

    try:
        result = build_send_email_url(
            destination=destination,
            subject=subject,
            content=content
        )
        if 'error' in result:
            logger.warning("Forum email delivery issue: %s", result['error'])
        return result
    except Exception as e:
        logger.error("Forum email unexpected error: %s", str(e))
        return None


def send_reply_notification_email(topic_author, replier_username, topic_title, post_url):
    """
    Send email notification when someone replies to a topic.

    Args:
        topic_author: Django User object (the topic owner receiving the notification).
        replier_username: Username of the person who replied.
        topic_title: Title of the topic that received a reply.
        post_url: Relative URL to the new reply post.
    """
    server_name = os.environ.get('SERVER_NAME', 'localhost:8000')
    absolute_url = f"http://{server_name}{post_url}"

    subject = f"New reply to your topic: {topic_title}"
    content = (
        f"Hello {topic_author.username},<br><br>"
        f"<strong>{replier_username}</strong> replied to your topic "
        f"\"<strong>{topic_title}</strong>\".<br><br>"
        f"<a href='{absolute_url}' target='_blank'>View the reply</a><br><br>"
        f"-- V.R.C Forum"
    )

    return send_forum_email(
        destination=topic_author.email,
        subject=subject,
        content=content
    )


def send_mention_notification_email(mentioned_user, mentioner_username, topic_title, post_url):
    """
    Send email notification when someone @mentions a user.

    Args:
        mentioned_user: Django User object (the user who was mentioned).
        mentioner_username: Username of the person who made the mention.
        topic_title: Title of the topic where the mention occurred.
        post_url: Relative URL to the post containing the mention.
    """
    server_name = os.environ.get('SERVER_NAME', 'localhost:8000')
    absolute_url = f"http://{server_name}{post_url}"

    subject = f"You were mentioned by @{mentioner_username}"
    content = (
        f"Hello {mentioned_user.username},<br><br>"
        f"<strong>@{mentioner_username}</strong> mentioned you in the topic "
        f"\"<strong>{topic_title}</strong>\".<br><br>"
        f"<a href='{absolute_url}' target='_blank'>View the post</a><br><br>"
        f"-- V.R.C Forum"
    )

    return send_forum_email(
        destination=mentioned_user.email,
        subject=subject,
        content=content
    )


def send_warning_notification_email(warned_user, severity, reason, moderator_username):
    """
    Send email notification when a user receives a warning.

    Args:
        warned_user: Django User object (the user who received the warning).
        severity: Warning severity level (notice, warning, final_warning).
        reason: Text reason for the warning.
        moderator_username: Username of the moderator who issued the warning.
    """
    severity_display = severity.replace('_', ' ').title()
    server_name = os.environ.get('SERVER_NAME', 'localhost:8000')
    forum_url = f"http://{server_name}/forum/"

    subject = f"Forum Moderation: You received a {severity_display}"
    content = (
        f"Hello {warned_user.username},<br><br>"
        f"You have received a <strong>{severity_display}</strong> from the forum moderation team.<br><br>"
        f"<strong>Reason:</strong> {reason}<br><br>"
        f"Please review the forum rules and ensure your future posts comply with community guidelines.<br><br>"
        f"<a href='{forum_url}' target='_blank'>Go to Forum</a><br><br>"
        f"-- V.R.C Forum Moderation Team"
    )

    return send_forum_email(
        destination=warned_user.email,
        subject=subject,
        content=content
    )


def send_mute_notification_email(muted_user, reason, duration_str, is_permanent):
    """
    Send email notification when a user is muted.

    Args:
        muted_user: Django User object (the user who was muted).
        reason: Text reason for the mute.
        duration_str: Human-readable duration string (e.g., "24 hours").
        is_permanent: Boolean indicating if the mute is permanent.
    """
    server_name = os.environ.get('SERVER_NAME', 'localhost:8000')
    forum_url = f"http://{server_name}/forum/"

    if is_permanent:
        duration_text = "permanently"
    else:
        duration_text = f"for {duration_str}"

    subject = "Forum Moderation: Your posting privileges have been restricted"
    content = (
        f"Hello {muted_user.username},<br><br>"
        f"Your posting privileges on the V.R.C Forum have been restricted "
        f"<strong>{duration_text}</strong>.<br><br>"
        f"<strong>Reason:</strong> {reason}<br><br>"
        f"During the mute period, you will not be able to create new posts or topics.<br><br>"
        f"If you believe this action was taken in error, please contact the moderation team.<br><br>"
        f"<a href='{forum_url}' target='_blank'>Go to Forum</a><br><br>"
        f"-- V.R.C Forum Moderation Team"
    )

    return send_forum_email(
        destination=muted_user.email,
        subject=subject,
        content=content
    )
