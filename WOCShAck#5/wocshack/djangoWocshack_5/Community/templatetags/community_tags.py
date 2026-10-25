import bleach
import markdown as md
from django import template
from django.utils.safestring import mark_safe

from Community.functions import is_content_creator as _is_content_creator

register = template.Library()

ALLOWED_TAGS = [
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'a', 'em', 'strong',
    'code', 'pre', 'blockquote', 'br', 'hr',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'img', 'span', 'div',
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'img': ['src', 'alt', 'title'],
    'code': ['class'],
    'pre': ['class'],
}


@register.filter
def markdownify(text):
    """Render Markdown text as safe HTML."""
    if not text:
        return ''
    html = md.markdown(
        text,
        extensions=['fenced_code', 'tables', 'nl2br'],
    )
    clean_html = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)
    return mark_safe(clean_html)


@register.simple_tag
def check_content_creator(user):
    """Returns True if user can create blog posts, events, and tutorials."""
    return _is_content_creator(user)
