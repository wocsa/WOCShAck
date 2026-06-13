"""
Developer admin moderation panel views.
Staff-only views for managing payouts, listings, and subscriptions.
"""
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Q, Subquery, OuterRef, DecimalField
from django.db.models.functions import Coalesce
from django import forms

from Api.models import Css as ApiCss
from Shopping.models import Coupon as ShoppingCoupon
from Bank.Utils.external_calls import add_amount
from Bank.models import Transaction as BankTransaction

from Account.models import PurchasedFeature

from .models import (
    DeveloperProfile,
    DeveloperPlan,
    DeveloperSubscription,
    CssProject,
    CssListing,
    Payout,
    DeveloperBalance,
    Promotion,
)


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class DeveloperPlanForm(forms.ModelForm):
    class Meta:
        model = DeveloperPlan
        fields = [
            'name', 'slug', 'price_monthly', 'price_yearly',
            'css_limit', 'api_calls_limit', 'commission_rate',
            'features', 'is_active',
        ]


# ---------------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------------

@login_required
@require_GET
def admin_dashboard(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    pending_payouts = Payout.objects.filter(status=Payout.Status.PENDING).count()
    active_subscriptions = DeveloperSubscription.objects.filter(
        status__in=[DeveloperSubscription.Status.ACTIVE, DeveloperSubscription.Status.TRIAL]
    ).values('user').distinct().count()
    total_developers = PurchasedFeature.objects.filter(
        feature_type=PurchasedFeature.FEATURE_DEVELOPER_ROLE,
        is_active=True,
    ).values('user').distinct().count()
    total_listings = CssListing.objects.count()

    context = {
        'pending_payouts': pending_payouts,
        'active_subscriptions': active_subscriptions,
        'total_developers': total_developers,
        'total_listings': total_listings,
    }
    return render(request, 'developer/admin/dashboard.html', context)


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------

@login_required
@require_GET
def payout_list(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    qs = Payout.objects.select_related('developer', 'method').order_by('-requested_at')

    status_filter = request.GET.get('status', '').strip()
    search = request.GET.get('search', '').strip()

    if status_filter in [s.value for s in Payout.Status]:
        qs = qs.filter(status=status_filter)

    if search:
        qs = qs.filter(developer__username__icontains=search)

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search': search,
        'status_choices': Payout.Status.choices,
    }
    return render(request, 'developer/admin/payout_list.html', context)


@login_required
def payout_review(request, payout_id):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    payout = get_object_or_404(Payout, id=payout_id)
    balance = DeveloperBalance.objects.filter(developer=payout.developer).first()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve':
            if not balance or balance.pending < payout.amount:
                messages.error(request, "Insufficient pending balance to approve this payout.")
                return redirect('developer_admin_payout_review', payout_id=payout.id)

            # Transfer full amount to developer's bank account
            bank_resp = add_amount(payout.developer.id, float(payout.amount))
            if not isinstance(bank_resp, dict) or bank_resp.get('status') != 'success':
                error_detail = bank_resp.get('error', 'Unknown error') if isinstance(bank_resp, dict) else 'Bank unreachable'
                
                # Return funds from pending back to available
                if balance:
                    balance.pending -= payout.amount
                    balance.available += payout.amount
                    balance.save()
                    
                payout.status = Payout.Status.FAILED
                payout.admin_notes = f"Bank transfer failed: {error_detail}"
                payout.processed_at = timezone.now()
                payout.save()
                messages.error(request, f"Payout #{str(payout.id)[:8]} failed: bank transfer error.")
                return redirect('developer_admin_payout_list')

            # Bank transfer succeeded — update balance and payout
            balance.pending -= payout.amount
            balance.total_paid += payout.amount
            balance.save()

            tx_ref = bank_resp.get('tx_ref', '')
            if tx_ref:
                payout.tx_ref = tx_ref
            payout.status = Payout.Status.COMPLETED
            payout.processed_at = timezone.now()
            payout.save()

            BankTransaction.objects.create(
                user=payout.developer,
                transaction_type='deposit',
                amount=payout.amount,
                counterpart_label='Developer Payout',
                note=f'Payout #{str(payout.id)[:8]}',
                status='completed',
            )

            messages.success(request, f"Payout #{str(payout.id)[:8]} approved and {payout.amount} NE transferred.")
            return redirect('developer_admin_payout_list')

        elif action == 'reject':
            rejection_reason = request.POST.get('rejection_reason', '').strip()

            # Return funds from pending back to available
            if balance:
                balance.pending -= payout.amount
                balance.available += payout.amount
                balance.save()

            payout.status = Payout.Status.FAILED
            payout.admin_notes = rejection_reason
            payout.processed_at = timezone.now()
            payout.save()
            messages.success(request, f"Payout #{str(payout.id)[:8]} has been rejected.")
            return redirect('developer_admin_payout_list')

        else:
            messages.error(request, "Invalid action.")

    context = {
        'payout': payout,
        'balance': balance,
    }
    return render(request, 'developer/admin/payout_review.html', context)


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

@login_required
@require_GET
def listing_list(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    qs = CssListing.objects.select_related('developer', 'project').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(developer__username__icontains=search) |
            Q(title__icontains=search)
        )

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'published_status': CssListing.Status.PUBLISHED,
        'rejected_status': CssListing.Status.REJECTED,
    }
    return render(request, 'developer/admin/listing_list.html', context)


