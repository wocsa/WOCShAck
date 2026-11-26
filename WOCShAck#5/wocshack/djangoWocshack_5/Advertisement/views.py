"""
Advertisement module views.

All views follow FBV patterns from Shopping/views.py:
- Proper authentication via @login_required
- Owner-only access guards with get_object_or_404
- is_staff checks for admin views
- CSRF protection via Django middleware
"""
import time

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Count, Q
from django.core.files.uploadedfile import InMemoryUploadedFile

from .models import Advertisement, AdImpression, AdClick, AdvertisementImage, ZONE_RATE_PER_DAY


# =============================================================================
# HELPERS
# =============================================================================

def get_client_ip(request):
    """
    Get client IP address.
    Copied from Forum/views.py pattern.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log_impression(ad, request, zone=''):
    """
    Create an AdImpression record for the given ad.
    Pass the zone slug so stats remain accurate for "All Zones" ads.
    """
    AdImpression.objects.create(
        advertisement=ad,
        user=request.user if request.user.is_authenticated else None,
        ip_address=get_client_ip(request),
        zone=zone,
    )


def _try_bank_payment(advertiser_user_id, amount):
    """
    Transfer `amount` Neuros from the advertiser's bank
    account to the platform admin account (user_id=1).

    Returns (success: bool, tx_ref: str, error_msg: str)
    Uses Bank/Utils/client.py via make_connection().
    """
    try:
        import sys
        import os
        # Import path is relative to djangoWocshack_5 package root
        from Bank.Utils.client import make_connection
        cli, sid = make_connection()
        if not cli or not sid:
            return False, '', 'Banking server is unavailable. Please try again later.'

        response = cli.transaction(
            sid,
            from_user=advertiser_user_id,
            to_user=1,            # Platform admin account
            amount=float(amount),
        )
        time.sleep(0.5)
        cli.close_session(sid)
        cli.close()

        if isinstance(response, dict) and response.get('status') == 'success':
            tx_ref = str(response.get('transaction_id', response.get('id', '')))
            return True, tx_ref, ''

        # Parse error messages from banking backend
        error = 'Payment failed.'
        if isinstance(response, dict):
            msg = response.get('message', response.get('error', ''))
            if msg:
                error = str(msg)
        return False, '', error

    except Exception as exc:
        return False, '', f'Banking error: {exc}'


def _validate_image_upload(file_obj):
    """
    Validate uploaded image: max 5 MB, allowed types.
    Returns error string or None if valid.
    """
    MAX_SIZE = 5 * 1024 * 1024  # 5 MB
    ALLOWED_CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

    if file_obj.size > MAX_SIZE:
        return 'Image must be smaller than 5 MB.'
    content_type = getattr(file_obj, 'content_type', '')
    if content_type not in ALLOWED_CONTENT_TYPES:
        return 'Only JPG, PNG, GIF, and WebP images are allowed.'
    return None


def _parse_date(date_str, end_of_day=False):
    """Parse a date string ('YYYY-MM-DD') into a timezone-aware datetime."""
    if not date_str:
        return None
    from django.utils.dateparse import parse_datetime, parse_date
    import datetime
    parsed = parse_datetime(date_str)
    if parsed:
        return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
    parsed_date = parse_date(date_str)
    if parsed_date:
        t = datetime.time.max if end_of_day else datetime.time.min
        return timezone.make_aware(
            datetime.datetime.combine(parsed_date, t)
        )
    return None


# =============================================================================
# PUBLIC VIEWS
# =============================================================================

def advertisement_index(request):
    """
    Landing page explaining the ad platform with pricing table and call-to-action.
    """
    return render(request, 'advertisement/index.html', {
        'rate_table': ZONE_RATE_PER_DAY,
        'placement_choices': Advertisement.PlacementZone.choices,
    })


# =============================================================================
# ADVERTISER VIEWS (login required)
# =============================================================================

