"""
Shared helpers for developer plan limit enforcement.
"""
from Developer.models import CssProject, DeveloperSubscription


def get_css_project_limit_error(user):
    """
    Return a user-facing error message when the active plan's CSS project limit
    has been reached, or None when creation is allowed.
    """
    subscription = (
        DeveloperSubscription.objects.filter(
            user=user,
            status__in=[
                DeveloperSubscription.Status.ACTIVE,
                DeveloperSubscription.Status.TRIAL,
            ],
        )
        .select_related('plan')
        .first()
    )
    css_limit = subscription.plan.css_limit if subscription else 0
    if css_limit <= 0:
        return None

    current_count = CssProject.objects.filter(developer=user).count()
    if current_count < css_limit:
        return None

    plan_name = subscription.plan.name if subscription else 'current'
    return (
        f'CSS project limit reached. Your {plan_name} plan allows '
        f'{css_limit} CSS projects (you have {current_count}). '
        f'Upgrade your plan to create more.'
    )
