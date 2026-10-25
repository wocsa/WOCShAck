"""
Developer module views — dashboard, profile, and subscription management.
"""
import logging
from functools import wraps
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST

import sys
import time

from Account.models import PurchasedFeature
from .models import (
    DeveloperProfile, DeveloperPlan, DeveloperSubscription,
    CssProject, CssListing, SaleAnalytics, DeveloperBalance,
    Webhook, Payout,
)
from Api.models import ApiKey
from Shopping.models import OrderItem
from Bank.Utils import client as bank_client
from Bank.Utils.external_calls import verify_user_pin
from Bank.models import Transaction as BankTransaction

logger = logging.getLogger(__name__)


# =============================================================================
# ACCESS CONTROL DECORATOR
# =============================================================================

def _sync_profile_commission_rate(user, plan):
    """Sync the DeveloperProfile.commission_rate with the subscription plan's rate."""
    try:
        profile = DeveloperProfile.objects.get(user=user)
        if profile.commission_rate != plan.commission_rate:
            profile.commission_rate = plan.commission_rate
            profile.save(update_fields=['commission_rate'])
    except DeveloperProfile.DoesNotExist:
        pass  # profile will pick up the rate when created later


def developer_required(view_func):
    """
    Require the user to have purchased the developer_role feature.
    Redirects to the Account store if the user is not a developer.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser) and \
                not PurchasedFeature.has_feature(request.user, 'developer_role'):
            messages.error(request, 'You need the Developer Role to access this page. Purchase it from the store.')
            return redirect('/account/store/')
        # Auto-subscribe to Free plan on first developer access if no active subscription exists
        has_active_sub = DeveloperSubscription.objects.filter(
            user=request.user,
            status__in=[DeveloperSubscription.Status.ACTIVE, DeveloperSubscription.Status.TRIAL]
        ).exists()
        if not has_active_sub:
            free_plan = DeveloperPlan.get_free_plan()
            if free_plan:
                DeveloperSubscription.objects.create(
                    user=request.user,
                    plan=free_plan,
                    status=DeveloperSubscription.Status.ACTIVE,
                    current_period_start=timezone.now(),
                    current_period_end=timezone.now() + timezone.timedelta(days=30),
                )
                _sync_profile_commission_rate(request.user, free_plan)
        return view_func(request, *args, **kwargs)
    return login_required(_wrapped_view)


# =============================================================================
# DASHBOARD
# =============================================================================

@developer_required
def dashboard(request):
    """Developer dashboard with overview cards, quick actions, and activity feed."""
    user = request.user

    from Api.models import Css as ApiCss

    # Ensure developer profile exists
    profile, _ = DeveloperProfile.objects.get_or_create(
        user=user,
        defaults={'display_name': user.username}
    )

    # Ensure balance record exists
    balance, _ = DeveloperBalance.objects.get_or_create(developer=user)

    # Stats — count both Developer CssProject entries and Api.Css marketplace files
    dev_projects_count = CssProject.objects.filter(developer=user).count()
    api_css_count = ApiCss.objects.filter(creator=user).count()
    projects_count = dev_projects_count + api_css_count

    listings_count = CssListing.objects.filter(developer=user).count()
    published_count = CssListing.objects.filter(developer=user, status='published').count()

    # Recent revenue (last 30 days)
    thirty_days_ago = timezone.now().date() - timezone.timedelta(days=30)
    recent_analytics = SaleAnalytics.objects.filter(
        developer=user,
        date__gte=thirty_days_ago
    )
    monthly_revenue = recent_analytics.aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
    monthly_sales = recent_analytics.aggregate(total=Sum('sales_count'))['total'] or 0

    # Active subscription
    subscription = DeveloperSubscription.objects.filter(
        user=user,
        status__in=['active', 'trial']
    ).select_related('plan').first()

    # Recent projects — combine Developer CssProject and Api.Css (marketplace files)
    recent_dev_projects = list(CssProject.objects.filter(developer=user).order_by('-updated_at')[:5])
    recent_api_css = list(ApiCss.objects.filter(creator=user).order_by('-updated_at')[:5])

    # API keys and webhooks count
    api_keys_count = ApiKey.objects.filter(user=user, is_active=True).count()
    webhooks_count = Webhook.objects.filter(developer=user, is_active=True).count()

    # Recent payments — sales of this developer's CSS files (via Shopping.OrderItem)
    recent_sales_qs = (
        OrderItem.objects.filter(css_file__creator=user)
        .select_related('order', 'order__user')
        .order_by('-order__created_at')[:10]
    )
    # Compute per-item commission after proportional coupon discount
    commission_rate = profile.commission_rate
    recent_sales = []
    for item in recent_sales_qs:
        order = item.order
        if order.discount_amount and order.total_amount:
            discount_ratio = order.discount_amount / order.total_amount
            effective_price = item.price_at_purchase * (1 - discount_ratio)
        else:
            effective_price = item.price_at_purchase
        item.commission = (effective_price * commission_rate).quantize(Decimal('0.01'))
        recent_sales.append(item)

    # Recent payouts — withdrawal requests by this developer
    recent_payouts = Payout.objects.filter(developer=user).order_by('-requested_at')[:10]

    context = {
        'profile': profile,
        'balance': balance,
        'projects_count': projects_count,
        'listings_count': listings_count,
        'published_count': published_count,
        'monthly_revenue': monthly_revenue,
        'monthly_sales': monthly_sales,
        'subscription': subscription,
        'recent_projects': recent_dev_projects,
        'recent_css_files': recent_api_css,
        'api_css_count': api_css_count,
        'api_keys_count': api_keys_count,
        'webhooks_count': webhooks_count,
        'recent_sales': recent_sales,
        'recent_payouts': recent_payouts,
    }
    return render(request, 'developer/dashboard.html', context)


# =============================================================================
# PROFILE
# =============================================================================

@developer_required
def developer_profile(request):
    """View developer profile."""
    profile, _ = DeveloperProfile.objects.get_or_create(
        user=request.user,
        defaults={'display_name': request.user.username}
    )
    context = {'profile': profile}
    return render(request, 'developer/profile.html', context)


@developer_required
def edit_developer_profile(request):
    """Edit developer profile."""
    profile, _ = DeveloperProfile.objects.get_or_create(
        user=request.user,
        defaults={'display_name': request.user.username}
    )

    if request.method == 'POST':
        profile.display_name = escape(request.POST.get('display_name', '')[:150])
        profile.tagline = escape(request.POST.get('tagline', '')[:255])
        profile.website = request.POST.get('website', '')[:200]
        profile.github_url = request.POST.get('github_url', '')[:200]
        profile.twitter_url = request.POST.get('twitter_url', '')[:200]

        specialties_raw = request.POST.get('specialties', '')
        if specialties_raw:
            profile.specialties = [s.strip() for s in specialties_raw.split(',') if s.strip()][:20]

        profile.save()
        messages.success(
            request,
            'Profile updated successfully. Your developer info is now visible on your public profile.'
        )
        return redirect('developer_profile')

    context = {'profile': profile}
    return render(request, 'developer/edit_profile.html', context)


# =============================================================================
# SUBSCRIPTION
# =============================================================================

@developer_required
def subscribe(request):
    """View available developer plans."""
    plans = DeveloperPlan.objects.filter(is_active=True)
    current_sub = DeveloperSubscription.objects.filter(
        user=request.user,
        status__in=['active', 'trial']
    ).select_related('plan').first()

    context = {
        'plans': plans,
        'current_sub': current_sub,
    }
    return render(request, 'developer/subscribe.html', context)


@developer_required
def subscribe_to_plan(request, plan_slug):
    """Subscribe to a specific plan. Free plans activate immediately; paid plans go to checkout."""
    plan = get_object_or_404(DeveloperPlan, slug=plan_slug, is_active=True)

    if request.method != 'POST':
        return redirect('developer_subscribe')

    if plan.price_monthly == Decimal('0.00'):
        # Free plan — activate immediately, no payment needed
        DeveloperSubscription.objects.filter(
            user=request.user,
            status__in=['active', 'trial']
        ).update(status='cancelled')
        DeveloperSubscription.objects.create(
            user=request.user,
            plan=plan,
            status=DeveloperSubscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
        )
        _sync_profile_commission_rate(request.user, plan)
        messages.success(request, f'Subscribed to {plan.name} plan!')
        return redirect('developer_subscription')

    # Paid plan — redirect to payment checkout
    request.session['subscription_plan_slug'] = plan_slug
    return redirect('developer_subscription_checkout')


@developer_required
def subscription_checkout(request):
    """Payment step for paid plan subscriptions."""
    plan_slug = request.session.get('subscription_plan_slug')
    if not plan_slug:
        return redirect('developer_subscribe')

    plan = get_object_or_404(DeveloperPlan, slug=plan_slug, is_active=True)

    if plan.price_monthly == Decimal('0.00'):
        return redirect('developer_subscribe')

    if request.method == 'GET':
        return render(request, 'developer/subscription_checkout.html', {'plan': plan})

    # POST — process payment
    pin = request.POST.get('pin', '').strip()

    if not verify_user_pin(request.user.id, pin):
        messages.error(request, 'Incorrect bank PIN. Please try again.')
        return render(request, 'developer/subscription_checkout.html', {'plan': plan})

    # Process bank transaction: user → admin
    payment_error = None
    tx_ref = ''
    try:
        from django.contrib.auth.models import User as DjangoUser
        admin_user = DjangoUser.objects.filter(is_superuser=True).first()
        admin_bank_id = admin_user.id if admin_user else 1

        cli, sid = bank_client.make_connection()
        if cli and sid:
            try:
                user_response = cli.get_user(sid, request.user.id)
                time.sleep(0.3)
                if isinstance(user_response, dict) and user_response.get('success'):
                    user_data = user_response.get('user', {})
                    balance = Decimal(str(user_data.get('balance', 0)))
                    bank_user_id = user_data.get('id')

                    if plan.price_monthly > balance:
                        payment_error = (
                            f'Insufficient funds. Your balance is {balance} NE, '
                            f'but the plan costs {plan.price_monthly} NE/month.'
                        )
                    else:
                        result = cli.transaction(
                            sid=sid,
                            from_user=bank_user_id,
                            to_user=admin_bank_id,
                            amount=float(plan.price_monthly),
                        )
                        time.sleep(0.3)
                        if result and result.get('status') == 'success':
                            tx_ref = result.get('tx_id', '') or result.get('transaction_id', '')
                        else:
                            payment_error = result.get('message', 'Transaction failed.') if result else 'No response from bank.'
                else:
                    payment_error = 'Could not retrieve your bank account.'
            finally:
                cli.close_session(sid)
                cli.close()
        else:
            payment_error = 'Bank system unavailable. Please try again later.'
    except Exception as e:
        payment_error = f'Payment error: {e}'

    if payment_error:
        messages.error(request, payment_error)
        return render(request, 'developer/subscription_checkout.html', {'plan': plan})

    # Payment successful — activate subscription
    DeveloperSubscription.objects.filter(
        user=request.user,
        status__in=['active', 'trial']
    ).update(status='cancelled')

    DeveloperSubscription.objects.create(
        user=request.user,
        plan=plan,
        status=DeveloperSubscription.Status.ACTIVE,
        current_period_start=timezone.now(),
        current_period_end=timezone.now() + timezone.timedelta(days=30),
        payment_tx_ref=tx_ref,
    )

    _sync_profile_commission_rate(request.user, plan)

    BankTransaction.objects.create(
        user=request.user,
        transaction_type='payment',
        amount=plan.price_monthly,
        counterpart_label=f'Developer subscription — {plan.name}',
        status='completed',
    )

    del request.session['subscription_plan_slug']
    messages.success(request, f'Payment successful! You are now subscribed to {plan.name}.')
    return redirect('developer_subscription')


@developer_required
def subscription_status(request):
    """View current subscription status."""
    subscription = DeveloperSubscription.objects.filter(
        user=request.user
    ).select_related('plan').order_by('-created_at').first()

    context = {'subscription': subscription}
    return render(request, 'developer/subscription.html', context)


@developer_required
@require_POST
def cancel_subscription(request):
    """Cancel the current subscription."""
    subscription = DeveloperSubscription.objects.filter(
        user=request.user,
        status__in=['active', 'trial']
    ).first()

    if subscription:
        subscription.status = DeveloperSubscription.Status.CANCELLED
        subscription.auto_renew = False
        subscription.save()
        messages.success(request, 'Your subscription has been cancelled.')
    else:
        messages.error(request, 'No active subscription found.')

    return redirect('developer_subscription')