@login_required
def create_advertisement(request):
    """
    Form to create a new advertisement.
    Handles multi-image uploads and markdown body.
    """
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()[:200]
        body = request.POST.get('body', '').strip()[:2000]
        image_url = request.POST.get('image_url', '').strip()[:500]
        target_url = request.POST.get('target_url', '').strip()[:500]
        placement_zone = request.POST.get('placement_zone', '')
        start_date_str = request.POST.get('start_date', '').strip()
        end_date_str = request.POST.get('end_date', '').strip()

        errors = []

        if not title:
            errors.append('Title is required.')
        if not body:
            errors.append('Ad body text is required.')
        if not target_url:
            errors.append('Target URL is required.')

        valid_zones = [z[0] for z in Advertisement.PlacementZone.choices]
        if placement_zone not in valid_zones:
            errors.append('Please select a valid placement zone.')

        start_date = timezone.now()
        parsed_start = _parse_date(start_date_str)
        if parsed_start:
            start_date = parsed_start

        end_date = _parse_date(end_date_str, end_of_day=True)

        now = timezone.now()
        if parsed_start and parsed_start.date() < now.date():
            errors.append('Start date cannot be in the past.')
        if end_date and start_date and end_date.date() < start_date.date():
            errors.append('End date cannot be before the start date.')

        # Validate uploaded images
        uploaded_images = request.FILES.getlist('images')
        image_errors = []
        for f in uploaded_images:
            err = _validate_image_upload(f)
            if err:
                image_errors.append(f'{f.name}: {err}')
        errors.extend(image_errors)

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'advertisement/create.html', {
                'form_data': request.POST,
                'placement_choices': Advertisement.PlacementZone.choices,
                'rate_table': ZONE_RATE_PER_DAY,
            })

        ad = Advertisement.objects.create(
            title=title,
            body=body,
            image_url=image_url,
            target_url=target_url,
            advertiser=request.user,
            placement_zone=placement_zone,
            status=Advertisement.Status.PENDING,
            start_date=start_date,
            end_date=end_date,
        )

        # Save uploaded images
        for idx, f in enumerate(uploaded_images):
            AdvertisementImage.objects.create(
                advertisement=ad,
                image=f,
                order=idx,
            )

        messages.success(request, 'Advertisement submitted for review.')
        return redirect('advertisement_detail', ad_id=ad.id)

    return render(request, 'advertisement/create.html', {
        'form_data': {},
        'placement_choices': Advertisement.PlacementZone.choices,
        'rate_table': ZONE_RATE_PER_DAY,
    })


@login_required
def advertiser_dashboard(request):
    """
    List the current user's ads with impression/click stats.
    """
    ads = Advertisement.objects.filter(advertiser=request.user).annotate(
        impression_count=Count('impressions'),
        click_count=Count('clicks'),
    ).order_by('-created_at')

    # Compute CTR for each ad in Python to avoid division-by-zero
    for ad in ads:
        if ad.impression_count > 0:
            ad.ctr = round((ad.click_count / ad.impression_count) * 100, 2)
        else:
            ad.ctr = 0.0

    return render(request, 'advertisement/dashboard.html', {'my_ads': ads})


@login_required
def advertisement_detail(request, ad_id):
    """
    Owner-only detail view for a single ad.
    """
    ad = get_object_or_404(Advertisement, id=ad_id, advertiser=request.user)
    impression_count = ad.impressions.count()
    click_count = ad.clicks.count()
    ctr = round((click_count / impression_count) * 100, 2) if impression_count else 0.0
    ad_images = ad.images.order_by('order', 'uploaded_at')
    cost, days = ad.compute_cost()

    return render(request, 'advertisement/detail.html', {
        'ad': ad,
        'impression_count': impression_count,
        'click_count': click_count,
        'ctr': ctr,
        'ad_images': ad_images,
        'projected_cost': cost,
        'projected_days': days,
    })


