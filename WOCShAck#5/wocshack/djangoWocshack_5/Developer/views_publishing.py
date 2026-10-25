"""
Developer module views — publishing, listings, pricing, and promotions.
"""
import os
import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST

from .views import developer_required
from .models import CssProject, CssListing, PricingTier, Promotion
from Api.models import Css as ApiCss, CssCategory
from Api.gif_utils import generate_gif_for_css

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_GIF_EXTENSIONS = {'.gif'}
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


def _validate_upload(file, allowed_extensions, field_name):
    """Validate an uploaded file's extension and size. Returns error message or None."""
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in allowed_extensions:
        return f'{field_name}: only {", ".join(allowed_extensions)} files are allowed.'
    if file.size > MAX_UPLOAD_SIZE:
        return f'{field_name}: file size must be under 5 MB.'
    return None


# =============================================================================
# PUBLISHING
# =============================================================================

@developer_required
def publish_project(request, project_id):
    """Publish a CSS project directly to the marketplace as an Api.Css entry."""
    project = get_object_or_404(CssProject, id=project_id, developer=request.user)

    # Check if already published as an Api.Css with same name
    existing = ApiCss.objects.filter(name=project.name, creator=request.user).first()
    if existing:
        messages.info(request, 'This project is already published. Edit it in the editor.')
        return redirect(f'/developer/editor/?css={existing.id}')

    # Enforce CSS publishing limit
    from Developer.models import DeveloperSubscription
    sub = DeveloperSubscription.objects.filter(
        user=request.user,
        status__in=['active', 'trial'],
    ).select_related('plan').first()
    css_limit = sub.plan.css_limit if sub else 0
    
    if css_limit > 0:
        current_count = ApiCss.objects.filter(creator=request.user).count()
        if current_count >= css_limit:
            plan_name = sub.plan.name if sub else 'current'
            messages.error(
                request,
                f'CSS publishing limit reached. Your {plan_name} plan allows '
                f'{css_limit} published marketplace listings (you have {current_count}). '
                f'Upgrade your plan to publish more.'
            )
            return redirect('developer_editor')

    categories = CssCategory.objects.all()

    if request.method == 'POST':
        title = escape(request.POST.get('title', '')[:100])
        price_str = request.POST.get('price', '0')
        category_id = request.POST.get('category', '')

        if not title:
            messages.error(request, 'Title is required.')
            return render(request, 'developer/publish.html', {'project': project, 'categories': categories})

        try:
            price = Decimal(price_str)
            if price < 0:
                price = Decimal('0.00')
        except (InvalidOperation, ValueError):
            price = Decimal('0.00')

        category = None
        if category_id:
            try:
                category = CssCategory.objects.get(id=category_id)
            except CssCategory.DoesNotExist:
                pass

        version = project.current_version
        css_content = version.css_content if version else ''

        try:
            with transaction.atomic():
                api_css = ApiCss.objects.create(
                    name=title,
                    css_content=css_content,
                    html_template=version.html_template if version else '<div class="loader"></div>',
                    author=request.user.username,
                    creator=request.user,
                    price=price,
                    category=category,
                )
        except IntegrityError:
            messages.error(request, f'A marketplace item named "{title}" already exists. Choose a different title.')
            return render(request, 'developer/publish.html', {'project': project, 'categories': categories})

        # Auto-generate preview GIF
        html_template = version.html_template if version else '<div class="loader"></div>'
        result = generate_gif_for_css(css_content, str(api_css.id), body_html=html_template)
        if result:
            content_file, filename = result
            api_css.preview_gif.save(filename, content_file, save=True)

        # Update project status
        project.status = CssProject.Status.PUBLISHED
        project.save()

        try:
            from Community.services.feed_service import create_feed_item
            from Community.models.feed import ActivityFeedItem
            create_feed_item(
                user=request.user,
                action_type=ActivityFeedItem.ActionType.CSS_PUBLISHED,
                title=f'Published to marketplace: {title}',
                description='',
                icon='🛒',
                related_object_id=str(api_css.id),
            )
        except Exception:
            pass

        messages.success(request, f'"{title}" published to the marketplace!')
        return redirect(f'/developer/editor/?css={api_css.id}')

    context = {'project': project, 'categories': categories}
    return render(request, 'developer/publish.html', context)


# =============================================================================
# LISTINGS
# =============================================================================

@developer_required
def listing_list(request):
    """View all developer's listings."""
    listings = CssListing.objects.filter(developer=request.user).select_related('project')
    context = {'listings': listings}
    return render(request, 'developer/listings.html', context)


