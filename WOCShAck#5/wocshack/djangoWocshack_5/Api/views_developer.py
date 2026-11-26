"""
Developer Module API Views.
Exposes developer profile, subscriptions, CSS projects/versions, listings,
analytics, webhooks, payouts, promotions, and CSS utility tools via REST.

All endpoints require the requesting user to have the developer_role feature
purchased (checked by @developer_required).
"""
import json
import re
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.models import User
from .views import api_success, api_error, api_auth_required, paginate_queryset, _check_and_log_api_call, _get_active_subscription
from .models import ApiKey, ApiKeyUsage

from Developer.models import (
    DeveloperProfile,
    DeveloperPlan,
    DeveloperSubscription,
    CssProject,
    CssVersion,
    CssListing,
    PricingTier,
    SaleAnalytics,
    CustomerAnalytics,
    Webhook,
    WebhookDelivery,
    DeveloperBalance,
    PayoutMethod,
    Payout,
    Promotion,
)
from Developer.Utils.plan_limits import get_css_project_limit_error
from Account.models import PurchasedFeature


# ---------------------------------------------------------------------------
# Helper: enforce developer role
# ---------------------------------------------------------------------------

def _require_developer(request):
    """
    Return None if user has developer role and is within API call limits,
    else an api_error response.  Also logs the API call for key-authenticated
    requests so the monthly counter stays accurate.
    """
    if not PurchasedFeature.has_feature(request.user, 'developer_role'):
        return api_error(
            "Developer role required. Purchase the Developer Role from /account/store/.",
            status=403,
        )
    # Enforce monthly API call limit (API-key auth only)
    limit_err = _check_and_log_api_call(request)
    if limit_err:
        return limit_err
    return None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# CSS utility helpers (used by /api/developer/tools/)
# ---------------------------------------------------------------------------

def _minify_css(css):
    css = re.sub(r'/\*[\s\S]*?\*/', '', css)       # strip comments
    css = re.sub(r'\s+', ' ', css)                  # collapse whitespace
    css = re.sub(r'\s*([:;{},>+~])\s*', r'\1', css) # trim around operators
    css = re.sub(r';}', '}', css)                   # remove trailing ;
    return css.strip()


def _beautify_css(css):
    css = _minify_css(css)
    css = re.sub(r'\{', ' {\n    ', css)
    css = re.sub(r';', ';\n    ', css)
    css = re.sub(r'\s*\}\s*', '\n}\n\n', css)
    return css.strip()


def _validate_css(css):
    errors = []
    open_b = css.count('{')
    close_b = css.count('}')
    if open_b != close_b:
        errors.append(f"Unbalanced braces: {open_b} opening vs {close_b} closing.")
    # Check for common syntax issues
    for i, line in enumerate(css.splitlines(), 1):
        stripped = line.strip()
        if stripped and not stripped.startswith('/*') and not stripped.endswith('*/'):
            if ':' in stripped and not stripped.startswith('@') and ';' not in stripped \
                    and '{' not in stripped and '}' not in stripped:
                errors.append(f"Line {i}: property declaration may be missing a semicolon.")
    return errors


_VENDOR_PREFIXES = {
    r'\btransform\b': ['-webkit-transform', '-ms-transform'],
    r'\btransition\b': ['-webkit-transition', '-o-transition'],
    r'\banimation\b': ['-webkit-animation'],
    r'\buser-select\b': ['-webkit-user-select', '-moz-user-select', '-ms-user-select'],
    r'\bbox-shadow\b': ['-webkit-box-shadow'],
    r'\bborder-radius\b': ['-webkit-border-radius'],
    r'\bflex\b': ['-webkit-flex'],
}


def _prefix_css(css):
    result = css
    for prop_re, prefixes in _VENDOR_PREFIXES.items():
        def make_replacement(prefixes=prefixes):
            def replace_fn(m):
                prop = m.group(0)
                prefix_str = ''.join(f'{p}: ' for p in prefixes)
                return prefix_str + prop
            return replace_fn
        result = re.sub(prop_re, make_replacement(), result)
    return result


# ==============================================================================
# Developer Profile
# ==============================================================================

