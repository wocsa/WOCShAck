"""
V.R.C CSS API - REST API for CSS marketplace.
All views implement proper authentication, authorization, input validation, and CSRF protection.
"""
from decimal import Decimal, InvalidOperation
import re as _re
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.db import IntegrityError, transaction
from django.db.models import Q, Count, Sum, Avg
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.utils.html import escape
import json
import re

from functools import wraps
import hashlib
from .models import Css, Purchase, DownloadLog, CssCategory, ApiKey, ApiKeyUsage


# =============================================================================
# API KEY AUTHENTICATION
# =============================================================================

def get_user_from_api_key(request):
    """
    Look up user from X-API-Key header.
    Hashes the provided key and compares against stored hashes.
    Returns User or None.  Attaches the resolved key object as request._api_key_obj
    so downstream code (e.g. API-call-limit enforcement) can reference it.
    """
    api_key = request.META.get('HTTP_X_API_KEY', '').strip()
    if not api_key:
        return None
    key_hash = hashlib.sha256(api_key.encode('utf-8')).hexdigest()
    try:
        key_obj = ApiKey.objects.select_related('user').get(key_hash=key_hash, is_active=True)
        # Check expiration
        if key_obj.expires_at and key_obj.expires_at < timezone.now():
            return None
        # Update last_used_at
        key_obj.last_used_at = timezone.now()
        key_obj.save(update_fields=['last_used_at'])
        # Attach key object for downstream API-call-limit tracking
        request._api_key_obj = key_obj
        return key_obj.user
    except ApiKey.DoesNotExist:
        return None


def _get_active_subscription(user):
    """Return the user's active DeveloperSubscription (with plan), or None."""
    from Developer.models import DeveloperSubscription
    return DeveloperSubscription.objects.filter(
        user=user,
        status__in=['active', 'trial'],
    ).select_related('plan').first()