@login_required
def edit_advertisement(request, ad_id):
    """
    Edit an ad — only allowed if status is pending or rejected.
    Only the owner can edit. Supports replacing images.
    """
    ad = get_object_or_404(Advertisement, id=ad_id, advertiser=request.user)

    if ad.status not in (Advertisement.Status.PENDING, Advertisement.Status.REJECTED):
        messages.error(request, 'Only pending or rejected ads can be edited.')
        return redirect('advertisement_detail', ad_id=ad_id)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()[:200]
        body = request.POST.get('body', '').strip()[:2000]
        image_url = request.POST.get('image_url', '').strip()[:500]
        target_url = request.POST.get('target_url', '').strip()[:500]
        placement_zone = request.POST.get('placement_zone', '')
        end_date_str = request.POST.get('end_date', '').strip()
        delete_image_ids = request.POST.getlist('delete_images')

        errors = []
        if not title:
            errors.append('Title is required.')
        if not body:
            errors.append('Ad body text is required.')
        if not target_url:
            errors.append('Target URL is required.')

        valid_zones = [z[0] for z in Advertisement.PlacementZone.choices]
        if placement_zone not in valid_zones:
            errors.append('Please select a valid placement zone.')

        parsed_end_date = _parse_date(end_date_str, end_of_day=True)
        if parsed_end_date and ad.start_date and parsed_end_date.date() < ad.start_date.date():
            errors.append('End date cannot be before the start date.')

        uploaded_images = request.FILES.getlist('images')
        for f in uploaded_images:
            err = _validate_image_upload(f)
            if err:
                errors.append(f'{f.name}: {err}')

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'advertisement/edit.html', {
                'ad': ad,
                'placement_choices': Advertisement.PlacementZone.choices,
                'ad_images': ad.images.order_by('order', 'uploaded_at'),
                'rate_table': ZONE_RATE_PER_DAY,
            })

        ad.title = title
        ad.body = body
        ad.image_url = image_url
        ad.target_url = target_url
        ad.placement_zone = placement_zone
        ad.end_date = parsed_end_date
        # Reset to pending after edit so staff re-reviews
        ad.status = Advertisement.Status.PENDING
        ad.rejection_reason = ''
        ad.save()

        # Delete images marked for removal (owner-scoped, safe)
        if delete_image_ids:
            ad.images.filter(id__in=delete_image_ids).delete()

        # Add new uploaded images
        existing_count = ad.images.count()
        for idx, f in enumerate(uploaded_images):
            AdvertisementImage.objects.create(
                advertisement=ad,
                image=f,
                order=existing_count + idx,
            )

        messages.success(request, 'Advertisement updated and resubmitted for review.')
        return redirect('advertisement_detail', ad_id=ad_id)

    return render(request, 'advertisement/edit.html', {
        'ad': ad,
        'placement_choices': Advertisement.PlacementZone.choices,
        'ad_images': ad.images.order_by('order', 'uploaded_at'),
        'rate_table': ZONE_RATE_PER_DAY,
    })


@login_required
@require_POST
def reorder_images(request, ad_id):
    """
    AJAX endpoint to reorder carousel images.
    POST body: image_ids[]  (ordered list of AdvertisementImage UUIDs)
    """
    ad = get_object_or_404(Advertisement, id=ad_id, advertiser=request.user)
    image_ids = request.POST.getlist('image_ids[]')
    for order, img_id in enumerate(image_ids):
        ad.images.filter(id=img_id).update(order=order)
    return JsonResponse({'status': 'ok'})


@login_required
def ad_stats(request, ad_id):
    """
    Owner-only stats page for a single ad.
    Shows impression and click breakdown over time, including per-zone stats.
    """
    ad = get_object_or_404(Advertisement, id=ad_id, advertiser=request.user)

    impressions = ad.impressions.order_by('-timestamp')[:50]
    clicks = ad.clicks.order_by('-timestamp')[:50]

    total_impressions = ad.impressions.count()
    total_clicks = ad.clicks.count()
    ctr = round((total_clicks / total_impressions) * 100, 2) if total_impressions else 0.0

    # Per-zone impression counts (relevant for "All Zones" ads)
    from django.db.models import Count as DCount
    zone_breakdown = (
        ad.impressions
        .values('zone')
        .annotate(count=DCount('id'))
        .order_by('-count')
    )

    return render(request, 'advertisement/ad_stats.html', {
        'ad': ad,
        'impressions': impressions,
        'clicks': clicks,
        'total_impressions': total_impressions,
        'total_clicks': total_clicks,
        'ctr': ctr,
        'zone_breakdown': zone_breakdown,
    })


# =============================================================================
# CLICK TRACKING (public POST)
# =============================================================================