@require_http_methods(["GET", "PATCH"])
@api_auth_required
def profile_view(request):
    """
    GET: Return the current developer's extended profile.
    PATCH: Update profile fields.
    """
    err = _require_developer(request)
    if err:
        return err

    profile, _ = DeveloperProfile.objects.get_or_create(user=request.user)

    if request.method == "GET":
        return api_success(_serialize_dev_profile(profile))

    # PATCH
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    for field in ('display_name', 'tagline', 'website', 'github_url', 'twitter_url'):
        if field in data:
            setattr(profile, field, str(data[field])[:255])

    if 'specialties' in data:
        if isinstance(data['specialties'], list):
            profile.specialties = data['specialties'][:20]

    if 'payout_method' in data:
        profile.payout_method = str(data['payout_method'])[:50]

    profile.save()
    return api_success(_serialize_dev_profile(profile), message="Profile updated.")


@require_http_methods(["GET"])
@api_auth_required
def public_profile_view(request, username):
    """
    GET: Return a developer's public profile.
    """
    target = get_object_or_404(User, username=username)
    try:
        profile = target.developerprofile
    except DeveloperProfile.DoesNotExist:
        return api_error("Developer profile not found.", status=404)

    return api_success({
        'username': target.username,
        'display_name': profile.display_name,
        'tagline': profile.tagline,
        'website': profile.website,
        'github_url': profile.github_url,
        'twitter_url': profile.twitter_url,
        'specialties': profile.specialties,
        'is_verified': profile.is_verified,
        'verified_at': profile.verified_at.isoformat() if profile.verified_at else None,
    })


def _serialize_dev_profile(profile):
    return {
        'display_name': profile.display_name,
        'tagline': profile.tagline,
        'website': profile.website,
        'github_url': profile.github_url,
        'twitter_url': profile.twitter_url,
        'specialties': profile.specialties,
        'commission_rate': float(profile.commission_rate),
        'payout_method': profile.payout_method,
        'is_verified': profile.is_verified,
        'verified_at': profile.verified_at.isoformat() if profile.verified_at else None,
        'created_at': profile.created_at.isoformat() if profile.created_at else None,
    }


# ==============================================================================
# Subscription Plans & Management
# ==============================================================================

@require_http_methods(["GET"])
def plans_view(request):
    """
    GET: List available subscription plans. Public endpoint.
    """
    plans = DeveloperPlan.objects.filter(is_active=True).order_by('price_monthly')
    data = []
    for p in plans:
        data.append({
            'id': str(p.id),
            'name': p.name,
            'slug': p.slug,
            'price_monthly': float(p.price_monthly),
            'price_yearly': float(p.price_yearly),
            'css_limit': p.css_limit,
            'api_calls_limit': p.api_calls_limit,
            'features': p.features,
        })
    return api_success({'plans': data})


@require_http_methods(["GET"])
@api_auth_required
def subscription_view(request):
    """
    GET: Return the current user's subscription status.
    """
    err = _require_developer(request)
    if err:
        return err

    try:
        sub = DeveloperSubscription.objects.select_related('plan').get(
            user=request.user, status__in=('active', 'trial')
        )
        return api_success({
            'plan': sub.plan.name,
            'plan_slug': sub.plan.slug,
            'status': sub.status,
            'auto_renew': sub.auto_renew,
            'current_period_start': sub.current_period_start.isoformat() if sub.current_period_start else None,
            'current_period_end': sub.current_period_end.isoformat() if sub.current_period_end else None,
            'is_active': sub.is_active_subscription,
        })
    except DeveloperSubscription.DoesNotExist:
        return api_success({'status': 'none', 'is_active': False})