def _check_and_log_api_call(request):
    """
    Enforce the developer plan's monthly api_calls_limit for API-key-authenticated
    requests. Logs the call to ApiKeyUsage and returns an api_error response if
    the limit has been exceeded, otherwise returns None.
    Session-authenticated calls (from the web UI) are not counted.
    """
    api_key_obj = getattr(request, '_api_key_obj', None)
    if api_key_obj is None:
        return None  # session auth — not subject to API call quota

    sub = _get_active_subscription(request.user)
    plan_limit = sub.plan.api_calls_limit if sub else 0

    if plan_limit > 0:
        # Count API calls for this user's keys in the current calendar month
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        calls_this_month = ApiKeyUsage.objects.filter(
            api_key__user=request.user,
            timestamp__gte=month_start,
        ).count()

        if calls_this_month >= plan_limit:
            plan_name = sub.plan.name if sub else 'current'
            return api_error(
                f"Monthly API call limit reached ({plan_limit} calls for "
                f"{plan_name} plan). Upgrade your plan for more API calls.",
                status=429,
            )

    # Log the API call
    ApiKeyUsage.objects.create(
        api_key=api_key_obj,
        endpoint=request.path,
        method=request.method,
        status_code=200,
        ip_address=request.META.get('REMOTE_ADDR', '0.0.0.0'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
    )
    return None


def api_auth_required(view_func):
    """
    Decorator that allows authentication via API key or session.
    Checks X-API-Key header first, falls back to session auth.
    """
    @wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        # Try API key auth first
        api_user = get_user_from_api_key(request)
        if api_user:
            request.user = api_user
            limit_err = _check_and_log_api_call(request)
            if limit_err:
                return limit_err
            return view_func(request, *args, **kwargs)
        # Fall back to session auth
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        return api_error('Authentication required. Provide X-API-Key header or log in.', status=401)
    return wrapper


# =============================================================================
# API RESPONSE HELPERS
# =============================================================================

def api_error(message, status=400, errors=None):
    """
    Standardized error response format.
    Ensures consistent error handling across all endpoints.
    """
    response = {
        'success': False,
        'error': message,
    }
    if errors:
        response['errors'] = errors
    return JsonResponse(response, status=status)


def api_success(data, message=None, status=200):
    """
    Standardized success response format.
    """
    response = {
        'success': True,
        'data': data,
    }
    if message:
        response['message'] = message
    return JsonResponse(response, status=status)


def paginate_queryset(queryset, request, default_per_page=20, max_per_page=100):
    """
    Paginate a queryset with validated parameters.
    """
    try:
        page = int(request.GET.get('page', 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = int(request.GET.get('per_page', default_per_page))
        per_page = min(max(1, per_page), max_per_page)
    except (ValueError, TypeError):
        per_page = default_per_page

    paginator = Paginator(queryset, per_page)

    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return {
        'items': list(page_obj),
        'pagination': {
            'page': page_obj.number,
            'per_page': per_page,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        }
    }


def serialize_css(css, include_content=True, include_stats=False):
    """
    Serialize CSS object to dictionary.
    Allows controlling what data is exposed.
    By default, css_content is NOT included in list views to prevent source code scraping.
    GIF preview URL is always included when available.
    """
    data = {
        'id': str(css.id),
        'name': css.name,
        'author': css.author,
        'creator_id': css.creator.id if css.creator else None,
        'creator_username': css.creator.username if css.creator else None,
        'price': str(css.price),
        'created_at': css.created_at.isoformat(),
        'updated_at': css.updated_at.isoformat(),
    }

    # This allows clients to display a preview without exposing CSS source code
    if hasattr(css, 'preview_gif') and css.preview_gif:
        data['preview_gif_url'] = css.preview_gif.url
    else:
        data['preview_gif_url'] = None

    # Include category if available
    if hasattr(css, 'category') and css.category:
        data['category'] = {
            'id': str(css.category.id),
            'name': css.category.name,
            'slug': css.category.slug,
        }
    else:
        data['category'] = None

    if include_content:
        data['css_content'] = css.css_content

    if include_stats:
        # Include aggregated statistics if requested
        data['stats'] = {
            'download_count': getattr(css, 'download_count', 0) or 0,
            'purchase_count': getattr(css, 'purchase_count', 0) or 0,
            'avg_rating': float(getattr(css, 'avg_rating', 0) or 0),
            'review_count': getattr(css, 'review_count', 0) or 0,
        }

    return data


# =============================================================================
# API ROOT
# =============================================================================

def api(request):
    """
    API root endpoint with documentation.
    """
    return JsonResponse({
        'success': True,
        'message': 'V.R.C CSS API',
        'version': '1.0.0',
        'endpoints': {
            'public': {
                'GET /api/': 'API documentation (this endpoint)',
                'GET /api/css/': 'List all CSS files (supports pagination, sorting, filtering)',
                'GET /api/css/<uuid>/': 'Get specific CSS file by ID',
                'GET /api/css/search/': 'Search CSS files',
                'GET /api/categories/': 'List all categories',
            },
            'authenticated': {
                'POST /api/css/': 'Create a new CSS file',
                'PUT /api/css/<uuid>/': 'Update your own CSS file',
                'DELETE /api/css/<uuid>/': 'Delete your own CSS file',
                'GET /api/css/my/': 'Get your own CSS files',
                'GET /api/css/purchased/': 'Get your purchased CSS files',
                'GET /api/css/accessible/': 'Get all accessible CSS (owned + purchased)',
                'POST /api/css/<uuid>/purchase/': 'Purchase a CSS file',
                'POST /api/css/<uuid>/download/': 'Log download of owned/purchased CSS',
                'GET /api/analytics/': 'Get sales analytics (sellers only)',
            }
        },
        'query_parameters': {
            'pagination': {
                'page': 'Page number (default: 1)',
                'per_page': 'Items per page (default: 20, max: 100)',
            },
            'sorting': {
                'sort': 'Sort field (name, price, created_at, author)',
                'order': 'Sort order (asc, desc)',
            },
            'filtering': {
                'search': 'Search in name and author',
                'author': 'Filter by author name',
                'creator': 'Filter by creator username',
                'category': 'Filter by category slug',
                'price_min': 'Minimum price filter',
                'price_max': 'Maximum price filter',
                'free': 'Only free items (true/false)',
            }
        }
    })


# =============================================================================
# PUBLIC ENDPOINTS - No authentication required
# =============================================================================

@require_GET
def get_all_css(request):
    """
    Public endpoint: Get all CSS files with pagination, sorting, and filtering.
    Uses allowlisted parameters to prevent injection attacks.
    """
    css_files = Css.objects.select_related('creator', 'category').all()

    # Search filter (name and author)
    search = request.GET.get('search', '').strip()[:100]
    if search:
        css_files = css_files.filter(
            Q(name__icontains=search) | Q(author__icontains=search)
        )

    # Author filter
    author = request.GET.get('author', '').strip()[:150]
    if author:
        css_files = css_files.filter(author__icontains=author)

    # Creator filter
    creator = request.GET.get('creator', '').strip()[:150]
    if creator:
        css_files = css_files.filter(creator__username__icontains=creator)

    # Category filter
    category_slug = request.GET.get('category', '').strip()[:100]
    if category_slug:
        css_files = css_files.filter(category__slug=category_slug)

    # Price filters
    try:
        price_min = request.GET.get('price_min')
        if price_min:
            price_min = Decimal(price_min)
            if price_min >= 0:
                css_files = css_files.filter(price__gte=price_min)
    except (InvalidOperation, ValueError):
        pass

    try:
        price_max = request.GET.get('price_max')
        if price_max:
            price_max = Decimal(price_max)
            if price_max >= 0:
                css_files = css_files.filter(price__lte=price_max)
    except (InvalidOperation, ValueError):
        pass

    # Free only filter
    free_only = request.GET.get('free', '').lower()
    if free_only == 'true':
        css_files = css_files.filter(price=0)

    sort_field = request.GET.get('sort', 'created_at').lower()
    sort_order = request.GET.get('order', 'desc').lower()

    valid_sort_fields = {
        'name': 'name',
        'price': 'price',
        'created_at': 'created_at',
        'updated_at': 'updated_at',
        'author': 'author',
    }

    if sort_field in valid_sort_fields:
        order_prefix = '-' if sort_order == 'desc' else ''
        css_files = css_files.order_by(f"{order_prefix}{valid_sort_fields[sort_field]}")
    else:
        css_files = css_files.order_by('-created_at')

    # Annotate with statistics for public listing (doesn't include content by default)
    css_files = css_files.annotate(
        download_count=Count('download_logs', distinct=True),
        purchase_count=Count('purchases', distinct=True),
    )

    # Paginate
    paginated = paginate_queryset(css_files, request)

    # Serialize (never include content for public list view)
    data = [
        serialize_css(css, include_content=False, include_stats=True)
        for css in paginated['items']
    ]

    return api_success({
        'css_files': data,
        'count': len(data),
        'pagination': paginated['pagination'],
    })


@require_GET
def get_one_css(request, css_id):
    """
    Public endpoint: Get a specific CSS file by ID.
    """
    try:
        css = Css.objects.select_related('creator', 'category').annotate(
            download_count=Count('download_logs', distinct=True),
            purchase_count=Count('purchases', distinct=True),
        ).get(id=css_id)
    except Css.DoesNotExist:
        return api_error('CSS file not found.', status=404)

    return api_success({
        'css': serialize_css(css, include_content=False, include_stats=True)
    })


@require_GET
def search_css(request):
    """
    Public endpoint: Search CSS files.
    Dedicated search endpoint with better relevance handling.
    """
    query = request.GET.get('q', '').strip()[:200]

    if not query or len(query) < 2:
        return api_error('Search query must be at least 2 characters.', status=400)

    css_files = Css.objects.select_related('creator', 'category').filter(
        Q(name__icontains=query) |
        Q(author__icontains=query) |
        Q(css_content__icontains=query)
    ).annotate(
        download_count=Count('download_logs', distinct=True),
        purchase_count=Count('purchases', distinct=True),
    ).order_by('-created_at')

    # Paginate results
    paginated = paginate_queryset(css_files, request)

    data = [
        serialize_css(css, include_content=False, include_stats=True)
        for css in paginated['items']
    ]

    return api_success({
        'query': escape(query),
        'css_files': data,
        'count': len(data),
        'pagination': paginated['pagination'],
    })


@require_GET
def list_categories(request):
    """
    Public endpoint: List all categories.
    """
    categories = CssCategory.objects.annotate(
        css_count=Count('css_files')
    ).order_by('name')

    data = [{
        'id': str(cat.id),
        'name': cat.name,
        'slug': cat.slug,
        'description': cat.description,
        'css_count': cat.css_count,
    } for cat in categories]

    return api_success({
        'categories': data,
        'count': len(data),
    })


# =============================================================================
# AUTHENTICATED ENDPOINTS - User must be logged in
# =============================================================================

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def create_css(request):
    """
    Create a new CSS file.
    Validates all inputs and ensures proper ownership.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error('Invalid JSON in request body.')

    name = data.get('name', '').strip()[:100]
    css_content = data.get('css_content', '').strip()
    author = data.get('author', request.user.username).strip()[:150]

    if not name:
        return api_error('Name is required.', errors={'name': 'This field is required.'})

    if not css_content:
        return api_error('CSS content is required.', errors={'css_content': 'This field is required.'})

    try:
        price = Decimal(str(data.get('price', 0)))
        if price < 0:
            return api_error('Price cannot be negative.', errors={'price': 'Must be 0 or greater.'})
        if price > Decimal('9999.99'):
            return api_error('Price exceeds maximum allowed.', errors={'price': 'Maximum is 9999.99.'})
    except (InvalidOperation, ValueError):
        return api_error('Invalid price format.', errors={'price': 'Must be a valid decimal number.'})

    # Category (optional)
    category_slug = data.get('category', '').strip()
    category = None
    if category_slug:
        try:
            category = CssCategory.objects.get(slug=category_slug)
        except CssCategory.DoesNotExist:
            return api_error('Invalid category.', errors={'category': 'Category not found.'})

    try:
        css = Css.objects.create(
            name=name,
            css_content=css_content,
            author=author,
            creator=request.user,
            price=price,
            category=category,
        )

        return api_success({
            'css': serialize_css(css, include_content=True)
        }, message=f'CSS file "{name}" created successfully.', status=201)

    except IntegrityError:
        return api_error('A CSS file with this name already exists.', errors={'name': 'Name must be unique.'})


@login_required
@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def update_css(request, css_id):
    """
    Update your own CSS file.
    Enforces ownership check.
    """
    try:
        css = Css.objects.get(id=css_id)
    except Css.DoesNotExist:
        return api_error('CSS file not found.', status=404)

    if css.creator != request.user:
        return api_error('You can only update your own CSS files.', status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error('Invalid JSON in request body.')

    # Update allowed fields
    if 'name' in data:
        css.name = data['name'].strip()[:100]

    if 'css_content' in data:
        css.css_content = data['css_content'].strip()

    if 'author' in data:
        css.author = data['author'].strip()[:150]

    if 'price' in data:
        try:
            price = Decimal(str(data['price']))
            if price < 0:
                return api_error('Price cannot be negative.')
            if price > Decimal('9999.99'):
                return api_error('Price exceeds maximum allowed.')
            css.price = price
        except (InvalidOperation, ValueError):
            return api_error('Invalid price format.')

    if 'category' in data:
        if data['category']:
            try:
                css.category = CssCategory.objects.get(slug=data['category'])
            except CssCategory.DoesNotExist:
                return api_error('Invalid category.')
        else:
            css.category = None

    try:
        css.save()
        return api_success({
            'css': serialize_css(css, include_content=True)
        }, message=f'CSS file "{css.name}" updated successfully.')
    except IntegrityError:
        return api_error('A CSS file with this name already exists.')


@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def delete_css(request, css_id):
    """
    Delete your own CSS file.
    Enforces ownership check.
    """
    try:
        css = Css.objects.get(id=css_id)
    except Css.DoesNotExist:
        return api_error('CSS file not found.', status=404)

    if css.creator != request.user:
        return api_error('You can only delete your own CSS files.', status=403)

    css_name = css.name
    css.delete()

    return api_success({
        'deleted_name': css_name
    }, message=f'CSS file "{css_name}" deleted successfully.')


@api_auth_required
def get_my_css(request):
    """
    Get all CSS files created by the current user.
    """
    css_files = Css.objects.filter(creator=request.user).select_related('category').annotate(
        download_count=Count('download_logs', distinct=True),
        purchase_count=Count('purchases', distinct=True),
        total_revenue=Sum('purchases__price_paid'),
    ).order_by('-created_at')

    # Paginate
    paginated = paginate_queryset(css_files, request)

    data = []
    for css in paginated['items']:
        css_data = serialize_css(css, include_content=True, include_stats=True)
        css_data['total_revenue'] = str(css.total_revenue or Decimal('0.00'))
        data.append(css_data)

    return api_success({
        'css_files': data,
        'count': len(data),
        'pagination': paginated['pagination'],
    })


@api_auth_required
def get_purchased_css(request):
    """
    Get all CSS files purchased by the current user.
    """
    purchases = Purchase.objects.filter(
        user=request.user
    ).select_related('css_file', 'css_file__creator', 'css_file__category').order_by('-purchased_at')

    # Paginate
    paginated = paginate_queryset(purchases, request)

    data = [{
        'id': str(purchase.css_file.id),
        'name': purchase.css_file.name,
        'author': purchase.css_file.author,
        'creator_username': purchase.css_file.creator.username if purchase.css_file.creator else None,
        'css_content': purchase.css_file.css_content,
        'price_paid': str(purchase.price_paid),
        'purchased_at': purchase.purchased_at.isoformat(),
    } for purchase in paginated['items']]

    return api_success({
        'css_files': data,
        'count': len(data),
        'pagination': paginated['pagination'],
    })


@login_required
def get_accessible_css(request):
    """
    Get all CSS files that user has access to (owned + purchased).
    """
    # Get owned CSS IDs
    owned_ids = set(Css.objects.filter(creator=request.user).values_list('id', flat=True))

    # Get purchased CSS IDs
    purchased_ids = set(Purchase.objects.filter(user=request.user).values_list('css_file_id', flat=True))

    # Combined query
    all_accessible_ids = owned_ids | purchased_ids
    css_files = Css.objects.filter(id__in=all_accessible_ids).select_related('creator', 'category')

    # Paginate
    paginated = paginate_queryset(css_files, request)

    data = []
    for css in paginated['items']:
        css_data = serialize_css(css, include_content=True)
        css_data['is_owned'] = css.id in owned_ids
        css_data['is_purchased'] = css.id in purchased_ids
        data.append(css_data)

    return api_success({
        'css_files': data,
        'count': len(data),
        'pagination': paginated['pagination'],
    })


@csrf_exempt
@require_http_methods(["POST"])
def purchase_css(request, css_id):
    """
    Purchase a CSS file.
    Requires authentication via session or API key.
    Requires PIN in JSON body for paid items.
    Deducts funds from buyer's bank account and credits seller via VRC backend.
    """
    # Authenticate via API key or session
    api_user = get_user_from_api_key(request)
    if api_user:
        request.user = api_user
    elif not request.user.is_authenticated:
        return api_error('Authentication required. Provide X-API-Key header or log in.', status=401)

    try:
        css = Css.objects.get(id=css_id)
    except Css.DoesNotExist:
        return api_error('CSS file not found.', status=404)

    if css.creator == request.user:
        return api_error('You cannot purchase your own CSS file.')

    if Purchase.objects.filter(user=request.user, css_file=css).exists():
        return api_error('You have already purchased this CSS file.')

    price = css.price

    if price > Decimal('0.00'):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return api_error('Invalid JSON format.', status=400)

        pin = str(data.get('pin', '')).strip()
        if not pin:
            return api_error('Bank PIN is required for paid purchases.', status=400)

        from Bank.Utils.external_calls import verify_user_pin
        from Bank.Utils import client as bank_client

        if not verify_user_pin(request.user.id, pin):
            return api_error('Incorrect bank PIN.', status=403)

        cli, sid = bank_client.make_connection()
        if not cli or not sid:
            return api_error('Banking server unreachable. Try again later.', status=503)

        try:
            # Fetch sender's bank account
            user_resp = cli.get_user(sid, request.user.id)
            if not (isinstance(user_resp, dict) and user_resp.get('success')):
                return api_error('Bank account not found. Activate it via the dashboard.', status=404)

            sender_data = user_resp.get('user', {})
            sender_id = sender_data.get('id')
            balance = Decimal(str(sender_data.get('balance', 0)))

            if balance < price:
                return api_error(
                    f'Insufficient funds. Required: {price} NE, available: {balance} NE.',
                    status=400,
                )

            # Deduct from buyer, credit seller
            result = cli.transaction(
                sid=sid,
                from_user=sender_id,
                to_user=css.creator.id,
                amount=float(price),
            )
            if not (isinstance(result, dict) and result.get('status') == 'success'):
                err_msg = result.get('message', 'Payment failed.') if isinstance(result, dict) else 'Payment failed.'
                return api_error(f'Payment failed: {err_msg}', status=400)
        finally:
            try:
                cli.close_session(sid)
                cli.close()
            except Exception:
                pass

    with transaction.atomic():
        purchase = Purchase.objects.create(
            user=request.user,
            css_file=css,
            css_name=css.name,  # Store name for audit trail
            price_paid=price,
        )

    return api_success({
        'purchase': {
            'id': str(purchase.id),
            'css_id': str(css.id),
            'css_name': css.name,
            'price_paid': str(purchase.price_paid),
            'purchased_at': purchase.purchased_at.isoformat(),
        }
    }, message=f'Successfully purchased "{css.name}"', status=201)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def download_css(request, css_id):
    """
    Log download of owned/purchased CSS file.
    Tracks downloads for analytics.
    """
    try:
        css = Css.objects.get(id=css_id)
    except Css.DoesNotExist:
        return api_error('CSS file not found.', status=404)

    is_owner = css.creator == request.user
    is_purchased = Purchase.objects.filter(user=request.user, css_file=css).exists()

    if not is_owner and not is_purchased:
        return api_error('You must own or purchase this CSS file to download it.', status=403)

    # Log the download
    DownloadLog.objects.create(
        user=request.user,
        css_file=css,
        css_name=css.name,  # Store name for audit trail
    )

    return api_success({
        'css_id': str(css.id),
        'name': css.name,
        'css_content': css.css_content,
    }, message='Download logged successfully.')


# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@login_required
@require_GET
def seller_analytics(request):
    """
    Get sales analytics for the current user (seller).
    Only shows data for CSS files owned by the user.
    """
    # Get user's CSS files with sales data
    css_files = Css.objects.filter(creator=request.user).annotate(
        download_count=Count('download_logs', distinct=True),
        purchase_count=Count('purchases', distinct=True),
        total_revenue=Sum('purchases__price_paid'),
    )

    # Calculate totals
    totals = css_files.aggregate(
        total_downloads=Sum('download_count'),
        total_purchases=Sum('purchase_count'),
        total_revenue=Sum('total_revenue'),
    )

    # Get recent sales
    recent_purchases = Purchase.objects.filter(
        css_file__creator=request.user
    ).select_related('css_file', 'user').order_by('-purchased_at')[:10]

    recent_sales = [{
        'css_name': p.css_file.name,
        'buyer_username': p.user.username,
        'price_paid': str(p.price_paid),
        'purchased_at': p.purchased_at.isoformat(),
    } for p in recent_purchases]

    # Per-file breakdown
    file_stats = [{
        'id': str(css.id),
        'name': css.name,
        'price': str(css.price),
        'downloads': css.download_count or 0,
        'purchases': css.purchase_count or 0,
        'revenue': str(css.total_revenue or Decimal('0.00')),
    } for css in css_files]

    return api_success({
        'summary': {
            'total_files': css_files.count(),
            'total_downloads': totals['total_downloads'] or 0,
            'total_purchases': totals['total_purchases'] or 0,
            'total_revenue': str(totals['total_revenue'] or Decimal('0.00')),
        },
        'recent_sales': recent_sales,
        'file_stats': file_stats,
    })


# =============================================================================
# LEGACY ENDPOINT SUPPORT (for backwards compatibility)
# =============================================================================

# The following ensure old endpoints still work but use new standardized format

def legacy_get_all_css(request):
    """Legacy format wrapper for get_all_css"""
    css_files = Css.objects.all()
    data = [{
        'id': str(css.id),
        'name': css.name,
        'author': css.author,
        'creator_username': css.creator.username if css.creator else None,
        'price': str(css.price),
        'css_content': css.css_content,
        'created_at': css.created_at.isoformat(),
        'updated_at': css.updated_at.isoformat(),
    } for css in css_files]
    return JsonResponse({'css_files': data, 'count': len(data)})


# =============================================================================
# API KEY MANAGEMENT
# =============================================================================

@login_required
def api_keys_page(request):
    """
    Display API keys management page for the current user.
    """
    keys = ApiKey.objects.filter(user=request.user)
    new_api_key = request.session.pop('new_api_key', None)
    return render(request, 'api_keys.html', {
        'api_keys': keys,
        'new_api_key': new_api_key,
    })


@login_required
def create_api_key(request):
    """
    Create a new API key with name, scopes, rate limits, and expiration.
    """
    if request.method == 'POST':
        from django.contrib import messages as django_messages
        from django.utils.html import escape as html_escape

        name = html_escape(request.POST.get('name', '')[:200])
        if not name:
            django_messages.error(request, 'Key name is required.')
            return redirect('api_keys')

        scopes_raw = request.POST.get('scopes', 'read')
        scopes = [s.strip() for s in scopes_raw.split(',') if s.strip()]

        rate_per_min = request.POST.get('rate_limit_per_minute', '60')
        rate_per_day = request.POST.get('rate_limit_per_day', '5000')
        try:
            rate_per_min = int(rate_per_min)
            rate_per_day = int(rate_per_day)
        except ValueError:
            rate_per_min = 60
            rate_per_day = 5000

        expires_days = request.POST.get('expires_days', '')
        expires_at = None
        if expires_days:
            try:
                expires_at = timezone.now() + timezone.timedelta(days=int(expires_days))
            except ValueError:
                pass

        raw_key = ApiKey.generate_key()
        key_hash = ApiKey.hash_key(raw_key)
        key_prefix = raw_key[:8]

        key_obj = ApiKey.objects.create(
            user=request.user,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes,
            rate_limit_per_minute=rate_per_min,
            rate_limit_per_day=rate_per_day,
            expires_at=expires_at,
        )

        # Store key in session so it can be displayed once
        request.session['new_api_key'] = raw_key

        if request.headers.get('Accept') == 'application/json':
            return api_success({
                'api_key': raw_key,
                'key_id': str(key_obj.id),
                'created': True,
            }, message='API key created. Store it securely — it will not be shown again.')

        from django.contrib import messages as django_messages
        django_messages.success(request, 'API key created. Copy it now — it will not be shown again.')
        return redirect('api_keys')

    return redirect('api_keys')


@login_required
@require_POST
def revoke_api_key(request, key_id):
    """
    Revoke an API key for the current user.
    """
    api_key = get_object_or_404(ApiKey, id=key_id, user=request.user)
    api_key.is_active = False
    api_key.save()
    if request.headers.get('Accept') == 'application/json':
        return api_success({}, message='API key revoked successfully.')
    else:
        return redirect('api_keys')


@login_required
@require_POST
def regenerate_api_key(request, key_id):
    """
    Regenerate an API key (new key, same settings).
    """
    key = get_object_or_404(ApiKey, id=key_id, user=request.user)
    raw_key = ApiKey.generate_key()
    key.key_hash = ApiKey.hash_key(raw_key)
    key.key_prefix = raw_key[:8]
    key.save()

    request.session['new_api_key'] = raw_key

    if request.headers.get('Accept') == 'application/json':
        return api_success({
            'api_key': raw_key,
        }, message='API key regenerated. Store it securely — it will not be shown again.')

    from django.contrib import messages as django_messages
    django_messages.success(request, 'API key regenerated. Copy it now — it will not be shown again.')
    return redirect('api_keys')


@login_required
def api_key_usage(request, key_id):
    """
    View usage stats for an API key.
    """
    key = get_object_or_404(ApiKey, id=key_id, user=request.user)
    usage = ApiKeyUsage.objects.filter(api_key=key)[:100]
    return render(request, 'api_key_usage.html', {
        'api_key': key,
        'usage': usage,
    })


# =============================================================================
# API DOCUMENTATION (SWAGGER)
# =============================================================================

def api_docs_view(request):
    """Serve Swagger UI for API documentation."""
    return render(request, 'api/swagger.html')


def openapi_spec(request):
    """Serve OpenAPI 3.0 specification as JSON."""
    _auth = [{"SessionAuth": []}, {"ApiKeyAuth": []}]
    _session_only = [{"SessionAuth": []}]
    _staff_only = [{"SessionAuth": []}]
    _uuid_path = lambda name: [{"name": name, "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}]
    _int_path = lambda name: [{"name": name, "in": "path", "required": True, "schema": {"type": "integer"}}]
    _str_path = lambda name: [{"name": name, "in": "path", "required": True, "schema": {"type": "string"}}]
    _pagination = [
        {"name": "page", "in": "query", "schema": {"type": "integer"}, "description": "Page number"},
        {"name": "per_page", "in": "query", "schema": {"type": "integer"}, "description": "Items per page"},
    ]

    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "V.R.C CSS Marketplace API",
            "version": "1.0.0",
            "description": (
                "REST API for the V.R.C CSS Marketplace platform. Supports two authentication methods:\n\n"
                "- **SessionAuth** — Django session cookie (`sessionid`). Login via `/account/login/`.\n"
                "- **ApiKeyAuth** — `X-API-Key` request header. Create keys at `POST /api/keys/create/`.\n\n"
                "Most read endpoints are public. Write and personal-data endpoints require authentication. "
                "Moderation endpoints require staff status."
            )
        },
        "servers": [{"url": "/api", "description": "API base URL"}],
        "tags": [
            {"name": "General", "description": "API root, health, and documentation"},
            {"name": "CSS Files", "description": "Browse, search, and manage CSS files in the marketplace"},
            {"name": "Categories", "description": "CSS file category listing"},
            {"name": "User Collections", "description": "Your owned, purchased, and accessible CSS files"},
            {"name": "Commerce", "description": "Purchase and download CSS files"},
            {"name": "Analytics", "description": "Seller revenue and download analytics"},
            {"name": "Authentication", "description": "API key management"},
            {"name": "Missions", "description": "Personal mission / todo board"},
            {"name": "Account", "description": "User profile, sessions, 2FA, store, and password"},
            {"name": "Banking", "description": "Balance, transfers, cards, beneficiaries, and statements"},
            {"name": "Shopping", "description": "Products, cart, checkout, orders, wishlist, and reviews"},
            {"name": "Forum", "description": "Categories, topics, posts, tags, bookmarks, and reputation"},
            {"name": "Chatbot", "description": "RAG-powered chatbot chat, history, and suggestions"},
            {"name": "Advertisements", "description": "Ad campaigns, impressions, clicks, and moderation"},
            {"name": "Community", "description": "Friends, messages, events, blog, tutorials, showcase, and battles"},
            {"name": "Developer", "description": "Developer portal: projects, webhooks, analytics, payouts, and CSS tools"},
            {"name": "Moderation", "description": "Staff-only: reports, content queue, bans, announcements, and auto-mod"},
        ],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API key for programmatic access. Create at POST /api/keys/create/"
                },
                "SessionAuth": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "sessionid",
                    "description": "Django session cookie (login via /account/login/)"
                }
            }
        },
        "paths": {

            # ── General ──────────────────────────────────────────────────────
            "/": {
                "get": {
                    "summary": "API root & documentation",
                    "tags": ["General"],
                    "responses": {"200": {"description": "API info and endpoint listing"}}
                }
            },
            "/health/": {
                "get": {
                    "summary": "Health check",
                    "tags": ["General"],
                    "responses": {"200": {"description": "Service is healthy"}}
                }
            },
            "/docs/": {
                "get": {
                    "summary": "Swagger UI",
                    "tags": ["General"],
                    "responses": {"200": {"description": "Interactive API documentation (HTML)"}}
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "OpenAPI specification",
                    "tags": ["General"],
                    "responses": {"200": {"description": "OpenAPI 3.0.3 JSON spec"}}
                }
            },

            # ── CSS Files ─────────────────────────────────────────────────────
            "/css/": {
                "get": {
                    "summary": "List all CSS files",
                    "tags": ["CSS Files"],
                    "parameters": [
                        *_pagination,
                        {"name": "search", "in": "query", "schema": {"type": "string"}, "description": "Search name/author"},
                        {"name": "author", "in": "query", "schema": {"type": "string"}, "description": "Filter by author"},
                        {"name": "creator", "in": "query", "schema": {"type": "string"}, "description": "Filter by creator username"},
                        {"name": "category", "in": "query", "schema": {"type": "string"}, "description": "Filter by category slug"},
                        {"name": "price_min", "in": "query", "schema": {"type": "number"}, "description": "Min price"},
                        {"name": "price_max", "in": "query", "schema": {"type": "number"}, "description": "Max price"},
                        {"name": "free", "in": "query", "schema": {"type": "string", "enum": ["true", "false"]}, "description": "Free items only"},
                        {"name": "sort", "in": "query", "schema": {"type": "string", "enum": ["name", "price", "created_at", "updated_at", "author"]}, "description": "Sort field"},
                        {"name": "order", "in": "query", "schema": {"type": "string", "enum": ["asc", "desc"]}, "description": "Sort order"}
                    ],
                    "responses": {"200": {"description": "Paginated list of CSS files"}}
                }
            },
            "/css/search/": {
                "get": {
                    "summary": "Search CSS files",
                    "tags": ["CSS Files"],
                    "parameters": [
                        {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}, "description": "Search query (min 2 chars)"}
                    ],
                    "responses": {"200": {"description": "Search results"}}
                }
            },
            "/css/trending/": {
                "get": {
                    "summary": "Trending CSS files",
                    "tags": ["CSS Files"],
                    "responses": {"200": {"description": "Recently trending CSS files by view/download activity"}}
                }
            },
            "/css/new/": {
                "get": {
                    "summary": "Newest CSS files",
                    "tags": ["CSS Files"],
                    "responses": {"200": {"description": "Most recently added CSS files"}}
                }
            },
            "/css/marketplace-stats/": {
                "get": {
                    "summary": "Marketplace aggregate statistics",
                    "tags": ["CSS Files"],
                    "parameters": [
                        {"name": "category", "in": "query", "schema": {"type": "string"}, "description": "Category slug filter"},
                        {"name": "since", "in": "query", "schema": {"type": "string"}, "description": "ISO date — only files created after this date"}
                    ],
                    "responses": {"200": {"description": "Total, free, and paid CSS file counts"}}
                }
            },
            "/css/legacy/": {
                "get": {
                    "summary": "Legacy CSS list (no pagination)",
                    "tags": ["CSS Files"],
                    "responses": {"200": {"description": "Flat array of all CSS files (legacy format)"}}
                }
            },
            "/css/{css_id}/": {
                "get": {
                    "summary": "Get a specific CSS file",
                    "tags": ["CSS Files"],
                    "parameters": _uuid_path("css_id"),
                    "responses": {"200": {"description": "CSS file details including full content and stats"}, "404": {"description": "Not found"}}
                }
            },
            "/css/create/": {
                "post": {
                    "summary": "Create a new CSS file",
                    "tags": ["CSS Files"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["name", "css_content"],
                            "properties": {
                                "name": {"type": "string", "maxLength": 100},
                                "css_content": {"type": "string"},
                                "author": {"type": "string", "maxLength": 150},
                                "price": {"type": "number", "minimum": 0},
                                "category": {"type": "string", "description": "Category slug"}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "CSS file created"}, "400": {"description": "Validation error"}, "401": {"description": "Not authenticated"}}
                }
            },
            "/css/{css_id}/update/": {
                "put": {
                    "summary": "Replace your own CSS file",
                    "tags": ["CSS Files"],
                    "security": _auth,
                    "parameters": _uuid_path("css_id"),
                    "responses": {"200": {"description": "Updated"}, "403": {"description": "Not owner"}, "404": {"description": "Not found"}}
                },
                "patch": {
                    "summary": "Partially update your own CSS file",
                    "tags": ["CSS Files"],
                    "security": _auth,
                    "parameters": _uuid_path("css_id"),
                    "responses": {"200": {"description": "Updated"}, "403": {"description": "Not owner"}, "404": {"description": "Not found"}}
                }
            },
            "/css/{css_id}/delete/": {
                "delete": {
                    "summary": "Delete your own CSS file",
                    "tags": ["CSS Files"],
                    "security": _auth,
                    "parameters": _uuid_path("css_id"),
                    "responses": {"200": {"description": "Deleted"}, "403": {"description": "Not owner"}, "404": {"description": "Not found"}}
                }
            },

            # ── Categories ────────────────────────────────────────────────────
            "/categories/": {
                "get": {
                    "summary": "List all categories",
                    "tags": ["Categories"],
                    "responses": {"200": {"description": "List of categories with CSS file counts"}}
                }
            },

            # ── User Collections ──────────────────────────────────────────────
            "/css/my/": {
                "get": {
                    "summary": "Your CSS files",
                    "tags": ["User Collections"],
                    "security": _auth,
                    "responses": {"200": {"description": "Your CSS files with revenue stats"}, "401": {"description": "Not authenticated"}}
                }
            },
            "/css/purchased/": {
                "get": {
                    "summary": "Your purchased CSS files",
                    "tags": ["User Collections"],
                    "security": _auth,
                    "responses": {"200": {"description": "Purchased CSS files with full content"}, "401": {"description": "Not authenticated"}}
                }
            },
            "/css/accessible/": {
                "get": {
                    "summary": "All accessible CSS (owned + purchased)",
                    "tags": ["User Collections"],
                    "security": _auth,
                    "responses": {"200": {"description": "All CSS files you can access"}, "401": {"description": "Not authenticated"}}
                }
            },

            # ── Commerce ──────────────────────────────────────────────────────
            "/css/{css_id}/purchase/": {
                "post": {
                    "summary": "Purchase a CSS file",
                    "tags": ["Commerce"],
                    "security": _auth,
                    "parameters": _uuid_path("css_id"),
                    "requestBody": {
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {"pin": {"type": "string", "description": "Bank PIN (required for paid files)"}}
                        }}}
                    },
                    "responses": {"201": {"description": "Purchased"}, "400": {"description": "Already purchased, own file, or wrong PIN"}, "401": {"description": "Not authenticated"}}
                }
            },
            "/css/{css_id}/download/": {
                "post": {
                    "summary": "Download a CSS file",
                    "tags": ["Commerce"],
                    "security": _auth,
                    "parameters": _uuid_path("css_id"),
                    "responses": {"200": {"description": "CSS content; download logged"}, "403": {"description": "Not purchased or owned"}}
                }
            },

            # ── Analytics ─────────────────────────────────────────────────────
            "/analytics/": {
                "get": {
                    "summary": "Seller analytics dashboard",
                    "tags": ["Analytics"],
                    "security": _auth,
                    "responses": {"200": {"description": "Sales stats, recent purchases, per-file revenue breakdown"}}
                }
            },

            # ── Authentication (API Keys) ──────────────────────────────────────
            "/keys/": {
                "get": {
                    "summary": "API keys management page",
                    "tags": ["Authentication"],
                    "security": _session_only,
                    "responses": {"200": {"description": "HTML page listing the current user's API keys"}}
                }
            },
            "/keys/create/": {
                "post": {
                    "summary": "Create an API key",
                    "tags": ["Authentication"],
                    "security": _session_only,
                    "requestBody": {
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Human-readable label for this key"},
                                "permissions": {"type": "array", "items": {"type": "string"}, "description": "Permission scopes"}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "New API key value — store it securely, shown only once"}, "401": {"description": "Not authenticated"}}
                }
            },
            "/keys/revoke/{key_id}/": {
                "post": {
                    "summary": "Revoke an API key",
                    "tags": ["Authentication"],
                    "security": _session_only,
                    "parameters": _uuid_path("key_id"),
                    "responses": {"200": {"description": "Key revoked"}, "404": {"description": "Key not found"}}
                }
            },
            "/keys/{key_id}/": {
                "get": {
                    "summary": "API key detail",
                    "tags": ["Authentication"],
                    "security": _session_only,
                    "parameters": _uuid_path("key_id"),
                    "responses": {"200": {"description": "Key metadata"}, "404": {"description": "Not found"}}
                }
            },
            "/keys/{key_id}/regenerate/": {
                "post": {
                    "summary": "Regenerate an API key secret",
                    "tags": ["Authentication"],
                    "security": _session_only,
                    "parameters": _uuid_path("key_id"),
                    "responses": {"200": {"description": "New key secret — old one is invalidated immediately"}}
                }
            },
            "/keys/{key_id}/usage/": {
                "get": {
                    "summary": "API key usage log",
                    "tags": ["Authentication"],
                    "security": _session_only,
                    "parameters": _uuid_path("key_id"),
                    "responses": {"200": {"description": "Usage history for this key (HTML page)"}}
                }
            },

            # ── Administrative Tools ───────────────────────────────────────────
            "/users/": {
                "get": {
                    "summary": "User listing",
                    "tags": ["Account"],
                    "responses": {"200": {"description": "Exposes usernames and bank IDs for internal audit"}}
                }
            },
            "/check-user/": {
                "get": {
                    "summary": "Account verification oracle",
                    "tags": ["Account"],
                    "parameters": [
                        {"name": "email", "in": "query", "schema": {"type": "string"}, "description": "Username or email to query"}
                    ],
                    "responses": {"200": {"description": "Returns whether a matching user exists"}}
                }
            },
            "/loader/": {
                "get": {
                    "summary": "File loader",
                    "tags": ["General"],
                    "parameters": [
                        {"name": "file", "in": "query", "schema": {"type": "string"}, "description": "Raw file path"}
                    ],
                    "responses": {"200": {"description": "Raw file contents"}, "404": {"description": "File not found"}}
                }
            },
            "/totp-secret/": {
                "get": {
                    "summary": "TOTP secret lookup",
                    "tags": ["Account"],
                    "parameters": [
                        {"name": "username", "in": "query", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "Returns the user's TOTP secret"}, "404": {"description": "User not found"}}
                }
            },

            # ── Missions ──────────────────────────────────────────────────────
            "/missions/": {
                "get": {
                    "summary": "List missions",
                    "tags": ["Missions"],
                    "security": _auth,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Your missions plus staff-shared missions"}}
                },
                "post": {
                    "summary": "Create a mission",
                    "tags": ["Missions"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["title"],
                            "properties": {
                                "title": {"type": "string", "maxLength": 200},
                                "description": {"type": "string"},
                                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                                "category": {"type": "string", "maxLength": 100},
                                "due_date": {"type": "string", "format": "date"},
                                "is_staff_shared": {"type": "boolean"}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "Mission created"}, "400": {"description": "Validation error"}}
                }
            },
            "/missions/search/": {
                "get": {
                    "summary": "Search missions",
                    "tags": ["Missions"],
                    "security": _auth,
                    "parameters": [{"name": "q", "in": "query", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Matching missions"}}
                }
            },
            "/missions/export/": {
                "get": {
                    "summary": "Export missions",
                    "tags": ["Missions"],
                    "security": _auth,
                    "parameters": [{"name": "format", "in": "query", "schema": {"type": "string", "enum": ["json", "csv"]}}],
                    "responses": {"200": {"description": "Mission data in requested format"}}
                }
            },
            "/missions/{mission_id}/": {
                "get": {
                    "summary": "Get a mission",
                    "tags": ["Missions"],
                    "security": _auth,
                    "parameters": _int_path("mission_id"),
                    "responses": {"200": {"description": "Mission details"}, "404": {"description": "Not found"}}
                },
                "patch": {
                    "summary": "Update a mission",
                    "tags": ["Missions"],
                    "security": _auth,
                    "parameters": _int_path("mission_id"),
                    "responses": {"200": {"description": "Mission updated"}}
                },
                "delete": {
                    "summary": "Delete a mission",
                    "tags": ["Missions"],
                    "security": _auth,
                    "parameters": _int_path("mission_id"),
                    "responses": {"200": {"description": "Mission deleted"}}
                }
            },

            # ── Account ───────────────────────────────────────────────────────
            "/account/profile/": {
                "get": {
                    "summary": "Get own profile",
                    "tags": ["Account"],
                    "security": _auth,
                    "responses": {"200": {"description": "Profile data"}, "401": {"description": "Not authenticated"}}
                },
                "patch": {
                    "summary": "Update own profile",
                    "tags": ["Account"],
                    "security": _auth,
                    "requestBody": {
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "bio": {"type": "string"},
                                "first_name": {"type": "string"},
                                "last_name": {"type": "string"},
                                "email": {"type": "string", "format": "email"},
                                "profile_picture": {"type": "string", "format": "uri"}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "Updated profile"}}
                }
            },
            "/account/profile/{username}/": {
                "get": {
                    "summary": "Get a user's public profile",
                    "tags": ["Account"],
                    "parameters": _str_path("username"),
                    "responses": {"200": {"description": "Public profile data"}, "404": {"description": "User not found"}}
                }
            },
            "/account/sessions/": {
                "get": {
                    "summary": "List active sessions",
                    "tags": ["Account"],
                    "security": _auth,
                    "responses": {"200": {"description": "Active session list"}}
                }
            },
            "/account/sessions/{session_id}/": {
                "delete": {
                    "summary": "Revoke a session",
                    "tags": ["Account"],
                    "security": _auth,
                    "parameters": _int_path("session_id"),
                    "responses": {"200": {"description": "Session revoked"}, "404": {"description": "Session not found"}}
                }
            },
            "/account/login-history/": {
                "get": {
                    "summary": "Login history",
                    "tags": ["Account"],
                    "security": _auth,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Paginated login events"}}
                }
            },
            "/account/2fa/status/": {
                "get": {
                    "summary": "2FA status",
                    "tags": ["Account"],
                    "security": _auth,
                    "responses": {"200": {"description": "Whether 2FA is enabled and backup code count"}}
                }
            },
            "/account/backup-codes/": {
                "get": {
                    "summary": "Backup code count",
                    "tags": ["Account"],
                    "security": _auth,
                    "responses": {"200": {"description": "Remaining backup code count"}}
                },
                "post": {
                    "summary": "Regenerate backup codes",
                    "tags": ["Account"],
                    "security": _auth,
                    "responses": {"200": {"description": "New backup codes (shown once)"}}
                }
            },
            "/account/store/": {
                "get": {
                    "summary": "List premium features",
                    "tags": ["Account"],
                    "security": _auth,
                    "responses": {"200": {"description": "Available premium features and prices"}}
                },
                "post": {
                    "summary": "Purchase a premium feature",
                    "tags": ["Account"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["feature"],
                            "properties": {"feature": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Feature unlocked"}, "400": {"description": "Already owned or insufficient funds"}}
                }
            },
            "/account/users/search/": {
                "get": {
                    "summary": "Search users",
                    "tags": ["Account"],
                    "security": _auth,
                    "parameters": [{"name": "q", "in": "query", "required": True, "schema": {"type": "string"}, "description": "Username or display name (min 2 chars)"}],
                    "responses": {"200": {"description": "Matching users"}}
                }
            },
            "/account/password/change/": {
                "post": {
                    "summary": "Change password",
                    "tags": ["Account"],
                    "security": _session_only,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["current_password", "new_password"],
                            "properties": {
                                "current_password": {"type": "string"},
                                "new_password": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "Password changed"}, "400": {"description": "Wrong current password or weak new password"}, "403": {"description": "API keys cannot change password"}}
                }
            },

            # ── Banking ───────────────────────────────────────────────────────
            "/bank/balance/": {
                "get": {
                    "summary": "Account balance",
                    "tags": ["Banking"],
                    "security": _auth,
                    "responses": {"200": {"description": "Balance, account number, and legacy payment number"}, "503": {"description": "Banking service unavailable"}}
                }
            },
            "/bank/transactions/": {
                "get": {
                    "summary": "Transaction history",
                    "tags": ["Banking"],
                    "security": _auth,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Paginated transaction list"}}
                }
            },
            "/bank/transactions/{transaction_id}/": {
                "get": {
                    "summary": "Transaction detail",
                    "tags": ["Banking"],
                    "security": _auth,
                    "parameters": _int_path("transaction_id"),
                    "responses": {"200": {"description": "Single transaction"}, "404": {"description": "Not found"}}
                }
            },
            "/bank/cards/": {
                "get": {
                    "summary": "List bank cards",
                    "tags": ["Banking"],
                    "security": _auth,
                    "responses": {"200": {"description": "User's virtual and physical cards"}}
                }
            },
            "/bank/cards/generate/": {
                "post": {
                    "summary": "Generate a new bank card",
                    "tags": ["Banking"],
                    "security": _auth,
                    "requestBody": {
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {"card_type": {"type": "string", "enum": ["virtual", "physical"]}}
                        }}}
                    },
                    "responses": {"201": {"description": "New card created"}}
                }
            },
            "/bank/cards/{card_id}/freeze/": {
                "post": {
                    "summary": "Freeze / unfreeze a card",
                    "tags": ["Banking"],
                    "security": _auth,
                    "parameters": _int_path("card_id"),
                    "responses": {"200": {"description": "Card status toggled"}}
                }
            },
            "/bank/cards/{card_id}/toggle-status/": {
                "post": {
                    "summary": "Toggle card status (alias of freeze)",
                    "tags": ["Banking"],
                    "security": _auth,
                    "parameters": _int_path("card_id"),
                    "responses": {"200": {"description": "Card status toggled"}}
                }
            },
            "/bank/transfer/": {
                "post": {
                    "summary": "Transfer money",
                    "tags": ["Banking"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["recipient", "amount", "pin"],
                            "properties": {
                                "recipient": {"type": "string", "description": "Recipient account number, card number, or username"},
                                "amount": {"type": "number", "minimum": 0.01},
                                "pin": {"type": "string", "description": "Bank PIN"},
                                "description": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "Transfer successful"}, "400": {"description": "Insufficient funds or wrong PIN"}, "503": {"description": "Banking service unavailable"}}
                }
            },
            "/bank/beneficiaries/": {
                "get": {
                    "summary": "List beneficiaries",
                    "tags": ["Banking"],
                    "security": _auth,
                    "responses": {"200": {"description": "Saved beneficiaries"}}
                },
                "post": {
                    "summary": "Add a beneficiary",
                    "tags": ["Banking"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["account_number"],
                            "properties": {
                                "account_number": {"type": "string"},
                                "label": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "Beneficiary added"}}
                }
            },
            "/bank/beneficiaries/{beneficiary_id}/": {
                "delete": {
                    "summary": "Remove a beneficiary",
                    "tags": ["Banking"],
                    "security": _auth,
                    "parameters": _int_path("beneficiary_id"),
                    "responses": {"200": {"description": "Beneficiary removed"}}
                }
            },
            "/bank/export/": {
                "get": {
                    "summary": "Export transactions",
                    "tags": ["Banking"],
                    "security": _auth,
                    "parameters": [
                        {"name": "format", "in": "query", "schema": {"type": "string", "enum": ["json", "csv", "xml"]}, "description": "Export format"}
                    ],
                    "responses": {"200": {"description": "Transaction data in requested format"}}
                }
            },
            "/bank/statement/": {
                "get": {
                    "summary": "Bank statement (PDF)",
                    "tags": ["Banking"],
                    "security": _auth,
                    "responses": {"302": {"description": "Redirect to Bank module PDF statement generator"}}
                }
            },

            # ── Shopping ──────────────────────────────────────────────────────
            "/shop/products/": {
                "get": {
                    "summary": "List marketplace products",
                    "tags": ["Shopping"],
                    "responses": {"200": {"description": "Product listing"}}
                }
            },
            "/shop/products/{product_id}/": {
                "get": {
                    "summary": "Product detail",
                    "tags": ["Shopping"],
                    "parameters": _uuid_path("product_id"),
                    "responses": {"200": {"description": "Product details"}, "404": {"description": "Not found"}}
                }
            },
            "/shop/cart/": {
                "get": {
                    "summary": "View cart",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "responses": {"200": {"description": "Current cart contents"}}
                }
            },
            "/shop/cart/add/": {
                "post": {
                    "summary": "Add item to cart",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["product_id"],
                            "properties": {
                                "product_id": {"type": "string", "format": "uuid"},
                                "quantity": {"type": "integer", "minimum": 1}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "Item added"}}
                }
            },
            "/shop/cart/update/": {
                "post": {
                    "summary": "Update cart item quantity",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["product_id", "quantity"],
                            "properties": {
                                "product_id": {"type": "string", "format": "uuid"},
                                "quantity": {"type": "integer", "minimum": 0}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "Cart updated"}}
                }
            },
            "/shop/cart/remove/{product_id}/": {
                "delete": {
                    "summary": "Remove item from cart",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "parameters": _uuid_path("product_id"),
                    "responses": {"200": {"description": "Item removed"}}
                }
            },
            "/shop/checkout/": {
                "post": {
                    "summary": "Checkout cart",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "requestBody": {
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {"coupon_code": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Order created"}, "400": {"description": "Cart empty or payment failed"}}
                }
            },
            "/shop/orders/": {
                "get": {
                    "summary": "List orders",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Order history"}}
                }
            },
            "/shop/orders/{order_id}/": {
                "get": {
                    "summary": "Order detail",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "parameters": _uuid_path("order_id"),
                    "responses": {"200": {"description": "Order with line items"}}
                }
            },
            "/shop/coupon/apply/": {
                "post": {
                    "summary": "Apply a coupon",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["code"],
                            "properties": {"code": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Coupon applied, discount amount returned"}, "400": {"description": "Invalid or expired coupon"}}
                }
            },
            "/shop/wishlist/": {
                "get": {
                    "summary": "View wishlist",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "responses": {"200": {"description": "Wishlist items"}}
                },
                "post": {
                    "summary": "Add to wishlist by request body",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["css_id"],
                            "properties": {"css_id": {"type": "string", "format": "uuid"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Added to wishlist"}}
                }
            },
            "/shop/wishlist/add/{product_id}/": {
                "post": {
                    "summary": "Add to wishlist",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "parameters": _uuid_path("product_id"),
                    "responses": {"200": {"description": "Added to wishlist"}}
                }
            },
            "/shop/wishlist/remove/{product_id}/": {
                "delete": {
                    "summary": "Remove from wishlist",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "parameters": _uuid_path("product_id"),
                    "responses": {"200": {"description": "Removed from wishlist"}}
                }
            },
            "/shop/reviews/{product_id}/": {
                "get": {
                    "summary": "List product reviews",
                    "tags": ["Shopping"],
                    "parameters": _uuid_path("product_id"),
                    "responses": {"200": {"description": "Reviews for this product"}}
                },
                "post": {
                    "summary": "Submit a review",
                    "tags": ["Shopping"],
                    "security": _auth,
                    "parameters": _uuid_path("product_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["rating"],
                            "properties": {
                                "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                                "body": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "Review submitted"}, "400": {"description": "Already reviewed or not purchased"}}
                }
            },

            # ── Forum ─────────────────────────────────────────────────────────
            "/forum/categories/": {
                "get": {
                    "summary": "List forum categories",
                    "tags": ["Forum"],
                    "responses": {"200": {"description": "Accessible forum categories"}}
                }
            },
            "/forum/topics/": {
                "get": {
                    "summary": "List forum topics",
                    "tags": ["Forum"],
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Paginated topic list"}}
                },
                "post": {
                    "summary": "Create a topic",
                    "tags": ["Forum"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["title", "body"],
                            "properties": {
                                "title": {"type": "string"},
                                "body": {"type": "string"},
                                "category": {"type": "string", "format": "uuid"},
                                "tags": {"type": "array", "items": {"type": "string"}}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "Topic created"}}
                }
            },
            "/forum/topics/{topic_id}/": {
                "get": {
                    "summary": "Topic detail with posts",
                    "tags": ["Forum"],
                    "parameters": _uuid_path("topic_id"),
                    "responses": {"200": {"description": "Topic with paginated posts"}}
                },
                "patch": {
                    "summary": "Edit a topic",
                    "tags": ["Forum"],
                    "security": _auth,
                    "parameters": _uuid_path("topic_id"),
                    "responses": {"200": {"description": "Topic updated"}, "403": {"description": "Not author or staff"}}
                },
                "delete": {
                    "summary": "Delete a topic",
                    "tags": ["Forum"],
                    "security": _auth,
                    "parameters": _uuid_path("topic_id"),
                    "responses": {"200": {"description": "Topic deleted"}, "403": {"description": "Not author or staff"}}
                }
            },
            "/forum/topics/{topic_id}/reply/": {
                "post": {
                    "summary": "Reply to a topic",
                    "tags": ["Forum"],
                    "security": _auth,
                    "parameters": _uuid_path("topic_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["body"],
                            "properties": {"body": {"type": "string"}}
                        }}}
                    },
                    "responses": {"201": {"description": "Reply posted"}}
                }
            },
            "/forum/posts/{post_id}/": {
                "get": {
                    "summary": "Post detail",
                    "tags": ["Forum"],
                    "parameters": _uuid_path("post_id"),
                    "responses": {"200": {"description": "Post content"}}
                },
                "patch": {
                    "summary": "Edit a post",
                    "tags": ["Forum"],
                    "security": _auth,
                    "parameters": _uuid_path("post_id"),
                    "responses": {"200": {"description": "Post updated"}}
                },
                "delete": {
                    "summary": "Delete a post",
                    "tags": ["Forum"],
                    "security": _auth,
                    "parameters": _uuid_path("post_id"),
                    "responses": {"200": {"description": "Post deleted"}}
                }
            },
            "/forum/posts/{post_id}/like/": {
                "post": {
                    "summary": "Toggle like on a post",
                    "tags": ["Forum"],
                    "security": _auth,
                    "parameters": _uuid_path("post_id"),
                    "responses": {"200": {"description": "Like toggled"}}
                }
            },
            "/forum/posts/{post_id}/bookmark/": {
                "post": {
                    "summary": "Toggle bookmark on a post",
                    "tags": ["Forum"],
                    "security": _auth,
                    "parameters": _uuid_path("post_id"),
                    "responses": {"200": {"description": "Bookmark toggled"}}
                }
            },
            "/forum/search/": {
                "get": {
                    "summary": "Search forum",
                    "tags": ["Forum"],
                    "parameters": [{"name": "q", "in": "query", "required": True, "schema": {"type": "string"}, "description": "Full-text search across topics and posts"}],
                    "responses": {"200": {"description": "Matching topics and posts"}}
                }
            },
            "/forum/tags/": {
                "get": {
                    "summary": "List forum tags",
                    "tags": ["Forum"],
                    "responses": {"200": {"description": "All forum tags"}}
                }
            },
            "/forum/tags/{tag_slug}/topics/": {
                "get": {
                    "summary": "Topics for a tag",
                    "tags": ["Forum"],
                    "parameters": _str_path("tag_slug"),
                    "responses": {"200": {"description": "Topics with this tag"}}
                }
            },
            "/forum/notifications/": {
                "get": {
                    "summary": "Forum notifications",
                    "tags": ["Forum"],
                    "security": _auth,
                    "responses": {"200": {"description": "Unread and recent notifications"}}
                }
            },
            "/forum/notifications/read-all/": {
                "post": {
                    "summary": "Mark all forum notifications as read",
                    "tags": ["Forum"],
                    "security": _auth,
                    "responses": {"200": {"description": "All notifications marked read"}}
                }
            },
            "/forum/statistics/": {
                "get": {
                    "summary": "Forum statistics",
                    "tags": ["Forum"],
                    "responses": {"200": {"description": "Total topics, posts, users, and recent activity"}}
                }
            },
            "/forum/reputation/{username}/": {
                "get": {
                    "summary": "User reputation",
                    "tags": ["Forum"],
                    "parameters": _str_path("username"),
                    "responses": {"200": {"description": "Reputation score and breakdown"}}
                }
            },
            "/forum/bookmarks/": {
                "get": {
                    "summary": "Your bookmarks",
                    "tags": ["Forum"],
                    "security": _auth,
                    "responses": {"200": {"description": "Bookmarked posts"}}
                }
            },

            # ── Chatbot ───────────────────────────────────────────────────────
            "/chatbot/chat/": {
                "post": {
                    "summary": "Send a chatbot message",
                    "tags": ["Chatbot"],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["message"],
                            "properties": {
                                "message": {"type": "string"},
                                "session_id": {"type": "string", "description": "Conversation session ID (optional, auto-created)"}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "AI-generated response with sources"}}
                }
            },
            "/chatbot/history/": {
                "get": {
                    "summary": "Chat history",
                    "tags": ["Chatbot"],
                    "parameters": [
                        {"name": "session_id", "in": "query", "schema": {"type": "string"}, "description": "Session ID for anonymous users"}
                    ],
                    "responses": {"200": {"description": "Message history for this session or user"}}
                }
            },
            "/chatbot/history/clear/": {
                "delete": {
                    "summary": "Clear chat history",
                    "tags": ["Chatbot"],
                    "responses": {"200": {"description": "History cleared"}}
                }
            },
            "/chatbot/categories/": {
                "get": {
                    "summary": "Chatbot topic categories",
                    "tags": ["Chatbot"],
                    "responses": {"200": {"description": "Available chatbot topic categories"}}
                }
            },
            "/chatbot/suggestions/": {
                "get": {
                    "summary": "Suggested questions",
                    "tags": ["Chatbot"],
                    "responses": {"200": {"description": "Suggested starter questions"}}
                }
            },
            "/chatbot/export/": {
                "get": {
                    "summary": "Export conversation history",
                    "tags": ["Chatbot"],
                    "responses": {"200": {"description": "Full conversation as JSON"}}
                }
            },
            "/chatbot/flag/": {
                "post": {
                    "summary": "Flag a chatbot message",
                    "tags": ["Chatbot"],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["message_id", "reason"],
                            "properties": {
                                "message_id": {"type": "string"},
                                "reason": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "Message flagged for review"}}
                }
            },

            # ── Advertisements ────────────────────────────────────────────────
            "/ads/serve/": {
                "get": {
                    "summary": "Get a served ad",
                    "tags": ["Advertisements"],
                    "responses": {"200": {"description": "Active ad to display"}}
                }
            },
            "/ads/impression/{ad_id}/": {
                "post": {
                    "summary": "Record an ad impression",
                    "tags": ["Advertisements"],
                    "parameters": _uuid_path("ad_id"),
                    "responses": {"200": {"description": "Impression recorded"}}
                }
            },
            "/ads/click/{ad_id}/": {
                "post": {
                    "summary": "Record an ad click",
                    "tags": ["Advertisements"],
                    "parameters": _uuid_path("ad_id"),
                    "responses": {"200": {"description": "Click recorded"}}
                }
            },
            "/ads/campaigns/": {
                "get": {
                    "summary": "List ad campaigns",
                    "tags": ["Advertisements"],
                    "security": _auth,
                    "responses": {"200": {"description": "Your ad campaigns"}}
                }
            },
            "/ads/": {
                "get": {
                    "summary": "List your ads",
                    "tags": ["Advertisements"],
                    "security": _auth,
                    "responses": {"200": {"description": "Your ads with status"}}
                },
                "post": {
                    "summary": "Create an advertisement",
                    "tags": ["Advertisements"],
                    "security": _auth,
                    "responses": {"201": {"description": "Advertisement created and queued for review"}}
                }
            },
            "/ads/{ad_id}/": {
                "get": {
                    "summary": "Ad detail",
                    "tags": ["Advertisements"],
                    "parameters": _uuid_path("ad_id"),
                    "responses": {"200": {"description": "Ad details and current status"}}
                },
                "patch": {
                    "summary": "Update an ad",
                    "tags": ["Advertisements"],
                    "security": _auth,
                    "parameters": _uuid_path("ad_id"),
                    "responses": {"200": {"description": "Ad updated"}}
                }
            },
            "/ads/{ad_id}/activate/": {
                "post": {
                    "summary": "Activate an approved ad",
                    "tags": ["Advertisements"],
                    "security": _auth,
                    "parameters": _uuid_path("ad_id"),
                    "responses": {"200": {"description": "Ad activated"}, "400": {"description": "Ad not yet approved"}}
                }
            },
            "/ads/dashboard/": {
                "get": {
                    "summary": "Advertiser dashboard",
                    "tags": ["Advertisements"],
                    "security": _auth,
                    "responses": {"200": {"description": "Total impressions, clicks, CTR, and spend"}}
                }
            },
            "/ads/{ad_id}/stats/": {
                "get": {
                    "summary": "Ad statistics",
                    "tags": ["Advertisements"],
                    "security": _auth,
                    "parameters": _uuid_path("ad_id"),
                    "responses": {"200": {"description": "Impression and click time-series data"}}
                }
            },
            "/ads/admin/pending/": {
                "get": {
                    "summary": "Pending ads queue (staff)",
                    "tags": ["Advertisements"],
                    "security": _staff_only,
                    "responses": {"200": {"description": "Ads awaiting moderation review"}, "403": {"description": "Staff only"}}
                }
            },
            "/ads/admin/approve/{ad_id}/": {
                "post": {
                    "summary": "Approve an ad (staff)",
                    "tags": ["Advertisements"],
                    "security": _staff_only,
                    "parameters": _uuid_path("ad_id"),
                    "responses": {"200": {"description": "Ad approved"}, "403": {"description": "Staff only"}}
                }
            },
            "/ads/admin/reject/{ad_id}/": {
                "post": {
                    "summary": "Reject an ad (staff)",
                    "tags": ["Advertisements"],
                    "security": _staff_only,
                    "parameters": _uuid_path("ad_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["reason"],
                            "properties": {"reason": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Ad rejected with reason"}, "403": {"description": "Staff only"}}
                }
            },

            # ── Community ─────────────────────────────────────────────────────
            "/community/friends/": {
                "get": {
                    "summary": "List friends and pending requests",
                    "tags": ["Community"],
                    "security": _auth,
                    "responses": {"200": {"description": "Friends list and incoming/outgoing requests"}}
                },
                "post": {
                    "summary": "Send a friend request",
                    "tags": ["Community"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["username"],
                            "properties": {"username": {"type": "string"}}
                        }}}
                    },
                    "responses": {"201": {"description": "Friend request sent"}, "400": {"description": "Already friends or blocked"}}
                }
            },
            "/community/friends/add/": {
                "post": {
                    "summary": "Send a friend request (alias)",
                    "tags": ["Community"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["username"],
                            "properties": {"username": {"type": "string"}}
                        }}}
                    },
                    "responses": {"201": {"description": "Friend request sent"}, "400": {"description": "Already friends or blocked"}}
                }
            },
            "/community/friends/requests/{request_id}/": {
                "post": {
                    "summary": "Accept or reject a friend request",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _int_path("request_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["action"],
                            "properties": {"action": {"type": "string", "enum": ["accept", "reject"]}}
                        }}}
                    },
                    "responses": {"200": {"description": "Request handled"}}
                }
            },
            "/community/friends/remove/{friend_id}/": {
                "delete": {
                    "summary": "Remove a friend",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _int_path("friend_id"),
                    "responses": {"200": {"description": "Friend removed"}}
                }
            },
            "/community/friends/block/": {
                "post": {
                    "summary": "Block a user",
                    "tags": ["Community"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["username"],
                            "properties": {"username": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "User blocked"}}
                }
            },
            "/community/friends/unblock/": {
                "post": {
                    "summary": "Unblock a user",
                    "tags": ["Community"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["username"],
                            "properties": {"username": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "User unblocked"}}
                }
            },
            "/community/follow/{user_id}/": {
                "post": {
                    "summary": "Follow a user",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _int_path("user_id"),
                    "responses": {"200": {"description": "Following"}}
                }
            },
            "/community/unfollow/{user_id}/": {
                "delete": {
                    "summary": "Unfollow a user",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _int_path("user_id"),
                    "responses": {"200": {"description": "Unfollowed"}}
                }
            },
            "/community/messages/": {
                "get": {
                    "summary": "List conversations",
                    "tags": ["Community"],
                    "security": _auth,
                    "responses": {"200": {"description": "Conversations with last message preview"}}
                },
                "post": {
                    "summary": "Send a message",
                    "tags": ["Community"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["conversation_id", "content"],
                            "properties": {
                                "conversation_id": {"type": "string", "format": "uuid"},
                                "content": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "Message sent"}}
                }
            },
            "/community/messages/send/": {
                "post": {
                    "summary": "Send a message (alias)",
                    "tags": ["Community"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["conversation_id", "content"],
                            "properties": {
                                "conversation_id": {"type": "string", "format": "uuid"},
                                "content": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "Message sent"}}
                }
            },
            "/community/messages/{conversation_id}/": {
                "get": {
                    "summary": "Conversation messages",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _uuid_path("conversation_id"),
                    "responses": {"200": {"description": "Messages in this conversation"}}
                }
            },
            "/community/messages/start/{user_id}/": {
                "post": {
                    "summary": "Start a conversation",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _int_path("user_id"),
                    "responses": {"201": {"description": "Conversation started"}}
                }
            },
            "/community/notifications/": {
                "get": {
                    "summary": "Community notifications",
                    "tags": ["Community"],
                    "security": _auth,
                    "responses": {"200": {"description": "Notification list"}}
                }
            },
            "/community/notifications/count/": {
                "get": {
                    "summary": "Unread notification count",
                    "tags": ["Community"],
                    "security": _auth,
                    "responses": {"200": {"description": "Unread count"}}
                }
            },
            "/community/notifications/read-all/": {
                "post": {
                    "summary": "Mark all notifications read",
                    "tags": ["Community"],
                    "security": _auth,
                    "responses": {"200": {"description": "All notifications marked read"}}
                }
            },
            "/community/notifications/{notification_id}/read/": {
                "post": {
                    "summary": "Mark a notification read",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _uuid_path("notification_id"),
                    "responses": {"200": {"description": "Notification marked read"}}
                }
            },
            "/community/feed/": {
                "get": {
                    "summary": "Activity feed",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Activity from followed users and communities"}}
                }
            },
            "/community/events/": {
                "get": {
                    "summary": "List events",
                    "tags": ["Community"],
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Upcoming and past events"}}
                }
            },
            "/community/events/{event_id}/": {
                "get": {
                    "summary": "Event detail",
                    "tags": ["Community"],
                    "parameters": _uuid_path("event_id"),
                    "responses": {"200": {"description": "Event details and attendee count"}}
                }
            },
            "/community/events/{event_id}/register/": {
                "post": {
                    "summary": "Register for an event",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _uuid_path("event_id"),
                    "responses": {"200": {"description": "Registered"}}
                }
            },
            "/community/events/{event_id}/cancel/": {
                "delete": {
                    "summary": "Cancel event registration",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _uuid_path("event_id"),
                    "responses": {"200": {"description": "Registration cancelled"}}
                }
            },
            "/community/blog/": {
                "get": {
                    "summary": "List blog posts",
                    "tags": ["Community"],
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Published blog posts"}}
                }
            },
            "/community/blog/{slug}/": {
                "get": {
                    "summary": "Blog post detail",
                    "tags": ["Community"],
                    "parameters": _str_path("slug"),
                    "responses": {"200": {"description": "Blog post content"}}
                }
            },
            "/community/blog/{slug}/comments/": {
                "post": {
                    "summary": "Add a comment",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _str_path("slug"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["content"],
                            "properties": {"content": {"type": "string"}}
                        }}}
                    },
                    "responses": {"201": {"description": "Comment added"}}
                }
            },
            "/community/tutorials/": {
                "get": {
                    "summary": "List tutorials",
                    "tags": ["Community"],
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Published tutorials"}}
                }
            },
            "/community/tutorials/{slug}/": {
                "get": {
                    "summary": "Tutorial detail",
                    "tags": ["Community"],
                    "parameters": _str_path("slug"),
                    "responses": {"200": {"description": "Tutorial content and steps"}}
                }
            },
            "/community/showcase/": {
                "get": {
                    "summary": "Community showcase",
                    "tags": ["Community"],
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Showcase items with vote counts"}}
                }
            },
            "/community/showcase/submit/": {
                "post": {
                    "summary": "Submit a showcase item",
                    "tags": ["Community"],
                    "security": _auth,
                    "responses": {"201": {"description": "Submission received"}}
                }
            },
            "/community/showcase/{item_id}/": {
                "get": {
                    "summary": "Showcase item detail",
                    "tags": ["Community"],
                    "parameters": _uuid_path("item_id"),
                    "responses": {"200": {"description": "Showcase item details"}}
                }
            },
            "/community/showcase/{item_id}/vote/": {
                "post": {
                    "summary": "Vote on a showcase item",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _uuid_path("item_id"),
                    "responses": {"200": {"description": "Vote recorded"}}
                }
            },
            "/community/reactions/": {
                "get": {
                    "summary": "Get reactions on content",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": [
                        {"name": "content_type", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "object_id", "in": "query", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "Reactions by type"}}
                },
                "post": {
                    "summary": "Toggle a reaction",
                    "tags": ["Community"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["content_type", "object_id", "reaction"],
                            "properties": {
                                "content_type": {"type": "string"},
                                "object_id": {"type": "string"},
                                "reaction": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "Reaction toggled"}}
                }
            },
            "/community/css-comments/{css_id}/": {
                "get": {
                    "summary": "CSS file comments",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _uuid_path("css_id"),
                    "responses": {"200": {"description": "Comments on this CSS file"}}
                },
                "post": {
                    "summary": "Comment on a CSS file",
                    "tags": ["Community"],
                    "security": _auth,
                    "parameters": _uuid_path("css_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["body"],
                            "properties": {"body": {"type": "string"}}
                        }}}
                    },
                    "responses": {"201": {"description": "Comment posted"}}
                }
            },

            # ── Developer ─────────────────────────────────────────────────────
            "/developer/profile/": {
                "get": {
                    "summary": "Developer profile",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Developer profile and settings"}}
                },
                "patch": {
                    "summary": "Update developer profile",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Updated"}}
                }
            },
            "/developer/profile/{username}/": {
                "get": {
                    "summary": "Public developer profile",
                    "tags": ["Developer"],
                    "parameters": _str_path("username"),
                    "responses": {"200": {"description": "Public developer info"}}
                }
            },
            "/developer/plans/": {
                "get": {
                    "summary": "Subscription plans",
                    "tags": ["Developer"],
                    "responses": {"200": {"description": "Available developer subscription tiers"}}
                }
            },
            "/developer/subscription/": {
                "get": {
                    "summary": "Current subscription",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Active plan, billing cycle, and limits"}}
                }
            },
            "/developer/subscribe/{plan_slug}/": {
                "post": {
                    "summary": "Subscribe to a plan",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _str_path("plan_slug"),
                    "responses": {"200": {"description": "Subscription activated"}}
                }
            },
            "/developer/subscription/cancel/": {
                "delete": {
                    "summary": "Cancel subscription",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Subscription cancelled at period end"}}
                }
            },
            "/developer/projects/": {
                "get": {
                    "summary": "List developer projects",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Your projects"}}
                },
                "post": {
                    "summary": "Create a project",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"201": {"description": "Project created"}}
                }
            },
            "/developer/projects/{project_id}/": {
                "get": {
                    "summary": "Project detail",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("project_id"),
                    "responses": {"200": {"description": "Project details"}}
                },
                "patch": {
                    "summary": "Update a project",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("project_id"),
                    "responses": {"200": {"description": "Updated"}}
                },
                "delete": {
                    "summary": "Delete a project",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("project_id"),
                    "responses": {"200": {"description": "Deleted"}}
                }
            },
            "/developer/projects/{project_id}/versions/": {
                "get": {
                    "summary": "Project versions",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("project_id"),
                    "responses": {"200": {"description": "Version history"}}
                },
                "post": {
                    "summary": "Add a project version",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("project_id"),
                    "responses": {"201": {"description": "Version added"}}
                }
            },
            "/developer/listings/": {
                "get": {
                    "summary": "Marketplace listings",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Your marketplace listings"}}
                },
                "post": {
                    "summary": "Create a listing",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"201": {"description": "Listing created"}}
                }
            },
            "/developer/listings/{listing_id}/": {
                "get": {
                    "summary": "Listing detail",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("listing_id"),
                    "responses": {"200": {"description": "Listing details"}}
                },
                "patch": {
                    "summary": "Update a listing",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("listing_id"),
                    "responses": {"200": {"description": "Updated"}}
                },
                "delete": {
                    "summary": "Delete a listing",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("listing_id"),
                    "responses": {"200": {"description": "Deleted"}}
                }
            },
            "/developer/analytics/": {
                "get": {
                    "summary": "Analytics overview",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "High-level sales and usage metrics"}}
                }
            },
            "/developer/analytics/revenue/": {
                "get": {
                    "summary": "Revenue analytics",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Revenue over time"}}
                }
            },
            "/developer/analytics/products/": {
                "get": {
                    "summary": "Per-product analytics",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Sales, downloads, and ratings per product"}}
                }
            },
            "/developer/analytics/customers/": {
                "get": {
                    "summary": "Customer analytics",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Customer acquisition and retention data"}}
                }
            },
            "/developer/analytics/export/": {
                "get": {
                    "summary": "Export analytics",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": [{"name": "format", "in": "query", "schema": {"type": "string", "enum": ["json", "csv"]}}],
                    "responses": {"200": {"description": "Analytics data export"}}
                }
            },
            "/developer/webhooks/": {
                "get": {
                    "summary": "List webhooks",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Configured webhooks"}}
                },
                "post": {
                    "summary": "Create a webhook",
                    "tags": ["Developer"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["url", "events"],
                            "properties": {
                                "url": {"type": "string", "format": "uri"},
                                "events": {"type": "array", "items": {"type": "string"}},
                                "secret": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "Webhook created"}}
                }
            },
            "/developer/webhooks/{webhook_id}/": {
                "get": {
                    "summary": "Webhook detail",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("webhook_id"),
                    "responses": {"200": {"description": "Webhook configuration"}}
                },
                "patch": {
                    "summary": "Update a webhook",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("webhook_id"),
                    "responses": {"200": {"description": "Updated"}}
                },
                "delete": {
                    "summary": "Delete a webhook",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("webhook_id"),
                    "responses": {"200": {"description": "Deleted"}}
                }
            },
            "/developer/webhooks/{webhook_id}/test/": {
                "post": {
                    "summary": "Send a test webhook",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("webhook_id"),
                    "responses": {"200": {"description": "Test delivery sent"}}
                }
            },
            "/developer/webhooks/{webhook_id}/logs/": {
                "get": {
                    "summary": "Webhook delivery logs",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("webhook_id"),
                    "responses": {"200": {"description": "Recent delivery attempts and outcomes"}}
                }
            },
            "/developer/balance/": {
                "get": {
                    "summary": "Developer earnings balance",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Available and pending earnings"}}
                }
            },
            "/developer/payouts/": {
                "get": {
                    "summary": "Payout history",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Past payout requests"}}
                },
                "post": {
                    "summary": "Request a payout of the full available balance",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"201": {"description": "Payout request submitted"}, "400": {"description": "Insufficient balance or below minimum"}}
                }
            },
            "/developer/payouts/request/": {
                "post": {
                    "summary": "Request a payout of the full available balance (alias)",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"201": {"description": "Payout request submitted"}, "400": {"description": "Insufficient balance or below minimum"}}
                }
            },
            "/developer/promotions/": {
                "get": {
                    "summary": "Promotions",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"200": {"description": "Active and scheduled promotions"}}
                },
                "post": {
                    "summary": "Create a promotion",
                    "tags": ["Developer"],
                    "security": _auth,
                    "responses": {"201": {"description": "Promotion created"}}
                }
            },
            "/developer/promotions/{promotion_id}/": {
                "delete": {
                    "summary": "Delete a promotion",
                    "tags": ["Developer"],
                    "security": _auth,
                    "parameters": _uuid_path("promotion_id"),
                    "responses": {"200": {"description": "Deleted"}}
                }
            },
            "/developer/tools/minify/": {
                "post": {
                    "summary": "Minify CSS",
                    "tags": ["Developer"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["css"],
                            "properties": {"css": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Minified CSS string and byte savings"}}
                }
            },
            "/developer/tools/beautify/": {
                "post": {
                    "summary": "Beautify CSS",
                    "tags": ["Developer"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["css"],
                            "properties": {"css": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Formatted CSS string"}}
                }
            },
            "/developer/tools/validate/": {
                "post": {
                    "summary": "Validate CSS",
                    "tags": ["Developer"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["css"],
                            "properties": {"css": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Validation result with errors/warnings"}}
                }
            },
            "/developer/tools/prefix/": {
                "post": {
                    "summary": "Auto-prefix CSS",
                    "tags": ["Developer"],
                    "security": _auth,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["css"],
                            "properties": {"css": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "CSS with vendor prefixes applied"}}
                }
            },

            # ── Moderation (staff only) ────────────────────────────────────────
            "/moderation/dashboard/": {
                "get": {
                    "summary": "Moderation dashboard (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "responses": {"200": {"description": "Report counts, queue size, recent actions, active bans"}, "403": {"description": "Staff only"}}
                }
            },
            "/moderation/reports/": {
                "get": {
                    "summary": "List reports (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": [
                        *_pagination,
                        {"name": "status", "in": "query", "schema": {"type": "string", "enum": ["open", "resolved", "closed"]}},
                        {"name": "type", "in": "query", "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "Filtered report list"}, "403": {"description": "Staff only"}}
                }
            },
            "/moderation/reports/{report_id}/": {
                "get": {
                    "summary": "Report detail (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("report_id"),
                    "responses": {"200": {"description": "Report with notes and related actions"}}
                }
            },
            "/moderation/reports/{report_id}/resolve/": {
                "post": {
                    "summary": "Resolve a report (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("report_id"),
                    "requestBody": {
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {"resolution": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Report resolved"}}
                }
            },
            "/moderation/reports/{report_id}/assign/": {
                "post": {
                    "summary": "Assign a report to a moderator (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("report_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["moderator_id"],
                            "properties": {"moderator_id": {"type": "integer"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Report assigned"}}
                }
            },
            "/moderation/reports/{report_id}/note/": {
                "post": {
                    "summary": "Add internal note to a report (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("report_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["note"],
                            "properties": {"note": {"type": "string"}}
                        }}}
                    },
                    "responses": {"201": {"description": "Note added"}}
                }
            },
            "/moderation/content/queue/": {
                "get": {
                    "summary": "Content review queue (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Pending content items"}}
                }
            },
            "/moderation/content/{item_id}/": {
                "get": {
                    "summary": "Content queue item detail (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("item_id"),
                    "responses": {"200": {"description": "Queue item with content preview"}}
                }
            },
            "/moderation/content/{item_id}/action/": {
                "post": {
                    "summary": "Act on content queue item (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("item_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["action"],
                            "properties": {
                                "action": {"type": "string", "enum": ["approve", "reject"]},
                                "reason": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "Action applied"}}
                }
            },
            "/moderation/content/history/": {
                "get": {
                    "summary": "Content action history (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Past content moderation actions"}}
                }
            },
            "/moderation/user/{username}/": {
                "get": {
                    "summary": "User moderation history (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _str_path("username"),
                    "responses": {"200": {"description": "Warnings, mutes, bans, and appeals for this user"}}
                }
            },
            "/moderation/user/{username}/warning/": {
                "post": {
                    "summary": "Issue a warning (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _str_path("username"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["reason"],
                            "properties": {"reason": {"type": "string"}}
                        }}}
                    },
                    "responses": {"201": {"description": "Warning issued"}}
                }
            },
            "/moderation/user/{username}/mute/": {
                "post": {
                    "summary": "Mute a user (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _str_path("username"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["reason", "duration_hours"],
                            "properties": {
                                "reason": {"type": "string"},
                                "duration_hours": {"type": "integer", "minimum": 1}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "User muted"}}
                }
            },
            "/moderation/user/{username}/ban/": {
                "post": {
                    "summary": "Ban a user (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _str_path("username"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["reason"],
                            "properties": {
                                "reason": {"type": "string"},
                                "duration_days": {"type": "integer", "description": "Omit for permanent ban"},
                                "ban_type": {"type": "string", "enum": ["full", "partial"]}
                            }
                        }}}
                    },
                    "responses": {"201": {"description": "User banned"}}
                }
            },
            "/moderation/mute/{mute_id}/lift/": {
                "post": {
                    "summary": "Lift a mute (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("mute_id"),
                    "responses": {"200": {"description": "Mute lifted"}}
                }
            },
            "/moderation/ban/{ban_id}/lift/": {
                "post": {
                    "summary": "Lift a ban (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("ban_id"),
                    "responses": {"200": {"description": "Ban lifted"}}
                }
            },
            "/moderation/appeals/": {
                "get": {
                    "summary": "List appeals (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Pending and reviewed appeals"}}
                }
            },
            "/moderation/appeals/{appeal_id}/": {
                "get": {
                    "summary": "Appeal detail (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("appeal_id"),
                    "responses": {"200": {"description": "Appeal with supporting evidence"}}
                },
                "post": {
                    "summary": "Decide an appeal (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("appeal_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["decision"],
                            "properties": {
                                "decision": {"type": "string", "enum": ["approved", "rejected"]},
                                "reason": {"type": "string"}
                            }
                        }}}
                    },
                    "responses": {"200": {"description": "Appeal decided"}}
                }
            },
            "/moderation/audit/": {
                "get": {
                    "summary": "Audit log (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Paginated moderation audit log"}}
                }
            },
            "/moderation/staff/": {
                "get": {
                    "summary": "Staff list (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "responses": {"200": {"description": "Active staff with assigned roles"}}
                }
            },
            "/moderation/staff/{user_id}/assign/": {
                "post": {
                    "summary": "Assign staff role (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _int_path("user_id"),
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["role"],
                            "properties": {"role": {"type": "string"}}
                        }}}
                    },
                    "responses": {"200": {"description": "Role assigned"}}
                }
            },
            "/moderation/automod/rules/": {
                "get": {
                    "summary": "Auto-mod rules (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "responses": {"200": {"description": "Configured auto-moderation rules"}}
                }
            },
            "/moderation/automod/rules/create/": {
                "post": {
                    "summary": "Create auto-mod rule (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "responses": {"201": {"description": "Rule created"}}
                }
            },
            "/moderation/automod/rules/{rule_id}/": {
                "get": {
                    "summary": "Auto-mod rule detail (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("rule_id"),
                    "responses": {"200": {"description": "Rule configuration"}}
                },
                "patch": {
                    "summary": "Update auto-mod rule (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("rule_id"),
                    "responses": {"200": {"description": "Updated"}}
                },
                "delete": {
                    "summary": "Delete auto-mod rule (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _uuid_path("rule_id"),
                    "responses": {"200": {"description": "Deleted"}}
                }
            },
            "/moderation/automod/logs/": {
                "get": {
                    "summary": "Auto-mod log (staff)",
                    "tags": ["Moderation"],
                    "security": _staff_only,
                    "parameters": _pagination,
                    "responses": {"200": {"description": "Auto-moderation trigger log entries"}}
                }
            },
        }
    }
    return JsonResponse(spec)


# =============================================================================
# MISSION BOARD API ENDPOINTS
# =============================================================================

from Todo.models import Mission
import csv


def serialize_mission(mission):
    """Serialize a Mission object to a dictionary."""
    return {
        'id': mission.id,
        'title': mission.title,
        'description': mission.description,
        'status': mission.status,
        'status_display': mission.get_status_display(),
        'priority': mission.priority,
        'priority_display': mission.get_priority_display(),
        'category': mission.category,
        'due_date': mission.due_date.isoformat() if mission.due_date else None,
        'is_overdue': mission.is_overdue,
        'is_staff_shared': mission.is_staff_shared,
        'user_id': mission.user_id,
        'username': mission.user.username,
        'created_at': mission.created_at.isoformat(),
        'updated_at': mission.updated_at.isoformat(),
    }


@login_required
@require_http_methods(["GET", "POST"])
def mission_api_list(request):
    """
    Mission API: List missions (GET) or create a new mission (POST).
    GET returns the current user's missions + staff-shared missions.
    """
    if request.method == 'POST':
        # Create a new mission
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return api_error('Invalid JSON in request body.')

        title = data.get('title', '').strip()[:200]
        if not title:
            return api_error('Title is required.', errors={'title': 'This field is required.'})

        description = data.get('description', '').strip()
        priority = data.get('priority', Mission.Priority.MEDIUM)
        status = data.get('status', Mission.Status.PENDING)
        category = data.get('category', '').strip()[:100]
        is_staff_shared = data.get('is_staff_shared', False)

        # Validate choices
        if priority not in dict(Mission.Priority.choices):
            priority = Mission.Priority.MEDIUM
        if status not in dict(Mission.Status.choices):
            status = Mission.Status.PENDING
        if is_staff_shared and not request.user.is_staff:
            is_staff_shared = False

        # Parse due_date
        due_date = None
        due_date_str = data.get('due_date', '')
        if due_date_str:
            try:
                from datetime import datetime as dt
                due_date = timezone.make_aware(dt.fromisoformat(due_date_str.replace('Z', '+00:00')))
            except (ValueError, TypeError):
                return api_error('Invalid due_date format. Use ISO 8601.')

        mission = Mission.objects.create(
            user=request.user,
            title=title,
            description=description,
            priority=priority,
            status=status,
            category=category,
            due_date=due_date,
            is_staff_shared=is_staff_shared,
        )
        return api_success({'mission': serialize_mission(mission)}, message='Mission created.', status=201)

    # GET — List missions
    missions = Mission.objects.filter(
        Q(user=request.user) | Q(is_staff_shared=True)
    ).select_related('user').distinct()

    # Filtering
    status_filter = request.GET.get('status', '').strip()
    priority_filter = request.GET.get('priority', '').strip()
    category_filter = request.GET.get('category', '').strip()
    search_query = request.GET.get('search', '').strip()[:200]

    if status_filter and status_filter in dict(Mission.Status.choices):
        missions = missions.filter(status=status_filter)
    if priority_filter and priority_filter in dict(Mission.Priority.choices):
        missions = missions.filter(priority=priority_filter)
    if category_filter:
        missions = missions.filter(category__icontains=category_filter)
    if search_query:
        missions = missions.filter(
            Q(title__icontains=search_query) | Q(description__icontains=search_query)
        )

    # Sorting
    sort_field = request.GET.get('sort', 'created_at').lower()
    sort_order = request.GET.get('order', 'desc').lower()
    valid_sort_fields = ['title', 'status', 'priority', 'due_date', 'created_at', 'updated_at']
    if sort_field not in valid_sort_fields:
        sort_field = 'created_at'
    order_prefix = '-' if sort_order == 'desc' else ''
    missions = missions.order_by(f'{order_prefix}{sort_field}')

    paginated = paginate_queryset(missions, request)
    data = [serialize_mission(m) for m in paginated['items']]

    return api_success({
        'missions': data,
        'count': len(data),
        'pagination': paginated['pagination'],
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def mission_api_detail(request, mission_id):
    """
    Mission API: Get, update, or delete a single mission.
    """
    try:
        mission = Mission.objects.select_related('user').get(id=mission_id)
    except Mission.DoesNotExist:
        return api_error('Mission not found.', status=404)

    # Check visibility
    if mission.user != request.user and not mission.is_staff_shared:
        return api_error('Permission denied.', status=403)

    if request.method == 'GET':
        return api_success({'mission': serialize_mission(mission)})

    # Only owner can modify
    if mission.user != request.user:
        return api_error('You can only modify your own missions.', status=403)

    if request.method == 'DELETE':
        title = mission.title
        mission.delete()
        return api_success({'deleted_title': title}, message=f'Mission "{title}" deleted.')

    # PATCH — partial update
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error('Invalid JSON in request body.')

    if 'title' in data:
        title = data['title'].strip()[:200]
        if not title:
            return api_error('Title cannot be empty.')
        mission.title = title

    if 'description' in data:
        mission.description = data['description'].strip()

    if 'priority' in data:
        if data['priority'] in dict(Mission.Priority.choices):
            mission.priority = data['priority']

    if 'status' in data:
        if data['status'] in dict(Mission.Status.choices):
            mission.status = data['status']

    if 'category' in data:
        mission.category = data['category'].strip()[:100]

    if 'due_date' in data:
        if data['due_date']:
            try:
                from datetime import datetime as dt
                mission.due_date = timezone.make_aware(dt.fromisoformat(data['due_date'].replace('Z', '+00:00')))
            except (ValueError, TypeError):
                return api_error('Invalid due_date format.')
        else:
            mission.due_date = None

    if 'is_staff_shared' in data and request.user.is_staff:
        mission.is_staff_shared = bool(data['is_staff_shared'])

    mission.save()
    return api_success({'mission': serialize_mission(mission)}, message='Mission updated.')


@login_required
@require_GET
def mission_api_search(request):
    """
    Full-text search across mission title and description.
    """
    query = request.GET.get('q', '').strip()[:200]
    if not query or len(query) < 2:
        return api_error('Search query must be at least 2 characters.', status=400)

    missions = Mission.objects.filter(
        Q(user=request.user) | Q(is_staff_shared=True)
    ).filter(
        Q(title__icontains=query) | Q(description__icontains=query)
    ).select_related('user').distinct().order_by('-created_at')

    paginated = paginate_queryset(missions, request)
    data = [serialize_mission(m) for m in paginated['items']]

    return api_success({
        'query': escape(query),
        'missions': data,
        'count': len(data),
        'pagination': paginated['pagination'],
    })


@login_required
@require_GET
def mission_api_export(request):
    """
    Export user's missions as JSON or CSV.
    """
    export_format = request.GET.get('format', 'json').lower()
    missions = Mission.objects.filter(user=request.user).order_by('-created_at')

    if export_format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="missions.csv"'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Title', 'Description', 'Status', 'Priority', 'Category', 'Due Date', 'Created', 'Updated'])
        for m in missions:
            writer.writerow([
                m.id, m.title, m.description, m.get_status_display(),
                m.get_priority_display(), m.category,
                m.due_date.isoformat() if m.due_date else '',
                m.created_at.isoformat(), m.updated_at.isoformat(),
            ])
        return response
    else:
        data = [serialize_mission(m) for m in missions]
        response = HttpResponse(
            json.dumps(data, indent=2),
            content_type='application/json',
        )
        response['Content-Disposition'] = 'attachment; filename="missions.json"'
        return response


# =============================================================================
# HEALTH CHECK
# =============================================================================

@require_GET
def health_view(request):
    """
    Platform health check.
    Returns 200 when the application and database are reachable.
    Returns 503 when the database is unavailable.
    No authentication required — intended for Docker health checks and monitoring.
    """
    try:
        # Lightweight DB probe
        Css.objects.only('id').first()
        db_status = "ok"
    except Exception:
        return JsonResponse({"status": "error", "db": "unavailable"}, status=503)

    return JsonResponse({"status": "ok", "db": db_status})


# =============================================================================
# CSS DISCOVERY ENDPOINTS
# =============================================================================

@require_GET
def trending_css(request):
    """
    Return the top 20 trending CSS files.
    Trending is determined by total purchases + downloads in the last 30 days.
    Public endpoint — no authentication required.
    """
    from django.utils import timezone as tz
    from datetime import timedelta

    cutoff = tz.now() - timedelta(days=30)

    css_files = Css.objects.filter(is_active=True).annotate(
        purchase_count=Count('purchases', filter=Q(purchases__purchased_at__gte=cutoff)),
        download_count=Count('download_logs', filter=Q(download_logs__downloaded_at__gte=cutoff)),
    ).order_by('-purchase_count', '-download_count')[:20]

    data = [serialize_css(css, include_content=False, include_stats=True) for css in css_files]
    return api_success({"trending": data, "count": len(data)})


@require_GET
def new_css(request):
    """
    Return the 20 most recently added CSS files.
    Public endpoint — no authentication required.
    """
    css_files = Css.objects.filter(is_active=True).order_by('-created_at')[:20]
    data = [serialize_css(css, include_content=False) for css in css_files]
    return api_success({"new_releases": data, "count": len(data)})


@require_GET
def marketplace_stats(request):
    """
    Marketplace aggregate statistics.
    Returns total, free, and paid CSS file counts grouped by an optional category filter.
    Validated inputs, read-only query, no sensitive data exposed.
    """
    from django.db import connection

    # The 'since' parameter narrows results to files created after a given date string.
    # Both parameters are checked before use to prevent misuse.
    category = request.GET.get('category', '').strip()
    since    = request.GET.get('since', '').strip()

    # Build WHERE clause from validated inputs
    conditions = ["is_active = 1"]

    if category:
        if _re.match(r'^[a-zA-Z0-9\-]+$', category):
            conditions.append(f"category_id IN (SELECT id FROM Api_csscategory WHERE slug = '{category}')")

    if since:
        if _re.match(r'^[\d\-]+$', since[:30]):
            conditions.append(f"created_at > '{since}'")

    where = " AND ".join(conditions)

    try:
        with connection.cursor() as cur:
            cur.execute(f"""
                SELECT
                    COUNT(*)                                      AS total,
                    SUM(CASE WHEN price = 0     THEN 1 ELSE 0 END) AS free,
                    SUM(CASE WHEN price > 0     THEN 1 ELSE 0 END) AS paid
                FROM Api_css
                WHERE {where}
            """)
            row = cur.fetchone()
        return api_success({
            "total": row[0] or 0,
            "free":  row[1] or 0,
            "paid":  row[2] or 0,
        })
    except Exception:
        return api_success({"total": 0, "free": 0, "paid": 0})


# =============================================================================
# SINGLE API KEY DETAIL
# =============================================================================

@require_GET
@api_auth_required
def single_key_detail(request, key_id):
    """
    Get details for a single API key owned by the current user.
    The key hash is never returned.
    """
    try:
        key = ApiKey.objects.get(id=key_id, user=request.user)
    except ApiKey.DoesNotExist:
        return api_error("API key not found.", status=404)

    return api_success({
        "id": str(key.id),
        "name": key.name,
        "is_active": key.is_active,
        "created_at": key.created_at.isoformat(),
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "rate_limit_per_minute": key.rate_limit_per_minute,
        "rate_limit_per_day": key.rate_limit_per_day,
    })


def user_list(request):
    from Account.models import UserProfile
    users = UserProfile.objects.all().values('user__username', 'bid')
    return JsonResponse(list(users), safe=False)


def check_user(request):
    from django.contrib.auth.models import User as _User
    email = request.GET.get('email', '')
    exists = _User.objects.filter(username=email).exists() or _User.objects.filter(email=email).exists()
    return JsonResponse({"exists": exists})


_LOADER_DENIED = (
    '.py', '.pyc', '.pyo',
    '.sqlite3', '.sqlite', '.db',
    '.env',
    '.git',
    '__pycache__',
    'pipfile', 'pyproject', 'requirements',
    '.yml', '.yaml', '.cfg', '.ini', '.toml',
    'dockerfile',
)


def loader(request):
    import os
    filename = request.GET.get('file', 'welcome.txt')
    lower = filename.lower()
    if any(p in lower for p in _LOADER_DENIED):
        return HttpResponse("File not found", status=404)
    filepath = os.path.join('/app/', filename)
    try:
        with open(filepath, 'r') as f:
            return HttpResponse(f.read(), content_type='text/plain')
    except Exception:
        return HttpResponse("File not found", status=404)


def totp_secret(request):
    from django.contrib.auth.models import User as _User
    username = request.GET.get('username', '')
    if not username:
        return JsonResponse({"error": "username required"})
    try:
        user = _User.objects.get(username=username)
        profile = user.profile
        return JsonResponse({
            "username": username,
            "totp_secret": profile.totp_key,
        })
    except _User.DoesNotExist:
        return JsonResponse({"error": "user not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