@require_POST
def record_click(request, ad_id):
    """
    Record an ad click then redirect to target_url.
    Only active ads accept clicks.
    """
    ad = get_object_or_404(Advertisement, id=ad_id)

    if ad.is_currently_active():
        AdClick.objects.create(
            advertisement=ad,
            user=request.user if request.user.is_authenticated else None,
            ip_address=get_client_ip(request),
        )

    # Safe redirect: only redirect to the ad's own stored target_url
    return redirect(ad.target_url)


# =============================================================================
# STAFF ADMIN VIEWS
# =============================================================================

@login_required
def admin_pending_ads(request):
    """
    Staff-only view of pending advertisements.
    Displays projected cost for each ad so staff can review billing before approval.
    """
    if not request.user.is_staff:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('advertisement_index')

    pending_ads = Advertisement.objects.filter(
        status=Advertisement.Status.PENDING
    ).select_related('advertiser').order_by('-created_at')

    # Attach projected cost to each ad
    for ad in pending_ads:
        cost, days = ad.compute_cost()
        ad.projected_cost = cost
        ad.projected_days = days
        ad.rate_per_day = ZONE_RATE_PER_DAY.get(ad.placement_zone, 0)

    return render(request, 'advertisement/admin_pending.html', {
        'pending_ads': pending_ads,
    })


@login_required
@require_POST
def approve_ad(request, ad_id):
    """
    Staff-only: approve a pending advertisement.
    Sets status to 'approved'. The advertiser then pays via the activate_ad page.
    """
    if not request.user.is_staff:
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('advertisement_index')

    ad = get_object_or_404(Advertisement, id=ad_id)
    cost, days = ad.compute_cost()

    ad.status = Advertisement.Status.APPROVED
    ad.reviewed_by = request.user
    ad.reviewed_at = timezone.now()
    ad.rejection_reason = ''
    ad.save()

    cost_info = f' Projected cost: {cost} Neuros for {days} day(s).' if cost else ''
    messages.success(
        request,
        f'"{ad.title}" approved.{cost_info} The advertiser must now activate it via the payment page.'
    )
    return redirect('admin_pending_ads')