@require_http_methods(["POST"])
@api_auth_required
def subscribe_view(request, slug):
    """
    POST: Subscribe to a developer plan. Deducts cost from bank balance.
    """
    err = _require_developer(request)
    if err:
        return err

    plan = get_object_or_404(DeveloperPlan, slug=slug, is_active=True)

    if DeveloperSubscription.objects.filter(
        user=request.user, status__in=('active', 'trial')
    ).exists():
        return api_error("You already have an active subscription.", status=400)

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = {}

    billing = data.get('billing', 'monthly')
    price = plan.price_yearly if billing == 'yearly' else plan.price_monthly

    from Bank.Utils import client as bank_client
    cli, sid = bank_client.make_connection()
    if not cli or not sid:
        return api_error("Banking server unreachable. Please try again later.", status=503)

    payment_ok = False
    try:
        user_resp = cli.get_user(sid, request.user.id)
        if not isinstance(user_resp, dict) or not user_resp.get('success'):
            return api_error("Bank account not found.", status=404)

        balance = Decimal(str(user_resp.get('user', {}).get('balance', 0)))
        if balance < price:
            return api_error(
                f"Insufficient balance. Required: {price} NE, available: {balance} NE.", status=400
            )

        sender_id = user_resp.get('user', {}).get('id')
        result = cli.transaction(sid=sid, from_user=sender_id, to_user=1, amount=float(price))
        if not (isinstance(result, dict) and result.get('status') == 'success'):
            error_msg = result.get('message', 'Payment failed.') if isinstance(result, dict) else 'Payment failed.'
            return api_error(f"Payment failed: {error_msg}", status=400)

        payment_ok = True
    finally:
        try:
            cli.close_session(sid)
            cli.close()
        except Exception:
            pass

    if not payment_ok:
        return api_error("Payment could not be processed.", status=400)

    # Re-check for an active subscription atomically to prevent TOCTOU double-charge.
    if DeveloperSubscription.objects.filter(
        user=request.user, status__in=('active', 'trial')
    ).exists():
        return api_error("Subscription already activated (concurrent request detected).", status=400)

    now = timezone.now()
    end = now.replace(year=now.year + 1) if billing == 'yearly' else (
        now.replace(month=now.month + 1) if now.month < 12 else now.replace(year=now.year + 1, month=1)
    )

    sub = DeveloperSubscription.objects.create(
        user=request.user,
        plan=plan,
        status='active',
        auto_renew=True,
        current_period_start=now,
        current_period_end=end,
    )

    # Sync profile commission_rate with the new plan's rate
    try:
        profile = DeveloperProfile.objects.get(user=request.user)
        if profile.commission_rate != plan.commission_rate:
            profile.commission_rate = plan.commission_rate
            profile.save(update_fields=['commission_rate'])
    except DeveloperProfile.DoesNotExist:
        pass

    return api_success({
        'plan': plan.name,
        'status': sub.status,
        'current_period_end': sub.current_period_end.isoformat(),
    }, message=f"Subscribed to {plan.name} plan.", status=201)


@require_http_methods(["DELETE"])
@api_auth_required
def cancel_subscription_view(request):
    """
    DELETE: Cancel the active subscription (takes effect at period end).
    """
    err = _require_developer(request)
    if err:
        return err

    try:
        sub = DeveloperSubscription.objects.get(
            user=request.user, status__in=('active', 'trial')
        )
    except DeveloperSubscription.DoesNotExist:
        return api_error("No active subscription found.", status=404)

    sub.status = 'cancelled'
    sub.auto_renew = False
    sub.save()
    return api_success({
        'status': 'cancelled',
        'active_until': sub.current_period_end.isoformat() if sub.current_period_end else None,
    }, message="Subscription cancelled. Access continues until the current period ends.")


# ==============================================================================
# CSS Projects
# ==============================================================================

