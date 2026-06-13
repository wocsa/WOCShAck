"""
Developer module views — e-shop coupon management.
Developers can create discount coupons scoped to their published CSS products.
"""
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils.html import escape
from django.views.decorators.http import require_POST

from .views import developer_required
from Api.models import Css as ApiCss
from Shopping.models import Coupon


@developer_required
def coupon_list(request):
    """List all e-shop coupons created by this developer."""
    coupons = Coupon.objects.filter(developer=request.user)
    context = {'coupons': coupons}
    return render(request, 'developer/coupons.html', context)


@developer_required
def create_coupon(request):
    """Create a new developer-scoped e-shop coupon."""
    my_products = ApiCss.objects.filter(creator=request.user)

    if request.method == 'POST':
        code = escape(request.POST.get('code', '')[:50]).upper()
        discount_type = Coupon.DiscountType.PERCENTAGE
        discount_value_str = request.POST.get('discount_value', '')
        max_uses_str = request.POST.get('max_uses', '0')
        max_uses_per_user_str = request.POST.get('max_uses_per_user', '1')
        min_order_str = request.POST.get('minimum_order_amount', '0')
        valid_from_str = request.POST.get('valid_from', '')
        valid_until_str = request.POST.get('valid_until', '')
        description = escape(request.POST.get('description', '')[:200])

        def _ctx():
            return {'products': my_products}

        if not code:
            messages.error(request, 'Coupon code is required.')
            return render(request, 'developer/create_coupon.html', _ctx())

        if Coupon.objects.filter(code__iexact=code).exists():
            messages.error(request, 'This coupon code is already in use.')
            return render(request, 'developer/create_coupon.html', _ctx())

        try:
            discount_value = Decimal(discount_value_str)
            if not (Decimal('0.01') <= discount_value <= Decimal('100')):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, 'Discount percent must be between 0.01 and 100.')
            return render(request, 'developer/create_coupon.html', _ctx())

        try:
            min_order = Decimal(min_order_str)
            if min_order < 0:
                min_order = Decimal('0.00')
        except (InvalidOperation, ValueError):
            min_order = Decimal('0.00')

        coupon = Coupon(
            code=code,
            description=description,
            discount_type=discount_type,
            discount_value=discount_value,
            minimum_order_amount=min_order,
            developer=request.user,
        )

        try:
            coupon.max_uses = int(max_uses_str)
        except (ValueError, TypeError):
            coupon.max_uses = 0

        try:
            coupon.max_uses_per_user = max(1, int(max_uses_per_user_str))
        except (ValueError, TypeError):
            coupon.max_uses_per_user = 1

        if valid_from_str:
            try:
                from django.utils.dateparse import parse_datetime
                parsed = parse_datetime(valid_from_str)
                if parsed:
                    coupon.valid_from = parsed
            except Exception:
                pass

        if valid_until_str:
            try:
                from django.utils.dateparse import parse_datetime
                parsed = parse_datetime(valid_until_str)
                if parsed:
                    coupon.valid_until = parsed
            except Exception:
                pass

        coupon.save()
        messages.success(request, f'Coupon "{code}" created! It applies to all your products in the e-shop.')
        return redirect('developer_coupons')

    context = {'products': my_products}
    return render(request, 'developer/create_coupon.html', context)


@developer_required
@require_POST
def delete_coupon(request, coupon_id):
    """Delete a developer-owned coupon."""
    coupon = get_object_or_404(Coupon, id=coupon_id, developer=request.user)
    code = coupon.code
    coupon.delete()
    messages.success(request, f'Coupon "{code}" deleted.')
    return redirect('developer_coupons')