@developer_required
def edit_listing(request, listing_id):
    """Edit an existing listing."""
    if request.user.is_staff or request.user.is_superuser:
        listing = get_object_or_404(CssListing, id=listing_id)
    else:
        listing = get_object_or_404(CssListing, id=listing_id, developer=request.user)

    if request.method == 'POST':
        listing.title = escape(request.POST.get('title', '')[:200])
        listing.description = request.POST.get('description', '')[:5000]
        listing.license_type = request.POST.get('license_type', listing.license_type)
        listing.visibility = request.POST.get('visibility', listing.visibility)
        listing.tags = escape(request.POST.get('tags', '')[:500])
        listing.demo_url = request.POST.get('demo_url', '')[:200]
        listing.documentation = request.POST.get('documentation', '')[:10000]

        if listing.license_type not in dict(CssListing.LicenseType.choices):
            listing.license_type = 'personal'
        if listing.visibility not in dict(CssListing.Visibility.choices):
            listing.visibility = 'public'

        if 'thumbnail' in request.FILES:
            err = _validate_upload(request.FILES['thumbnail'], ALLOWED_IMAGE_EXTENSIONS, 'Thumbnail')
            if err:
                messages.error(request, err)
                return render(request, 'developer/edit_listing.html', {'listing': listing, 'pricing_tiers': listing.pricing_tiers.all()})
            listing.thumbnail = request.FILES['thumbnail']
        if 'preview_gif' in request.FILES:
            err = _validate_upload(request.FILES['preview_gif'], ALLOWED_GIF_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS, 'Preview')
            if err:
                messages.error(request, err)
                return render(request, 'developer/edit_listing.html', {'listing': listing, 'pricing_tiers': listing.pricing_tiers.all()})
            listing.preview_gif = request.FILES['preview_gif']

        listing.save()
        messages.success(request, 'Listing updated.')
        return redirect('developer_listings')

    pricing_tiers = listing.pricing_tiers.all()
    context = {'listing': listing, 'pricing_tiers': pricing_tiers}
    return render(request, 'developer/edit_listing.html', context)


@developer_required
@require_POST
def delete_listing(request, listing_id):
    """Delete a listing."""
    listing = get_object_or_404(CssListing, id=listing_id, developer=request.user)
    listing_title = listing.title
    listing.delete()
    messages.success(request, f'Listing "{listing_title}" deleted.')
    return redirect('developer_listings')


# =============================================================================
# PRICING
# =============================================================================

@developer_required
def set_pricing(request, listing_id):
    """Set pricing tiers for a listing."""
    listing = get_object_or_404(CssListing, id=listing_id, developer=request.user)

    if request.method == 'POST':
        # Clear existing pricing
        listing.pricing_tiers.all().delete()

        # Add new tiers from form
        tier_names = request.POST.getlist('tier_name')
        tier_prices = request.POST.getlist('tier_price')
        tier_scopes = request.POST.getlist('tier_scope')
        tier_source = request.POST.getlist('tier_includes_source')
        tier_support = request.POST.getlist('tier_includes_support')

        for i, name in enumerate(tier_names):
            if not name:
                continue
            try:
                price = Decimal(tier_prices[i]) if i < len(tier_prices) else Decimal('0')
            except (ValueError, IndexError):
                price = Decimal('0')

            scope = tier_scopes[i] if i < len(tier_scopes) else 'personal'
            if scope not in dict(PricingTier.Scope.choices):
                scope = 'personal'

            PricingTier.objects.create(
                listing=listing,
                name=escape(name[:100]),
                price=price,
                scope=scope,
                includes_source=str(i) in tier_source,
                includes_support=str(i) in tier_support,
            )

        messages.success(request, 'Pricing updated.')
        return redirect('developer_edit_listing', listing_id=listing.id)

    pricing_tiers = listing.pricing_tiers.all()
    context = {'listing': listing, 'pricing_tiers': pricing_tiers}
    return render(request, 'developer/set_pricing.html', context)


# =============================================================================
# PROMOTIONS
# =============================================================================

@developer_required
def promotion_list(request):
    """View all promotions."""
    promotions = Promotion.objects.filter(
        listing__developer=request.user
    ).select_related('listing')
    context = {'promotions': promotions}
    return render(request, 'developer/promotions.html', context)


@developer_required
def create_promotion(request):
    """Create a new promotion code."""
    listings = CssListing.objects.filter(developer=request.user)

    if request.method == 'POST':
        code = escape(request.POST.get('code', '')[:50]).upper()
        listing_id = request.POST.get('listing_id', '')
        discount_percent = request.POST.get('discount_percent', '')
        start_date = request.POST.get('start_date', '')
        end_date = request.POST.get('end_date', '')
        usage_limit = request.POST.get('usage_limit', '0')

        if not code:
            messages.error(request, 'Promotion code is required.')
            return render(request, 'developer/create_promotion.html', {'listings': listings})

        if Promotion.objects.filter(code=code).exists():
            messages.error(request, 'This promotion code already exists.')
            return render(request, 'developer/create_promotion.html', {'listings': listings})

        listing = None
        if listing_id:
            listing = get_object_or_404(CssListing, id=listing_id, developer=request.user)

        try:
            discount_percent_value = Decimal(discount_percent)
            if not (Decimal('0.01') <= discount_percent_value <= Decimal('100')):
                raise ValueError
        except (ValueError, ArithmeticError, InvalidOperation):
            messages.error(request, 'Discount percent must be between 0.01 and 100.')
            return render(request, 'developer/create_promotion.html', {'listings': listings})

        promo = Promotion(
            code=code,
            listing=listing,
            start_date=start_date or timezone.now(),
            end_date=end_date or (timezone.now() + timezone.timedelta(days=30)),
            discount_percent=discount_percent_value,
        )

        try:
            promo.usage_limit = int(usage_limit)
        except ValueError:
            promo.usage_limit = 0

        promo.save()
        messages.success(request, f'Promotion "{code}" created!')
        return redirect('developer_promotions')

    context = {'listings': listings}
    return render(request, 'developer/create_promotion.html', context)