@login_required
@require_POST
def listing_suspend(request, listing_id):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    listing = get_object_or_404(CssListing, id=listing_id)

    api_css = ApiCss.objects.filter(name=listing.title, creator=listing.developer).first()

    if listing.status == CssListing.Status.PUBLISHED:
        listing.status = CssListing.Status.REJECTED
        listing.rejection_reason = "Suspended by admin."
        listing.save()
        if api_css:
            api_css.is_active = False
            api_css.save()
        messages.success(request, f'Listing "{listing.title or str(listing.id)[:8]}" has been suspended.')
    else:
        listing.status = CssListing.Status.PUBLISHED
        listing.rejection_reason = ''
        listing.published_at = timezone.now()
        listing.save()
        if api_css:
            api_css.is_active = True
            api_css.save()
        messages.success(request, f'Listing "{listing.title}" has been restored.')

    return redirect('developer_admin_listing_list')


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

@login_required
@require_GET
def subscription_list(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    qs = DeveloperSubscription.objects.select_related('user', 'plan').order_by('-created_at')

    status_filter = request.GET.get('status', '').strip()
    search = request.GET.get('search', '').strip()

    if status_filter in [s.value for s in DeveloperSubscription.Status]:
        qs = qs.filter(status=status_filter)

    if search:
        qs = qs.filter(user__username__icontains=search)

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search': search,
        'status_choices': DeveloperSubscription.Status.choices,
    }
    return render(request, 'developer/admin/subscription_list.html', context)


# ---------------------------------------------------------------------------
# Developer Profiles
# ---------------------------------------------------------------------------

@login_required
@require_GET
def developer_list(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    # Ensure every user with the developer role has a profile entry
    from django.contrib.auth.models import User
    dev_users = User.objects.filter(
        purchased_features__feature_type=PurchasedFeature.FEATURE_DEVELOPER_ROLE,
        purchased_features__is_active=True,
    )
    for u in dev_users:
        profile, created = DeveloperProfile.objects.get_or_create(
            user=u,
            defaults={'display_name': u.username, 'is_verified': True, 'verified_at': timezone.now()},
        )
        if not created and not profile.is_verified:
            profile.is_verified = True
            profile.verified_at = timezone.now()
            profile.save(update_fields=['is_verified', 'verified_at'])

    active_plan_commission = Subquery(
        DeveloperSubscription.objects.filter(
            user=OuterRef('user'),
            status__in=[DeveloperSubscription.Status.ACTIVE, DeveloperSubscription.Status.TRIAL],
        ).select_related('plan').values('plan__commission_rate')[:1],
        output_field=DecimalField(max_digits=4, decimal_places=2),
    )

    qs = DeveloperProfile.objects.filter(
        user__in=dev_users
    ).select_related('user').annotate(
        plan_commission_rate=active_plan_commission,
    ).order_by('user__username')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(user__username__icontains=search) |
            Q(display_name__icontains=search)
        )

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
    }
    return render(request, 'developer/admin/developer_list.html', context)


# ---------------------------------------------------------------------------
# Developer Plans
# ---------------------------------------------------------------------------

@login_required
@require_GET
def plan_list(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    qs = DeveloperPlan.objects.order_by('price_monthly')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(name__icontains=search)

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
    }
    return render(request, 'developer/admin/plan_list.html', context)


@login_required
def plan_create(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    if request.method == 'POST':
        form = DeveloperPlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f'Plan "{plan.name}" created.')
            return redirect('developer_admin_plan_list')
    else:
        form = DeveloperPlanForm()

    return render(request, 'developer/admin/plan_edit.html', {'form': form, 'plan': None})


@login_required
def plan_edit(request, plan_id):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    plan = get_object_or_404(DeveloperPlan, pk=plan_id)

    if request.method == 'POST':
        form = DeveloperPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, f'Plan "{plan.name}" updated.')
            return redirect('developer_admin_plan_list')
    else:
        form = DeveloperPlanForm(instance=plan)

    return render(request, 'developer/admin/plan_edit.html', {'form': form, 'plan': plan})


# ---------------------------------------------------------------------------
# Promotions
# ---------------------------------------------------------------------------

@login_required
@require_GET
def promotion_list(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    qs = Promotion.objects.select_related('listing').order_by('-created_at')
    coupons_qs = ShoppingCoupon.objects.select_related('developer').filter(
        developer__isnull=False
    ).order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(code__icontains=search)
        coupons_qs = coupons_qs.filter(
            Q(code__icontains=search) | Q(developer__username__icontains=search)
        )

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'shop_coupons': coupons_qs,
    }
    return render(request, 'developer/admin/promotion_list.html', context)


@login_required
@require_POST
def promotion_revoke(request, promotion_id):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    promotion = get_object_or_404(Promotion, id=promotion_id)
    promotion.is_active = False
    promotion.save()
    messages.success(request, f"Promotion '{promotion.code}' has been revoked.")
    return redirect('developer_admin_promotion_list')


@login_required
@require_POST
def coupon_revoke(request, coupon_id):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    coupon = get_object_or_404(ShoppingCoupon, id=coupon_id, developer__isnull=False)
    coupon.is_active = False
    coupon.save()
    messages.success(request, f"Coupon '{coupon.code}' has been revoked.")
    return redirect('developer_admin_promotion_list')


# ---------------------------------------------------------------------------
# CSS Projects
# ---------------------------------------------------------------------------

@login_required
@require_GET
def project_list(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('/')

    qs = CssProject.objects.select_related('developer').order_by('-updated_at')

    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()

    if search:
        qs = qs.filter(
            Q(developer__username__icontains=search) |
            Q(name__icontains=search)
        )

    if status_filter in [s.value for s in CssProject.Status]:
        qs = qs.filter(status=status_filter)

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'status_filter': status_filter,
        'status_choices': CssProject.Status.choices,
    }
    return render(request, 'developer/admin/project_list.html', context)
