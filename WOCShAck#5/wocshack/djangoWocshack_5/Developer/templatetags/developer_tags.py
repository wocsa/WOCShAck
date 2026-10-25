"""Template tags for Developer module."""
from django import template

from Account.models import PurchasedFeature

register = template.Library()


@register.simple_tag
def is_developer(user):
    """
    Check if the user has purchased the developer_role feature.
    Handles edge cases with AnonymousUser, SimpleLazyObject, and missing attributes.
    """
    try:
        if user is None:
            return False
        if not getattr(user, 'is_authenticated', False):
            return False
        return PurchasedFeature.has_feature(user, 'developer_role')
    except Exception:
        return False