@login_required
def activate_ad(request, ad_id):
    """
    Advertiser payment page to activate an approved advertisement.
    Mirrors the Shopping payment view: dual authentication (password + PIN),
    card selection, and balance check before charging the VRC banking backend.
    """
    ad = get_object_or_404(Advertisement, id=ad_id, advertiser=request.user)

    if ad.status != Advertisement.Status.APPROVED:
        messages.error(request, 'Only approved ads can be activated.')
        return redirect('advertisement_detail', ad_id=ad_id)

    cost, days = ad.compute_cost()
    rate_per_day = ZONE_RATE_PER_DAY.get(ad.placement_zone, 0)

    from decimal import Decimal
    from Bank.Utils.external_calls import get_user_balance, verify_user_pin
    from Bank.models import BankCard

    def _build_ctx(password='', pin='', first_name='', last_name='', email='', phone='', card_number=''):
        balance = get_user_balance(request.user.id)
        balance_after = None
        if balance is not None and cost is not None:
            try:
                balance_after = Decimal(str(balance)) - cost
            except Exception:
                pass
        user_cards = BankCard.objects.filter(user=request.user).exclude(status='cancelled')
        return {
            'ad': ad,
            'cost': cost,
            'days': days,
            'rate_per_day': rate_per_day,
            'balance': balance,
            'balance_after': balance_after,
            'user_cards': user_cards,
            'first_name': first_name or request.user.first_name,
            'last_name': last_name or request.user.last_name,
            'email': email or request.user.email,
            'phone': phone,
            'card_number': card_number,
        }

    if request.method == 'POST':
        password   = request.POST.get('password', '').strip()
        pin        = request.POST.get('pin', '').strip()
        card_number = request.POST.get('card_number', '').strip()[:16]
        first_name = request.POST.get('first_name', '').strip()[:100]
        last_name  = request.POST.get('name', '').strip()[:100]
        email      = request.POST.get('email', '').strip()[:254]
        phone      = request.POST.get('phone', '').strip()[:20]

        ctx = _build_ctx(password, pin, first_name, last_name, email, phone, card_number)

        if cost is not None and cost > 0:
            # All auth fields required when there is a cost
            if not password or not pin or not card_number:
                messages.error(request, 'Please fill in all required fields (password, PIN, and card).')
                return render(request, 'advertisement/payment.html', ctx)

            # Verify account password
            if not request.user.check_password(password):
                messages.error(request, 'Incorrect account password. Payment authorisation failed.')
                return render(request, 'advertisement/payment.html', ctx)

            # Verify bank PIN
            if not verify_user_pin(request.user.id, pin):
                messages.error(request, 'Incorrect bank PIN. Payment authorisation failed.')
                return render(request, 'advertisement/payment.html', ctx)

            # Verify card belongs to the user
            try:
                card = BankCard.objects.get(user=request.user, payment_number=card_number)
            except BankCard.DoesNotExist:
                messages.error(request, 'Invalid card number.')
                return render(request, 'advertisement/payment.html', ctx)

            if card.status == 'frozen':
                messages.error(request, 'This card is frozen. Please unfreeze it in the Banking Dashboard first.')
                return render(request, 'advertisement/payment.html', ctx)

            # Verify sufficient balance
            balance = get_user_balance(request.user.id)
            if balance is None:
                messages.error(request, 'Could not verify your balance. Please try again.')
                return render(request, 'advertisement/payment.html', ctx)
            if cost > Decimal(str(balance)):
                messages.error(request, f'Insufficient funds. Your balance is {balance} Neuros but the campaign costs {cost} Neuros.')
                return render(request, 'advertisement/payment.html', ctx)

            # Process payment
            success, tx_ref, error_msg = _try_bank_payment(
                advertiser_user_id=request.user.id,
                amount=cost,
            )
            if not success:
                messages.error(request, f'Payment failed: {error_msg}')
                return render(request, 'advertisement/payment.html', ctx)

            ad.cost_neuros = cost
            ad.payment_tx_ref = tx_ref

        ad.status = Advertisement.Status.ACTIVE
        ad.save()
        messages.success(request, f'"{ad.title}" is now live!')
        return redirect('advertisement_detail', ad_id=ad_id)

    return render(request, 'advertisement/payment.html', _build_ctx())


@login_required
@require_POST
def reject_ad(request, ad_id):
    """
    Staff-only: reject a pending advertisement with a reason.
    """
    if not request.user.is_staff:
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('advertisement_index')

    ad = get_object_or_404(Advertisement, id=ad_id)
    rejection_reason = request.POST.get('rejection_reason', '').strip()[:1000]

    ad.status = Advertisement.Status.REJECTED
    ad.reviewed_by = request.user
    ad.reviewed_at = timezone.now()
    ad.rejection_reason = rejection_reason
    ad.save()

    messages.success(request, f'Advertisement "{ad.title}" rejected.')
    return redirect('admin_pending_ads')


# =============================================================================
# STAFF ADMIN — EXTENDED PANEL
# =============================================================================

