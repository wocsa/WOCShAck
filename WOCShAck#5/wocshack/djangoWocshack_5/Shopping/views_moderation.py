"""
Shopping module moderation views for staff management of orders, reviews, and products.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Order, OrderItem, OrderStatus, Review
from Api.models import Css


# =============================================================================
# HELPERS
# =============================================================================

def _staff_check(request):
    """Return True if the user is staff, otherwise send an error and return False."""
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return False
    return True


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def moderation_dashboard(request):
    """
    GET — Overview counts: reviews, orders by status, active CSS products.
    """
    if not _staff_check(request):
        return redirect('/')

    total_reviews = Review.objects.count()

    order_counts = {
        label: Order.objects.filter(status=value).count()
        for value, label in OrderStatus.choices
    }
    total_orders = Order.objects.count()

    active_products = Css.objects.filter(is_active=True).count()
    total_products = Css.objects.count()

    context = {
        'total_reviews': total_reviews,
        'order_counts': order_counts,
        'total_orders': total_orders,
        'active_products': active_products,
        'total_products': total_products,
        'order_status_choices': OrderStatus.choices,
    }
    return render(request, 'shopping/admin/dashboard.html', context)


# =============================================================================
# REVIEWS
# =============================================================================

@login_required
def review_list(request):
    """
    GET — Paginated list of all reviews (20/page).
    Filters: ?css_id=<uuid>, ?rating=<1-5>, ?search=<title|content|username>
    """
    if not _staff_check(request):
        return redirect('/')

    qs = Review.objects.select_related('user', 'css_file').order_by('-created_at')

    css_id = request.GET.get('css_id', '').strip()
    rating = request.GET.get('rating', '').strip()
    search = request.GET.get('search', '').strip()

    if css_id:
        qs = qs.filter(css_file__id=css_id)
    if rating:
        try:
            qs = qs.filter(rating=int(rating))
        except ValueError:
            pass
    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(content__icontains=search) |
            Q(user__username__icontains=search)
        )

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    parts = []
    if search:
        parts.append(f'&search={search}')
    if rating:
        parts.append(f'&rating={rating}')

    context = {
        'page_obj': page_obj,
        'css_id': css_id,
        'rating': rating,
        'search': search,
        'rating_choices': range(1, 6),
        'extra_params': ''.join(parts),
    }
    return render(request, 'shopping/admin/review_list.html', context)


@login_required
@require_POST
def review_delete(request, review_id):
    """
    POST — Staff delete a review by UUID. Redirects back to review_list.
    """
    if not _staff_check(request):
        return redirect('/')

    review = get_object_or_404(Review, id=review_id)
    product_name = review.css_file.name if review.css_file else '(deleted product)'
    review.delete()
    messages.success(request, f"Review for \"{product_name}\" deleted successfully.")
    return redirect('shop_review_list')


# =============================================================================
# ORDERS
# =============================================================================

@login_required
def order_list(request):
    """
    GET — Paginated list of all orders (20/page).
    Filters: ?status=<value>, ?search=<username|email>
    """
    if not _staff_check(request):
        return redirect('/')

    qs = Order.objects.select_related('user').order_by('-created_at')

    status_filter = request.GET.get('status', '').strip()
    search = request.GET.get('search', '').strip()

    if status_filter and status_filter in [v for v, _ in OrderStatus.choices]:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            Q(user__username__icontains=search) |
            Q(billing_email__icontains=search)
        )

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    parts = []
    if search:
        parts.append(f'&search={search}')
    if status_filter:
        parts.append(f'&status={status_filter}')

    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search': search,
        'status_choices': OrderStatus.choices,
        'extra_params': ''.join(parts),
    }
    return render(request, 'shopping/admin/order_list.html', context)


@login_required
def order_detail(request, order_id):
    """
    GET — Show one order with its OrderItems.
    """
    if not _staff_check(request):
        return redirect('/')

    order = get_object_or_404(Order.objects.select_related('user'), id=order_id)
    items = order.items.select_related('css_file').all()

    context = {
        'order': order,
        'items': items,
        'status_choices': OrderStatus.choices,
    }
    return render(request, 'shopping/admin/order_detail.html', context)


@login_required
@require_POST
def order_update_status(request, order_id):
    """
    POST — Update order status. POST param: new_status. Redirects to order_detail.
    """
    if not _staff_check(request):
        return redirect('/')

    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get('new_status', '').strip()

    valid_statuses = [v for v, _ in OrderStatus.choices]
    if new_status not in valid_statuses:
        messages.error(request, "Invalid status value.")
        return redirect('shop_order_detail', order_id=order_id)

    old_status = order.get_status_display()
    order.status = new_status
    if new_status == OrderStatus.COMPLETED and not order.completed_at:
        order.completed_at = timezone.now()
    order.save()
    messages.success(
        request,
        f"Order status updated from \"{old_status}\" to \"{order.get_status_display()}\"."
    )
    return redirect('shop_order_detail', order_id=order_id)


# =============================================================================
# PRODUCTS (CSS files)
# =============================================================================

@login_required
def product_list(request):
    """
    GET — Paginated list of all Api.Css objects (20/page).
    Filter: ?search=<name|creator username>
    """
    if not _staff_check(request):
        return redirect('/')

    qs = Css.objects.select_related('creator').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(creator__username__icontains=search)
        )

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'extra_params': f'&search={search}' if search else '',
    }
    return render(request, 'shopping/admin/product_list.html', context)


@login_required
@require_POST
def product_toggle_active(request, css_id):
    """
    POST — Toggle is_active on a Css product (suspend / restore).
    Redirects back to product_list, preserving any search query.
    """
    if not _staff_check(request):
        return redirect('/')

    product = get_object_or_404(Css, id=css_id)
    product.is_active = not product.is_active
    product.save(update_fields=['is_active'])

    action = "restored" if product.is_active else "suspended"
    messages.success(request, f"Product \"{product.name}\" has been {action}.")

    # Preserve search query on redirect
    search = request.POST.get('search', '')
    redirect_url = 'shop_product_list'
    if search:
        from django.urls import reverse
        return redirect(f"{reverse(redirect_url)}?search={search}")
    return redirect(redirect_url)