@require_http_methods(["GET", "POST"])
@api_auth_required
def projects_view(request):
    """
    GET: List the developer's CSS projects.
    POST: Create a new project.
    """
    err = _require_developer(request)
    if err:
        return err

    if request.method == "GET":
        projects = CssProject.objects.filter(developer=request.user).order_by('-created_at')
        paginated = paginate_queryset(projects, request, default_per_page=20)

        data = []
        for p in paginated['items']:
            ver = p.current_version
            data.append({
                'id': str(p.id),
                'name': p.name,
                'description': p.description,
                'status': p.status,
                'current_version': ver.version_number if ver else None,
                'created_at': p.created_at.isoformat(),
                'updated_at': p.updated_at.isoformat(),
            })
        return api_success({'projects': data, 'pagination': paginated['pagination']})

    # POST — create

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    name = data.get('name', '').strip()
    if not name:
        return api_error("name is required.", status=400)

    limit_error = get_css_project_limit_error(request.user)
    if limit_error:
        return api_error(limit_error, status=400)

    project = CssProject.objects.create(
        developer=request.user,
        name=name[:200],
        description=data.get('description', '')[:1000],
    )
    return api_success({
        'id': str(project.id),
        'name': project.name,
        'status': project.status,
    }, message="Project created.", status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_auth_required
def project_detail_view(request, project_id):
    """
    GET: Project detail with current version.
    PATCH: Update project metadata.
    DELETE: Delete a project (only if not published).
    """
    err = _require_developer(request)
    if err:
        return err

    project = get_object_or_404(CssProject, id=project_id, developer=request.user)

    if request.method == "GET":
        ver = project.current_version
        return api_success({
            'id': str(project.id),
            'name': project.name,
            'description': project.description,
            'status': project.status,
            'current_version': {
                'version_number': ver.version_number,
                'css_content': ver.css_content,
                'html_template': ver.html_template,
                'commit_message': ver.commit_message,
                'created_at': ver.created_at.isoformat(),
            } if ver else None,
            'created_at': project.created_at.isoformat(),
            'updated_at': project.updated_at.isoformat(),
        })

    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return api_error("Invalid JSON format.", status=400)

        if 'name' in data:
            project.name = str(data['name'])[:200]
        if 'description' in data:
            project.description = str(data['description'])[:1000]
        project.save()
        return api_success({'id': str(project.id), 'name': project.name}, message="Project updated.")

    # DELETE
    if project.status == 'published':
        return api_error("Cannot delete a published project. Archive it first.", status=400)
    project.delete()
    return api_success({}, message="Project deleted.")


@require_http_methods(["GET", "POST"])
@api_auth_required
def project_versions_view(request, project_id):
    """
    GET: List version history.
    POST: Save a new version.
    """
    err = _require_developer(request)
    if err:
        return err

    project = get_object_or_404(CssProject, id=project_id, developer=request.user)

    if request.method == "GET":
        versions = CssVersion.objects.filter(project=project).order_by('-created_at')
        paginated = paginate_queryset(versions, request, default_per_page=20)
        data = [{
            'id': str(v.id),
            'version_number': v.version_number,
            'commit_message': v.commit_message,
            'is_current': v.is_current,
            'created_at': v.created_at.isoformat(),
        } for v in paginated['items']]
        return api_success({'versions': data, 'pagination': paginated['pagination']})

    # POST — create version
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    css_content = data.get('css_content', '').strip()
    commit_message = data.get('commit_message', '').strip()

    if not css_content:
        return api_error("css_content is required.", status=400)
    if not commit_message:
        return api_error("commit_message is required.", status=400)

    # Determine next version number
    last = CssVersion.objects.filter(project=project).order_by('-created_at').first()
    try:
        last_num = int(last.version_number.lstrip('v')) if last else 0
        new_num = f"v{last_num + 1}"
    except (ValueError, AttributeError):
        new_num = "v1"

    # Mark previous current as non-current
    CssVersion.objects.filter(project=project, is_current=True).update(is_current=False)

    version = CssVersion.objects.create(
        project=project,
        version_number=new_num,
        css_content=css_content,
        html_template=data.get('html_template', ''),
        commit_message=commit_message[:500],
        is_current=True,
    )
    return api_success({
        'id': str(version.id),
        'version_number': version.version_number,
    }, message="Version saved.", status=201)


# ==============================================================================
# Listings
# ==============================================================================

@require_http_methods(["GET", "POST"])
@api_auth_required
def listings_view(request):
    """
    GET: List developer's marketplace listings.
    POST: Create a listing from a project.
    """
    err = _require_developer(request)
    if err:
        return err

    if request.method == "GET":
        listings = CssListing.objects.filter(developer=request.user).order_by('-created_at')
        paginated = paginate_queryset(listings, request, default_per_page=20)
        data = [{
            'id': str(l.id),
            'title': l.title,
            'status': l.status,
            'visibility': l.visibility,
            'license_type': l.license_type,
            'published_at': l.published_at.isoformat() if l.published_at else None,
            'created_at': l.created_at.isoformat(),
        } for l in paginated['items']]
        return api_success({'listings': data, 'pagination': paginated['pagination']})

    # POST — create listing
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    title = data.get('title', '').strip()
    project_id = data.get('project_id')

    if not title:
        return api_error("title is required.", status=400)

    project = None
    if project_id:
        try:
            project = CssProject.objects.get(id=project_id, developer=request.user)
        except CssProject.DoesNotExist:
            return api_error("Project not found.", status=404)

    listing = CssListing.objects.create(
        developer=request.user,
        project=project,
        title=title[:255],
        description=data.get('description', '')[:5000],
        license_type=data.get('license_type', 'personal'),
        tags=data.get('tags', '')[:200],
        visibility=data.get('visibility', 'public'),
    )
    return api_success({'id': str(listing.id), 'title': listing.title}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_auth_required
def listing_detail_view(request, listing_id):
    """
    GET: Listing detail with pricing tiers.
    PATCH: Update listing (draft/rejected only).
    DELETE: Delete listing.
    """
    err = _require_developer(request)
    if err:
        return err

    listing = get_object_or_404(CssListing, id=listing_id, developer=request.user)

    if request.method == "GET":
        tiers = PricingTier.objects.filter(listing=listing)
        tiers_data = [{
            'id': str(t.id),
            'name': t.name,
            'price': float(t.price),
            'scope': t.scope,
            'includes_source': t.includes_source,
            'includes_support': t.includes_support,
        } for t in tiers]
        return api_success({
            'id': str(listing.id),
            'title': listing.title,
            'description': listing.description,
            'status': listing.status,
            'visibility': listing.visibility,
            'license_type': listing.license_type,
            'tags': listing.tags,
            'browser_support': listing.browser_support,
            'rejection_reason': listing.rejection_reason,
            'published_at': listing.published_at.isoformat() if listing.published_at else None,
            'pricing_tiers': tiers_data,
        })

    if request.method == "PATCH":
        if listing.status not in ('draft', 'rejected'):
            return api_error("Only draft or rejected listings can be edited.", status=400)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return api_error("Invalid JSON format.", status=400)

        for field in ('title', 'description', 'tags', 'visibility', 'license_type'):
            if field in data:
                setattr(listing, field, str(data[field])[:255 if field == 'title' else 5000])

        listing.save()
        return api_success({'id': str(listing.id)}, message="Listing updated.")

    # DELETE — only allow removing listings that are not live on the marketplace
    if listing.status not in ('draft', 'rejected'):
        return api_error(
            "Only draft or rejected listings can be deleted. "
            "Unpublish the listing first before deleting it.",
            status=400,
        )
    listing.delete()
    return api_success({}, message="Listing deleted.")


# ==============================================================================
# Analytics
# ==============================================================================

@require_http_methods(["GET"])
@api_auth_required
def analytics_overview_view(request):
    """
    GET: Analytics overview — aggregate revenue, sales, and conversion.
    """
    err = _require_developer(request)
    if err:
        return err

    from django.db.models import Sum, Avg
    agg = SaleAnalytics.objects.filter(developer=request.user).aggregate(
        total_revenue=Sum('revenue'),
        total_sales=Sum('sales_count'),
        avg_conversion=Avg('conversion_rate'),
        total_views=Sum('page_views'),
    )

    return api_success({
        'total_revenue': float(agg['total_revenue'] or 0),
        'total_sales': agg['total_sales'] or 0,
        'avg_conversion_rate': float(agg['avg_conversion'] or 0),
        'total_page_views': agg['total_views'] or 0,
    })


@require_http_methods(["GET"])
@api_auth_required
def analytics_revenue_view(request):
    """
    GET: Revenue breakdown by day. Optional: ?days=30|60|90
    """
    err = _require_developer(request)
    if err:
        return err

    try:
        days = min(int(request.GET.get('days', 30)), 365)
    except ValueError:
        days = 30

    from datetime import timedelta
    cutoff = timezone.now().date() - timedelta(days=days)
    rows = SaleAnalytics.objects.filter(
        developer=request.user, date__gte=cutoff
    ).order_by('date').values('date', 'revenue', 'sales_count')

    data = [{'date': str(r['date']), 'revenue': float(r['revenue']), 'sales': r['sales_count']} for r in rows]
    return api_success({'revenue': data, 'period_days': days})


@require_http_methods(["GET"])
@api_auth_required
def analytics_products_view(request):
    """
    GET: Per-listing sales and view stats.
    """
    err = _require_developer(request)
    if err:
        return err

    listings = CssListing.objects.filter(developer=request.user, status='published')
    data = []
    for listing in listings:
        data.append({
            'id': str(listing.id),
            'title': listing.title,
            'published_at': listing.published_at.isoformat() if listing.published_at else None,
        })
    return api_success({'products': data})


@require_http_methods(["GET"])
@api_auth_required
def analytics_customers_view(request):
    """
    GET: Customer segment analytics.
    """
    err = _require_developer(request)
    if err:
        return err

    customers = CustomerAnalytics.objects.filter(developer=request.user).select_related('customer')
    paginated = paginate_queryset(customers, request, default_per_page=20)

    data = [{
        'customer': c.customer.username,
        'purchase_count': c.purchase_count,
        'lifetime_value': float(c.lifetime_value),
        'first_purchase': c.first_purchase.isoformat() if c.first_purchase else None,
        'last_purchase': c.last_purchase.isoformat() if c.last_purchase else None,
        'favorite_category': c.favorite_category,
    } for c in paginated['items']]
    return api_success({'customers': data, 'pagination': paginated['pagination']})


@require_http_methods(["GET"])
@api_auth_required
def analytics_export_view(request):
    """
    GET: Export analytics data. ?format=json|csv
    """
    err = _require_developer(request)
    if err:
        return err

    fmt = request.GET.get('format', 'json').lower()
    rows = SaleAnalytics.objects.filter(developer=request.user).order_by('date')

    if fmt == 'csv':
        from django.http import HttpResponse
        import csv
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="analytics.csv"'
        writer = csv.writer(resp)
        writer.writerow(['Date', 'Revenue', 'Sales', 'Views', 'Conversion Rate'])
        for r in rows:
            writer.writerow([r.date, r.revenue, r.sales_count, r.page_views, r.conversion_rate])
        return resp

    data = [{
        'date': str(r.date),
        'revenue': float(r.revenue),
        'sales_count': r.sales_count,
        'page_views': r.page_views,
        'conversion_rate': float(r.conversion_rate),
    } for r in rows]
    return api_success({'analytics': data})


# ==============================================================================
# Webhooks
# ==============================================================================

@require_http_methods(["GET", "POST"])
@api_auth_required
def webhooks_view(request):
    """
    GET: List configured webhooks.
    POST: Create a webhook.
    """
    err = _require_developer(request)
    if err:
        return err

    if request.method == "GET":
        webhooks = Webhook.objects.filter(developer=request.user).order_by('-created_at')
        data = [{
            'id': str(w.id),
            'url': w.url,
            'events': w.events,
            'is_active': w.is_active,
            'failure_count': w.failure_count,
            'last_triggered_at': w.last_triggered_at.isoformat() if w.last_triggered_at else None,
            'created_at': w.created_at.isoformat(),
        } for w in webhooks]
        return api_success({'webhooks': data})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    url = data.get('url', '').strip()
    events = data.get('events', [])

    if not url:
        return api_error("url is required.", status=400)
    if not url.startswith('https://'):
        return api_error("Webhook URL must use HTTPS.", status=400)
    if not isinstance(events, list) or not events:
        return api_error("events must be a non-empty list of event names.", status=400)

    import secrets
    webhook = Webhook.objects.create(
        developer=request.user,
        url=url,
        secret=secrets.token_hex(32),
        events=events,
        is_active=True,
    )
    return api_success({'id': str(webhook.id), 'url': webhook.url, 'events': webhook.events}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_auth_required
def webhook_detail_view(request, webhook_id):
    """
    GET: Webhook detail.
    PATCH: Update URL or events.
    DELETE: Delete webhook.
    """
    err = _require_developer(request)
    if err:
        return err

    webhook = get_object_or_404(Webhook, id=webhook_id, developer=request.user)

    if request.method == "GET":
        return api_success({
            'id': str(webhook.id),
            'url': webhook.url,
            'events': webhook.events,
            'is_active': webhook.is_active,
            'failure_count': webhook.failure_count,
            'last_triggered_at': webhook.last_triggered_at.isoformat() if webhook.last_triggered_at else None,
        })

    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return api_error("Invalid JSON format.", status=400)

        if 'url' in data:
            url = str(data['url']).strip()
            if not url.startswith('https://'):
                return api_error("Webhook URL must use HTTPS.", status=400)
            webhook.url = url
        if 'events' in data:
            if not isinstance(data['events'], list):
                return api_error("events must be a list.", status=400)
            webhook.events = data['events']
        if 'is_active' in data:
            webhook.is_active = bool(data['is_active'])

        webhook.save()
        return api_success({'id': str(webhook.id)}, message="Webhook updated.")

    # DELETE
    webhook.delete()
    return api_success({}, message="Webhook deleted.")


@require_http_methods(["POST"])
@api_auth_required
def webhook_test_view(request, webhook_id):
    """
    POST: Send a test delivery to the webhook.
    """
    err = _require_developer(request)
    if err:
        return err

    webhook = get_object_or_404(Webhook, id=webhook_id, developer=request.user)

    if not webhook.is_active:
        return api_error("Webhook is inactive.", status=400)

    import hmac
    import hashlib
    import urllib.request

    payload = {'event': 'test', 'message': 'This is a test delivery from WOCShAck API.'}
    payload_bytes = json.dumps(payload).encode('utf-8')
    signature = hmac.new(webhook.secret.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()

    try:
        req = urllib.request.Request(
            webhook.url,
            data=payload_bytes,
            headers={
                'Content-Type': 'application/json',
                'X-WOCShAck-Signature': f'sha256={signature}',
                'X-WOCShAck-Event': 'test',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status_code = resp.status
            response_body = resp.read().decode('utf-8', errors='replace')[:500]
    except Exception as exc:
        status_code = 0
        response_body = str(exc)[:500]

    delivery = WebhookDelivery.objects.create(
        webhook=webhook,
        event_type='test',
        payload=payload,
        status_code=status_code,
        response_body=response_body,
        attempts=1,
    )
    webhook.last_triggered_at = timezone.now()
    webhook.save()

    return api_success({
        'delivery_id': str(delivery.id),
        'status_code': status_code,
        'response_body': response_body,
    })


@require_http_methods(["GET"])
@api_auth_required
def webhook_logs_view(request, webhook_id):
    """
    GET: List recent delivery attempts for a webhook.
    """
    err = _require_developer(request)
    if err:
        return err

    webhook = get_object_or_404(Webhook, id=webhook_id, developer=request.user)
    deliveries = WebhookDelivery.objects.filter(webhook=webhook).order_by('-created_at')
    paginated = paginate_queryset(deliveries, request, default_per_page=20)

    data = [{
        'id': str(d.id),
        'event_type': d.event_type,
        'status_code': d.status_code,
        'attempts': d.attempts,
        'delivered_at': d.delivered_at.isoformat() if d.delivered_at else None,
        'created_at': d.created_at.isoformat(),
    } for d in paginated['items']]
    return api_success({'deliveries': data, 'pagination': paginated['pagination']})


# ==============================================================================
# Balance & Payouts
# ==============================================================================

@require_http_methods(["GET"])
@api_auth_required
def balance_view(request):
    """
    GET: Developer balance — available, pending, total earned.
    """
    err = _require_developer(request)
    if err:
        return err

    balance, _ = DeveloperBalance.objects.get_or_create(developer=request.user)
    return api_success({
        'available': float(balance.available),
        'pending': float(balance.pending),
        'total_earned': float(balance.total_earned),
        'total_paid': float(balance.total_paid),
        'updated_at': balance.updated_at.isoformat() if balance.updated_at else None,
    })


@require_http_methods(["GET", "POST"])
@api_auth_required
def payouts_view(request):
    """
    GET: List payout history.
    POST: Request a payout.
    """
    err = _require_developer(request)
    if err:
        return err

    if request.method == "GET":
        payouts = Payout.objects.filter(developer=request.user).order_by('-requested_at')
        paginated = paginate_queryset(payouts, request, default_per_page=20)
        data = [{
            'id': str(p.id),
            'amount': float(p.amount),
            'fee': float(p.fee),
            'net_amount': float(p.net_amount),
            'status': p.status,
            'tx_ref': p.tx_ref,
            'requested_at': p.requested_at.isoformat() if p.requested_at else None,
            'processed_at': p.processed_at.isoformat() if p.processed_at else None,
        } for p in paginated['items']]
        return api_success({'payouts': data, 'pagination': paginated['pagination']})

    # POST — request payout
    # Use select_for_update to prevent concurrent payout requests from draining
    # the same balance twice (TOCTOU race condition).
    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        try:
            balance = DeveloperBalance.objects.select_for_update().get(developer=request.user)
        except DeveloperBalance.DoesNotExist:
            return api_error("No developer balance record found.", status=404)

        if balance.available <= 0:
            return api_error("No available balance for payout.", status=400)

        try:
            primary_method = PayoutMethod.objects.get(developer=request.user, is_primary=True)
        except PayoutMethod.DoesNotExist:
            return api_error("No primary payout method configured.", status=400)

        amount = balance.available

        payout = Payout.objects.create(
            developer=request.user,
            amount=amount,
            fee=Decimal('0.00'),
            net_amount=amount,
            method=primary_method,
            status='pending',
        )

        balance.available = Decimal('0.00')
        balance.pending += amount
        balance.save()

    return api_success({
        'payout_id': str(payout.id),
        'amount': float(amount),
        'status': payout.status,
    }, message="Payout requested.", status=201)


@require_http_methods(["POST"])
@api_auth_required
def payouts_request_view(request):
    """POST-only alias for requesting a payout."""
    return payouts_view(request)


# ==============================================================================
# Promotions
# ==============================================================================

@require_http_methods(["GET", "POST"])
@api_auth_required
def promotions_view(request):
    """
    GET: List promotions.
    POST: Create a promotion.
    """
    err = _require_developer(request)
    if err:
        return err

    if request.method == "GET":
        # Promotions tied to developer's listings
        dev_listing_ids = CssListing.objects.filter(developer=request.user).values_list('id', flat=True)
        promotions = Promotion.objects.filter(listing_id__in=dev_listing_ids).order_by('-created_at')
        paginated = paginate_queryset(promotions, request, default_per_page=20)
        data = [{
            'id': str(p.id),
            'code': p.code,
            'discount_percent': float(p.discount_percent) if p.discount_percent else None,
            'discount_amount': float(p.discount_amount) if p.discount_amount else None,
            'usage_count': p.usage_count,
            'usage_limit': p.usage_limit,
            'is_active': p.is_active,
            'is_valid': p.is_valid,
            'start_date': p.start_date.isoformat() if p.start_date else None,
            'end_date': p.end_date.isoformat() if p.end_date else None,
        } for p in paginated['items']]
        return api_success({'promotions': data, 'pagination': paginated['pagination']})

    # POST — create
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    code = data.get('code', '').strip().upper()
    if not code:
        return api_error("code is required.", status=400)

    if Promotion.objects.filter(code=code).exists():
        return api_error("Promotion code already exists.", status=400)

    listing_id = data.get('listing_id')
    if not listing_id:
        return api_error("listing_id is required.", status=400)
    try:
        listing = CssListing.objects.get(id=listing_id, developer=request.user)
    except CssListing.DoesNotExist:
        return api_error("Listing not found.", status=404)

    discount_percent = None
    discount_amount = None
    if 'discount_percent' in data:
        try:
            discount_percent = Decimal(str(data['discount_percent']))
            if not 0 < discount_percent <= 100:
                return api_error("discount_percent must be between 0 and 100.", status=400)
        except (InvalidOperation, ValueError):
            return api_error("Invalid discount_percent.", status=400)
    elif 'discount_amount' in data:
        try:
            discount_amount = Decimal(str(data['discount_amount']))
            if discount_amount <= 0:
                return api_error("discount_amount must be positive.", status=400)
        except (InvalidOperation, ValueError):
            return api_error("Invalid discount_amount.", status=400)
    else:
        return api_error("Either discount_percent or discount_amount is required.", status=400)

    promo = Promotion.objects.create(
        listing=listing,
        code=code,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        start_date=data.get('start_date') or timezone.now(),
        end_date=data.get('end_date'),
        usage_limit=data.get('usage_limit', 0) or 0,
        is_active=True,
    )
    return api_success({'id': str(promo.id), 'code': promo.code}, status=201)


@require_http_methods(["DELETE"])
@api_auth_required
def promotion_delete_view(request, promo_id):
    """
    DELETE: Delete a promotion.
    """
    err = _require_developer(request)
    if err:
        return err

    dev_listing_ids = CssListing.objects.filter(developer=request.user).values_list('id', flat=True)
    promo = get_object_or_404(Promotion, id=promo_id, listing_id__in=dev_listing_ids)
    promo.delete()
    return api_success({}, message="Promotion deleted.")


# ==============================================================================
# CSS Tools
# ==============================================================================

@require_http_methods(["POST"])
@api_auth_required
def tools_minify_view(request):
    """
    POST {"css_content": "..."}: Return minified CSS.
    """
    err = _require_developer(request)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    css = data.get('css_content', '')
    if not css:
        return api_error("css_content is required.", status=400)

    original_size = len(css)
    minified = _minify_css(css)
    return api_success({
        'css_content': minified,
        'original_size': original_size,
        'minified_size': len(minified),
        'savings_percent': round((1 - len(minified) / original_size) * 100, 1) if original_size else 0,
    })


@require_http_methods(["POST"])
@api_auth_required
def tools_beautify_view(request):
    """
    POST {"css_content": "..."}: Return beautified CSS.
    """
    err = _require_developer(request)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    css = data.get('css_content', '')
    if not css:
        return api_error("css_content is required.", status=400)

    return api_success({'css_content': _beautify_css(css)})


@require_http_methods(["POST"])
@api_auth_required
def tools_validate_view(request):
    """
    POST {"css_content": "..."}: Validate CSS syntax and return any errors.
    """
    err = _require_developer(request)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    css = data.get('css_content', '')
    if not css:
        return api_error("css_content is required.", status=400)

    errors = _validate_css(css)
    return api_success({
        'is_valid': len(errors) == 0,
        'errors': errors,
        'error_count': len(errors),
    })


@require_http_methods(["POST"])
@api_auth_required
def tools_prefix_view(request):
    """
    POST {"css_content": "..."}: Add vendor prefixes to CSS.
    """
    err = _require_developer(request)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    css = data.get('css_content', '')
    if not css:
        return api_error("css_content is required.", status=400)

    return api_success({'css_content': _prefix_css(css)})