@login_required
def admin_dashboard(request):
    """
    Staff-only: overview dashboard with status counts, impression/click totals
    (last 30 days), and per-zone revenue estimates for approved/active ads.
    """
    if not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('advertisement_index')

    from django.core.paginator import Paginator
    from django.db.models import Sum
    import decimal

    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)

    # --- Status counts ---
    status_qs = (
        Advertisement.objects
        .values('status')
        .annotate(count=Count('id'))
    )
    status_counts = {row['status']: row['count'] for row in status_qs}

    pending_count   = status_counts.get(Advertisement.Status.PENDING,  0)
    approved_count  = status_counts.get(Advertisement.Status.APPROVED, 0)
    rejected_count  = status_counts.get(Advertisement.Status.REJECTED, 0)
    active_count    = status_counts.get(Advertisement.Status.ACTIVE,   0)
    expired_count   = status_counts.get(Advertisement.Status.EXPIRED,  0)
    total_count     = Advertisement.objects.count()

    # --- Impression / click totals (last 30 days) ---
    total_impressions = AdImpression.objects.filter(
        timestamp__gte=thirty_days_ago
    ).count()
    total_clicks = AdClick.objects.filter(
        timestamp__gte=thirty_days_ago
    ).count()

    # --- Revenue estimate by zone (sum cost_neuros for approved + active ads) ---
    revenue_qs = (
        Advertisement.objects
        .filter(
            status__in=[Advertisement.Status.APPROVED, Advertisement.Status.ACTIVE],
            cost_neuros__isnull=False,
        )
        .values('placement_zone')
        .annotate(revenue=Sum('cost_neuros'))
        .order_by('placement_zone')
    )
    zone_revenue = [
        {
            'zone': row['placement_zone'],
            'zone_display': dict(Advertisement.PlacementZone.choices).get(
                row['placement_zone'], row['placement_zone']
            ),
            'revenue': row['revenue'] or decimal.Decimal('0'),
        }
        for row in revenue_qs
    ]
    total_revenue = sum(z['revenue'] for z in zone_revenue)

    return render(request, 'advertisement/admin_dashboard.html', {
        'pending_count':    pending_count,
        'approved_count':   approved_count,
        'rejected_count':   rejected_count,
        'active_count':     active_count,
        'expired_count':    expired_count,
        'total_count':      total_count,
        'total_impressions': total_impressions,
        'total_clicks':     total_clicks,
        'zone_revenue':     zone_revenue,
        'total_revenue':    total_revenue,
    })


@login_required
def admin_all_ads(request):
    """
    Staff-only: paginated list of all advertisements with filters for status,
    placement zone, and a keyword search (advertiser username or ad title).
    """
    if not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('advertisement_index')

    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    ads = Advertisement.objects.select_related('advertiser').order_by('-created_at')

    # --- Filtering ---
    filter_status = request.GET.get('status', '').strip()
    filter_zone   = request.GET.get('zone', '').strip()
    search        = request.GET.get('search', '').strip()

    if filter_status:
        ads = ads.filter(status=filter_status)
    if filter_zone:
        ads = ads.filter(placement_zone=filter_zone)
    if search:
        ads = ads.filter(
            Q(title__icontains=search) | Q(advertiser__username__icontains=search)
        )

    # --- Pagination (20/page) ---
    paginator = Paginator(ads, 20)
    page_num  = request.GET.get('page')
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return render(request, 'advertisement/admin_all_ads.html', {
        'page_obj':      page_obj,
        'filter_status': filter_status,
        'filter_zone':   filter_zone,
        'search':        search,
        'status_choices': Advertisement.Status.choices,
        'zone_choices':   Advertisement.PlacementZone.choices,
    })


@login_required
@require_POST
def admin_suspend_ad(request, ad_id):
    """
    Staff-only: suspend an advertisement by setting its status to REJECTED
    and marking the rejection_reason as '[Suspended by admin]'.
    """
    if not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('advertisement_index')

    ad = get_object_or_404(Advertisement, id=ad_id)
    ad.status = Advertisement.Status.REJECTED
    ad.rejection_reason = '[Suspended by admin]'
    ad.reviewed_by  = request.user
    ad.reviewed_at  = timezone.now()
    ad.save()

    messages.success(request, f'Advertisement "{ad.title}" has been suspended.')
    return redirect('advertisement_admin_all')


def ad_preview(request):
    from django.template import Template, Context
    from django.http import HttpResponse as _HttpResponse
    template_str = request.GET.get('template', '<p>No ad provided</p>')
    t = Template(template_str)
    c = Context({'request': request})
    return _HttpResponse(t.render(c))


@login_required
@require_POST
def admin_unsuspend_ad(request, ad_id):
    """
    Staff-only: lift a suspension by restoring the ad's status to APPROVED.
    Clears the rejection reason set during suspension.
    """
    if not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('advertisement_index')

    ad = get_object_or_404(Advertisement, id=ad_id)
    ad.status = Advertisement.Status.APPROVED
    ad.rejection_reason = ''
    ad.reviewed_by  = request.user
    ad.reviewed_at  = timezone.now()
    ad.save()

    messages.success(request, f'Advertisement "{ad.title}" has been unsuspended (set to Approved).')
    return redirect('advertisement_admin_all')
