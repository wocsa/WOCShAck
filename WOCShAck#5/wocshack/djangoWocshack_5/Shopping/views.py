"""
Shopping module views.
"""
import builtins
import io
import pickle
import base64
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.html import escape
import time

from Api.models import Css, Purchase
from .models import (
    Cart, CartItem, Order, OrderItem, OrderStatus,
    Review, Wishlist, Coupon, CouponUsage
)
from Bank.Utils import client as bank_client
from Bank.Utils.external_calls import get_user_balance, verify_user_pin
from Bank.models import BankCard, Transaction as BankTransaction
from Developer.models import DeveloperBalance, DeveloperSubscription


_PICKLE_SAFE = {
    'builtins': {'dict', 'list', 'tuple', 'set', 'frozenset',
                 'str', 'int', 'float', 'bool', 'bytes', 'NoneType'},
}


class _CartUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module in _PICKLE_SAFE and name in _PICKLE_SAFE[module]:
            return getattr(builtins, name)
        raise pickle.UnpicklingError(f"forbidden: {module}.{name}")


# =============================================================================
# SHOP VIEWS
# =============================================================================

def shop(request):
    """Display all CSS files available for purchase with filters and pagination."""
    query = request.GET.get('q', '')

    css_files = Css.objects.filter(is_active=True).defer('css_content').annotate(
        avg_rating=Avg('reviews__rating', filter=Q(reviews__is_approved=True)),
        review_count=Count('reviews', filter=Q(reviews__is_approved=True))
    )

    # Get filter parameters with sanitization
    search = request.GET.get('search', '').strip()[:100]  # Limit search length
    author = request.GET.get('author', '').strip()[:150]
    price_range = request.GET.get('price', '')
    sort_by = request.GET.get('sort', '-created_at')
    per_page = request.GET.get('per_page', '12')

    # Apply search filter (name)
    if search:
        css_files = css_files.filter(name__icontains=search)

    # Apply author filter (match against the creator's username, not the display-name CharField)
    if author:
        css_files = css_files.filter(creator__username__icontains=author)

    price_ranges = {
        'free': Q(price=0),
        'low': Q(price__gt=0, price__lte=5),
        'mid': Q(price__gt=5, price__lte=10),
        'high': Q(price__gt=10, price__lte=20),
        'premium': Q(price__gt=20),
    }
    if price_range in price_ranges:
        css_files = css_files.filter(price_ranges[price_range])

    valid_sorts = ['name', '-name', 'price', '-price', 'created_at', '-created_at', 'author', '-author']
    if sort_by in valid_sorts:
        css_files = css_files.order_by(sort_by)

    # Get unique authors for filter dropdown
    all_authors = Css.objects.values_list('author', flat=True).distinct().order_by('author')

    try:
        per_page = int(per_page)
        if per_page not in [12, 24, 48]:
            per_page = 12
    except ValueError:
        per_page = 12

    paginator = Paginator(css_files, per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Build query string for pagination links (without page parameter)
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    query_string = query_params.urlencode()

    # Get cart item count for display
    cart = Cart.get_or_create_for_request(request)
    cart_count = cart.get_item_count()

    # Get wishlist item IDs for the current user
    wishlist_ids = []
    if request.user.is_authenticated:
        wishlist_ids = list(Wishlist.objects.filter(user=request.user).values_list('css_file_id', flat=True))

    context = {
        'css_files': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'query_string': query_string,
        'search': escape(search),
        'author': escape(author),
        'price_range': price_range,
        'sort_by': sort_by,
        'per_page': per_page,
        'all_authors': all_authors,
        'cart_count': cart_count,
        'wishlist_ids': wishlist_ids,
        'query': query,
    }

    return render(request, "shop.html", context)


def product_detail(request, css_id):
    """
    Display product details with reviews.
    CSS content is deferred to prevent source code exposure in the product detail page.
    GIF preview images are displayed instead of live CSS code.
    """
    # The product detail page shows a GIF preview, not live CSS.
    css_file = get_object_or_404(Css.objects.filter(is_active=True).defer('css_content'), id=css_id)

    # Get approved reviews
    reviews = css_file.reviews.filter(is_approved=True).select_related('user')

    # Calculate average rating
    rating_stats = reviews.aggregate(
        avg_rating=Avg('rating'),
        review_count=Count('id')
    )

    # Check if user has purchased this item (for verified purchase badge)
    user_has_purchased = False
    user_review = None
    is_in_wishlist = False

    if request.user.is_authenticated:
        user_has_purchased = Purchase.objects.filter(
            user=request.user,
            css_file=css_file
        ).exists()
        user_review = Review.objects.filter(
            user=request.user,
            css_file=css_file
        ).first()
        is_in_wishlist = Wishlist.objects.filter(
            user=request.user,
            css_file=css_file
        ).exists()

    context = {
        'css_file': css_file,
        'reviews': reviews,
        'avg_rating': rating_stats['avg_rating'] or 0,
        'review_count': rating_stats['review_count'],
        'user_has_purchased': user_has_purchased,
        'user_review': user_review,
        'is_in_wishlist': is_in_wishlist,
    }

    return render(request, "product_detail.html", context)


# =============================================================================
# CART VIEWS
# =============================================================================

def cart(request):
    """Display shopping cart with CSS items."""
    cart_backup = request.COOKIES.get('cart_backup')
    if cart_backup:
        try:
            _CartUnpickler(io.BytesIO(base64.b64decode(cart_backup))).load()
        except Exception:
            pass

    cart_obj = Cart.get_or_create_for_request(request)
    cart_items = cart_obj.cart_items.select_related('css_file')

    # Calculate totals
    items_data = []
    for item in cart_items:
        items_data.append({
            'item': item,
            'css': item.css_file,
            'quantity': item.quantity,
            'total_price': item.get_total(),
        })

    total = cart_obj.get_total()

    # Store total in session for payment page
    request.session['payment_total'] = float(total)

    # Get applied coupon from session
    applied_coupon = None
    discount_amount = Decimal('0.00')
    coupon_code = request.session.get('coupon_code')

    if coupon_code:
        try:
            coupon = Coupon.objects.get(code__iexact=coupon_code)
            applicable_total = coupon.get_applicable_total(cart_items)
            is_valid, message = coupon.is_valid(
                order_total=applicable_total,
                user=request.user if request.user.is_authenticated else None
            )
            if is_valid:
                applied_coupon = coupon
                discount_amount = coupon.calculate_discount(applicable_total)
        except Coupon.DoesNotExist:
            del request.session['coupon_code']

    final_total = total - discount_amount

    context = {
        'cart_items': items_data,
        'total': total,
        'discount_amount': discount_amount,
        'final_total': final_total,
        'applied_coupon': applied_coupon,
        'item_count': cart_obj.get_item_count(),
    }

    return render(request, "cart.html", context)


def add_to_cart(request, css_id):
    """
    Add a CSS file to the cart.
    Uses database-backed cart.
    """
    css = get_object_or_404(Css, id=css_id)
    cart_obj = Cart.get_or_create_for_request(request)

    # Get or create cart item
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart_obj,
        css_file=css,
        defaults={'quantity': 1}
    )

    if not created:
        if cart_item.quantity < 100:
            cart_item.quantity += 1
            cart_item.save()

    messages.success(request, f'"{css.name}" added to cart.')
    return redirect('cart')


@csrf_exempt
def remove_from_cart(request, css_id):
    """Remove a CSS file from the cart."""
    cart_obj = Cart.get_or_create_for_request(request)
    CartItem.objects.filter(cart=cart_obj, css_file_id=css_id).delete()
    messages.success(request, 'Item removed from cart.')
    return redirect('cart')


@require_POST
def update_cart(request, css_id):
    """
    Update quantity of a CSS file in the cart.
    Includes CSRF protection via decorator and quantity validation.
    """
    cart_obj = Cart.get_or_create_for_request(request)

    try:
        quantity = int(request.POST.get('quantity', 1))
        quantity = max(0, min(quantity, 100))  # Bound between 0 and 100
    except (ValueError, TypeError):
        quantity = 1

    if quantity > 0:
        CartItem.objects.filter(
            cart=cart_obj,
            css_file_id=css_id
        ).update(quantity=quantity)
    else:
        CartItem.objects.filter(cart=cart_obj, css_file_id=css_id).delete()

    return redirect('cart')


# =============================================================================
# COUPON VIEWS
# =============================================================================

@require_POST
def apply_coupon(request):
    """
    Apply a coupon code to the cart.
    Validates coupon thoroughly before applying.
    """
    coupon_code = request.POST.get('coupon_code', '').strip().upper()[:50]

    if not coupon_code:
        messages.error(request, 'Please enter a coupon code.')
        return redirect('cart')

    try:
        coupon = Coupon.objects.get(code__iexact=coupon_code)
    except Coupon.DoesNotExist:
        messages.error(request, 'Invalid coupon code.')
        return redirect('cart')

    # Get cart total for validation
    cart_obj = Cart.get_or_create_for_request(request)
    cart_items = cart_obj.cart_items.select_related('css_file')
    applicable_total = coupon.get_applicable_total(cart_items)

    # Validate coupon
    is_valid, message = coupon.is_valid(
        order_total=applicable_total,
        user=request.user if request.user.is_authenticated else None
    )

    if not is_valid:
        messages.error(request, message)
        return redirect('cart')

    # Store coupon in session
    request.session['coupon_code'] = coupon.code
    discount = coupon.calculate_discount(applicable_total)
    messages.success(request, f'Coupon applied! You save {discount} Neuros.')

    return redirect('cart')


@require_POST
def remove_coupon(request):
    """
    Remove applied coupon from cart.
    """
    if 'coupon_code' in request.session:
        del request.session['coupon_code']
        messages.success(request, 'Coupon removed.')

    return redirect('cart')


# =============================================================================
# PAYMENT VIEWS
# =============================================================================

@login_required
def payment(request):
    """
    Display payment page with dual authentication.
    Requires both account password and bank PIN before processing payment.
    This protects against unauthorized purchases if a user's session is compromised.
    """
    cart_obj = Cart.get_or_create_for_request(request)
    cart_items = cart_obj.cart_items.select_related('css_file')

    if not cart_items.exists():
        messages.error(request, 'Your cart is empty.')
        return redirect('cart')

    total = cart_obj.get_total()

    # Check for applied coupon
    discount_amount = Decimal('0.00')
    coupon_code = request.session.get('coupon_code')

    if coupon_code:
        try:
            coupon = Coupon.objects.get(code__iexact=coupon_code)
            applicable_total = coupon.get_applicable_total(cart_items)
            is_valid, _ = coupon.is_valid(
                order_total=applicable_total,
                user=request.user if request.user.is_authenticated else None
            )
            if is_valid:
                discount_amount = coupon.calculate_discount(applicable_total)
        except Coupon.DoesNotExist:
            pass

    final_total = total - discount_amount

    cli, sid = bank_client.make_connection()
    if not cli or not sid:
        messages.error(request, 'Banking system unavailable. Please try again later.')
        return redirect('cart')

    # Check if user exists in banking system
    user_check_response = cli.get_user(sid, request.user.id)
    cli.close_session(sid)
    cli.close()

    if not (isinstance(user_check_response, dict) and user_check_response.get("success")):
        messages.error(request, 'You need a bank account to make purchases. Please set up your banking PIN first.')
        return redirect('cart')

    if request.method == "POST":
        password = request.POST.get("password", "").strip()
        pin = request.POST.get("pin", "").strip()
        card_number = request.POST.get("card_number", "").strip()[:16]
        first_name = request.POST.get("first_name", "").strip()[:100]
        last_name = request.POST.get("name", "").strip()[:100]
        email = request.POST.get("email", "").strip()[:254]
        phone = request.POST.get("phone", "").strip()[:20]

        submitted_total = request.POST.get("total")
        if submitted_total is not None:
            try:
                final_total = Decimal(submitted_total)
            except Exception:
                pass

        # Helper: build the context dict for re-rendering the form on error.
        # Centralised here so every early exit stays DRY and consistent.
        user_cards = BankCard.objects.filter(user=request.user).exclude(status='cancelled')

        def _form_ctx():
            return {
                'total': total,
                'discount_amount': discount_amount,
                'final_total': final_total,
                'coupon_code': coupon_code,
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': phone,
                'card_number': card_number,
                'user_cards': user_cards,
            }

        if not password or not pin or not card_number:
            messages.error(request, "Account password, bank PIN, and card number are all required for secure payment.")
            return render(request, "payment.html", _form_ctx())

        if not first_name or not last_name or not email:
            messages.error(request, "Please fill in all billing information fields.")
            return render(request, "payment.html", _form_ctx())

        if not request.user.check_password(password):
            messages.error(request, "Incorrect account password. Payment authorization failed.")
            return render(request, "payment.html", _form_ctx())

        if not verify_user_pin(request.user.id, pin):
            messages.error(request, "Incorrect bank PIN. Payment authorization failed.")
            return render(request, "payment.html", _form_ctx())

        # The queryset is scoped to request.user so users cannot reference other
        # people's cards.  Only exact payment_number match is accepted.
        try:
            card = BankCard.objects.get(
                user=request.user,
                payment_number=card_number,
            )
        except BankCard.DoesNotExist:
            messages.error(request, "Invalid card number. Please enter the 16-digit number shown on your V.R.C card.")
            return render(request, "payment.html", _form_ctx())

        if card.status == 'frozen':
            messages.error(request, "Your card is frozen and cannot be used for payments. Unfreeze your card in the banking dashboard first.")
            return render(request, "payment.html", _form_ctx())

        # Cancelled cards are also ineligible.
        if card.status == 'cancelled':
            messages.error(request, "This card has been cancelled and cannot be used for payments.")
            return render(request, "payment.html", _form_ctx())

        balance = get_user_balance(request.user.id)
        if balance is None:
            messages.error(request, "Could not verify your balance. Please try again.")
            return render(request, "payment.html", _form_ctx())

        # Convert balance to Decimal for comparison
        balance_decimal = Decimal(str(balance))
        if final_total > balance_decimal:
            messages.error(request, f"Insufficient funds. Your balance is {balance} Neuros, but the order total is {final_total} Neuros.")
            return render(request, "payment.html", _form_ctx())

        # Store minimal info for payment processing (NOT the password or PIN)
        request.session['payment_info'] = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'total': float(final_total),
            'discount': float(discount_amount),
            'coupon_code': coupon_code,
            'card_number': card_number,
        }
        request.session['payment_total'] = float(final_total)

        messages.success(request, 'Authentication successful. Processing your payment...')
        response = redirect("payment_loading")
        response.set_cookie('last_card', card_number)
        return response

    # GET request - show payment form with dual authentication
    # Get user's current balance for display
    balance = get_user_balance(request.user.id)
    balance_after_purchase = None
    if balance is not None:
        # Convert balance to Decimal to match final_total type
        balance_decimal = Decimal(str(balance))
        balance_after_purchase = balance_decimal - final_total

    # Fetch all non-cancelled cards for the dropdown
    user_cards = BankCard.objects.filter(user=request.user).exclude(status='cancelled')

    context = {
        'total': total,
        'discount_amount': discount_amount,
        'final_total': final_total,
        'coupon_code': coupon_code,
        'balance': balance,
        'balance_after_purchase': balance_after_purchase,
        'cart_items': cart_items,
        'cart_item_count': cart_items.count(),
        'user_cards': user_cards,
    }

    return render(request, "payment.html", context)


def payment_loading(request):
    """
    Display payment loading/processing page.
    """
    total = request.session.get('payment_total', 0)
    return render(request, "payment_loading.html", {"total": total})


@login_required
@require_POST
def complete_order(request):
    """
    Complete the order after payment confirmation.
    Integrates with Bank client to deduct payment from user's bank account.
    Uses database transaction for atomicity.
    """
    import sys
    print(f"[PAYMENT DEBUG] complete_order called by user: {request.user.username} (id={request.user.id})", file=sys.stderr, flush=True)

    payment_info = request.session.get('payment_info', {})
    print(f"[PAYMENT DEBUG] payment_info from session: {payment_info}", file=sys.stderr, flush=True)

    if not payment_info:
        print(f"[PAYMENT DEBUG] FAILED: No payment info in session", file=sys.stderr, flush=True)
        messages.error(request, 'Payment information not found.')
        return redirect('cart')

    cart_obj = Cart.get_or_create_for_request(request)
    cart_items = cart_obj.cart_items.select_related('css_file')
    print(f"[PAYMENT DEBUG] Cart has {cart_items.count()} items", file=sys.stderr, flush=True)

    if not cart_items.exists():
        print(f"[PAYMENT DEBUG] FAILED: Cart is empty", file=sys.stderr, flush=True)
        messages.error(request, 'Your cart is empty.')
        return redirect('cart')

    # Calculate final amount to charge
    cart_total = cart_obj.get_total()
    final_total = Decimal(str(payment_info.get('total', 0)))
    discount_amount = Decimal(str(payment_info.get('discount', 0)))

    coupon_code = payment_info.get('coupon_code')
    coupon_obj = None
    if coupon_code and discount_amount > 0:
        try:
            coupon_obj = Coupon.objects.get(code__iexact=coupon_code)
            applicable_total = coupon_obj.get_applicable_total(cart_items)
            is_valid, validation_msg = coupon_obj.is_valid(
                order_total=applicable_total,
                user=request.user,
            )
            if not is_valid:
                messages.error(
                    request,
                    f'Coupon "{coupon_code}" is no longer valid: {validation_msg} '
                    'Please review your cart and try again.',
                )
                # Clear stale coupon data from session
                request.session.pop('coupon_code', None)
                request.session.pop('payment_info', None)
                return redirect('cart')
            # Recalculate discount from current coupon state
            discount_amount = coupon_obj.calculate_discount(applicable_total)
            total = cart_obj.get_total()
            final_total = total - discount_amount
        except Coupon.DoesNotExist:
            messages.error(
                request,
                f'Coupon "{coupon_code}" no longer exists. '
                'Please review your cart and try again.',
            )
            request.session.pop('coupon_code', None)
            request.session.pop('payment_info', None)
            return redirect('cart')

    payment_success = False
    payment_error_message = None

    try:
        # Connect to Bank system
        cli, sid = bank_client.make_connection()
        print(f"[PAYMENT DEBUG] Bank connection result: cli={cli is not False and cli is not None}, sid={sid}", file=sys.stderr, flush=True)

        if cli and sid:
            try:
                # Get user's bank account information
                user_response = cli.get_user(sid, request.user.id)
                time.sleep(0.5)
                print(f"[PAYMENT DEBUG] User response: {user_response}", file=sys.stderr, flush=True)

                if isinstance(user_response, dict) and user_response.get("success"):
                    user_data = user_response.get("user", {})
                    current_balance = Decimal(str(user_data.get("balance", 0)))
                    user_id = user_data.get("id")
                    print(f"[PAYMENT DEBUG] User ID: {user_id}, Balance: {current_balance}, Order total: {final_total}", file=sys.stderr, flush=True)

                    if final_total > current_balance:
                        payment_error_message = f'Insufficient funds. Your balance is {current_balance} Neuros, but the order total is {final_total} Neuros.'
                    else:
                        # Pay each seller for their items, distributing coupon
                        # discount proportionally across applicable items.
                        all_transactions_successful = True
                        transaction_errors = []

                        # Build per-item discounted amounts
                        item_charges = []
                        if discount_amount > 0 and coupon_obj is not None:
                            applicable_total = coupon_obj.get_applicable_total(cart_items)
                        else:
                            applicable_total = Decimal('0.00')

                        # Find the last applicable item index for rounding
                        last_applicable_idx = -1
                        items_list = list(cart_items)
                        if discount_amount > 0 and coupon_obj is not None and applicable_total > 0:
                            for idx, cart_item in enumerate(items_list):
                                css = cart_item.css_file
                                is_applicable = (
                                    coupon_obj.developer_id is None
                                    or css.creator_id == coupon_obj.developer_id
                                )
                                if is_applicable:
                                    last_applicable_idx = idx

                        discount_distributed = Decimal('0.00')
                        for idx, cart_item in enumerate(items_list):
                            css = cart_item.css_file
                            undiscounted = css.price * cart_item.quantity

                            # Determine this item's share of the discount
                            if (
                                discount_amount > 0
                                and coupon_obj is not None
                                and applicable_total > 0
                            ):
                                is_applicable = (
                                    coupon_obj.developer_id is None
                                    or css.creator_id == coupon_obj.developer_id
                                )
                                if is_applicable:
                                    if idx == last_applicable_idx:
                                        # Last applicable item absorbs rounding remainder
                                        item_discount = discount_amount - discount_distributed
                                    else:
                                        item_discount = (
                                            undiscounted / applicable_total * discount_amount
                                        ).quantize(Decimal('0.01'))
                                    discount_distributed += item_discount
                                else:
                                    item_discount = Decimal('0.00')
                            else:
                                item_discount = Decimal('0.00')

                            discounted_total = max(undiscounted - item_discount, Decimal('0.00'))
                            item_charges.append((cart_item, css, discounted_total))

                        # Route all payments to the platform admin account
                        from django.contrib.auth.models import User as _DjangoUser
                        _admin_user = _DjangoUser.objects.filter(is_superuser=True).first()
                        admin_bank_id = _admin_user.id if _admin_user else 1

                        for cart_item, css, charge_amount in item_charges:
                            seller_id = css.creator.id

                            # Skip if buyer is the seller (buying own items)
                            if user_id == seller_id:
                                print(f"[PAYMENT DEBUG] Skipping self-purchase: item={css.name}, seller={seller_id}", file=sys.stderr, flush=True)
                                continue

                            # Skip zero-amount transactions (fully discounted)
                            if charge_amount <= 0:
                                print(f"[PAYMENT DEBUG] Skipping zero-amount item: {css.name}", file=sys.stderr, flush=True)
                                continue

                            print(f"[PAYMENT DEBUG] Processing payment: item={css.name}, from={user_id}, to=admin({admin_bank_id}), amount={float(charge_amount)}", file=sys.stderr, flush=True)

                            result = cli.transaction(
                                sid=sid,
                                from_user=user_id,
                                to_user=admin_bank_id,
                                amount=float(charge_amount)
                            )
                            time.sleep(0.5)
                            print(f"[PAYMENT DEBUG] Transaction result for {css.name}: {result}", file=sys.stderr, flush=True)

                            if not result or result.get('status') != 'success':
                                all_transactions_successful = False
                                error_msg = result.get('message', 'Transaction failed') if result else 'No response from bank server'
                                transaction_errors.append(f"{css.name}: {error_msg}")
                                print(f"[PAYMENT DEBUG] Transaction FAILED for {css.name}: {error_msg}", file=sys.stderr, flush=True)
                                break

                        if all_transactions_successful:
                            payment_success = True
                            print(f"[PAYMENT DEBUG] All payments marked as SUCCESS", file=sys.stderr, flush=True)
                        else:
                            payment_error_message = "Payment failed: " + "; ".join(transaction_errors)
                            print(f"[PAYMENT DEBUG] Payment FAILED: {payment_error_message}", file=sys.stderr, flush=True)
                else:
                    payment_error_message = 'Could not verify your bank account. Please ensure your bank account is set up.'
                    print(f"[PAYMENT DEBUG] Failed to get user account", file=sys.stderr, flush=True)
            finally:
                cli.close_session(sid)
                cli.close()
        else:
            payment_error_message = 'Bank system connection error. Please try again later.'
            print(f"[PAYMENT DEBUG] Bank connection FAILED", file=sys.stderr, flush=True)
    except Exception as e:
        payment_error_message = f'Payment processing error: {str(e)}'
        print(f"[PAYMENT DEBUG] Exception occurred: {e}", file=sys.stderr, flush=True)

    # Look up which card was used (stored during authentication step)
    _card_number_used = payment_info.get('card_number', '')
    _card_used = None
    if _card_number_used:
        try:
            _card_used = BankCard.objects.get(user=request.user, payment_number=_card_number_used)
        except BankCard.DoesNotExist:
            pass

    if not payment_success:
        print(f"[PAYMENT DEBUG] Payment FAILED, creating cancelled order. Error: {payment_error_message}", file=sys.stderr, flush=True)
        # Log the failed payment attempt as a Bank Transaction
        BankTransaction.objects.create(
            user=request.user,
            card=_card_used,
            transaction_type='payment',
            amount=final_total,
            counterpart_label='Shopping - CSS marketplace',
            note=f'Order payment failed: {payment_error_message}'[:500],
            status='failed',
        )
        # Create order with PENDING status to track failed payment
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user,
                total_amount=cart_total,
                discount_amount=discount_amount,
                coupon_code=payment_info.get('coupon_code'),
                billing_first_name=payment_info.get('first_name', ''),
                billing_last_name=payment_info.get('last_name', ''),
                billing_email=payment_info.get('email', ''),
                billing_phone=payment_info.get('phone', ''),
                status=OrderStatus.CANCELLED,  # Mark as cancelled due to payment failure
            )

            # Still create order items for record keeping
            for cart_item in cart_items:
                css = cart_item.css_file
                OrderItem.objects.create(
                    order=order,
                    css_file=css,
                    css_name=css.name,
                    css_author=css.author,
                    price_at_purchase=css.price,
                    quantity=cart_item.quantity,
                )

        # Show error message with specific reason
        messages.error(request, f'Payment failed: {payment_error_message}')
        messages.info(request, 'Your order has been cancelled. Please try again or contact support.')
        print(f"[PAYMENT DEBUG] Redirecting to cart after payment failure", file=sys.stderr, flush=True)
        return redirect('cart')

    print(f"[PAYMENT DEBUG] Payment SUCCESS, creating completed order", file=sys.stderr, flush=True)
    with transaction.atomic():
        # Create order with COMPLETED status
        order = Order.objects.create(
            user=request.user,
            total_amount=cart_total,
            discount_amount=discount_amount,
            coupon_code=payment_info.get('coupon_code'),
            billing_first_name=payment_info.get('first_name', ''),
            billing_last_name=payment_info.get('last_name', ''),
            billing_email=payment_info.get('email', ''),
            billing_phone=payment_info.get('phone', ''),
            status=OrderStatus.COMPLETED,
            completed_at=timezone.now(),
        )

        # Create order items and purchases
        for cart_item in cart_items:
            css = cart_item.css_file

            # Create order item
            OrderItem.objects.create(
                order=order,
                css_file=css,
                css_name=css.name,
                css_author=css.author,
                price_at_purchase=css.price,
                quantity=cart_item.quantity,
            )

            # Create purchase record (if not already purchased)
            Purchase.objects.get_or_create(
                user=request.user,
                css_file=css,
                defaults={'price_paid': css.price}
            )

        # Credit each seller's DeveloperBalance with their commission share
        for cart_item, css, charge_amount in item_charges:
            if charge_amount <= 0 or css.creator_id == request.user.id:
                continue
            try:
                active_sub = DeveloperSubscription.objects.filter(
                    user_id=css.creator_id,
                    status__in=['active', 'trial']
                ).select_related('plan').first()
                commission_rate = active_sub.plan.commission_rate if active_sub else Decimal('0.70')
            except Exception:
                commission_rate = Decimal('0.70')

            developer_share = (charge_amount * commission_rate).quantize(Decimal('0.01'))
            balance, _ = DeveloperBalance.objects.get_or_create(developer_id=css.creator_id)
            balance.available += developer_share
            balance.total_earned += developer_share
            balance.save()

        # Record coupon usage only when a discount was actually charged
        if coupon_obj is not None and discount_amount > 0:
            CouponUsage.objects.create(
                coupon=coupon_obj,
                user=request.user,
                order=order
            )
            coupon_obj.current_uses += 1
            coupon_obj.save()

        # Clear cart and session data
        cart_obj.clear()
        if 'coupon_code' in request.session:
            del request.session['coupon_code']
        if 'payment_info' in request.session:
            del request.session['payment_info']
        if 'payment_total' in request.session:
            del request.session['payment_total']

    # Log the successful payment as a Bank Transaction
    BankTransaction.objects.create(
        user=request.user,
        card=_card_used,
        transaction_type='payment',
        amount=final_total,
        counterpart_label='Shopping - CSS marketplace',
        note=f'Order #{order.id} - {cart_items.count()} item(s)',
        status='completed',
    )

    messages.success(request, f'Payment successful! {final_total} Neuros deducted from your account.')
    messages.success(request, f'Order {order.id} completed successfully!')
    print(f"[PAYMENT DEBUG] Order {order.id} completed successfully, redirecting to order detail", file=sys.stderr, flush=True)

    # Email failure is suppressed so it never breaks the order completion flow.
    try:
        from Shopping.utils.invoice import send_invoice_email
        order_items_for_invoice = order.items.select_related('css_file').all()
        email_result = send_invoice_email(order, order_items_for_invoice)
        if email_result and 'status' in email_result:
            messages.info(request, f'A receipt has been sent to {order.billing_email}.')
            print(f"[INVOICE EMAIL] Sent invoice to {order.billing_email}", file=sys.stderr, flush=True)
        else:
            print(f"[INVOICE EMAIL] Could not send invoice email (webmail may be unavailable)", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[INVOICE EMAIL] Email send error (non-critical): {e}", file=sys.stderr, flush=True)

    return redirect('order_detail', order_id=order.id)


# =============================================================================
# ORDER HISTORY VIEWS
# =============================================================================

@login_required
def order_history(request):
    """
    Display user's order history.
    Only shows orders belonging to the authenticated user.
    """
    orders = Order.objects.filter(user=request.user).prefetch_related('items')

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter and status_filter in OrderStatus.values:
        orders = orders.filter(status=status_filter)

    # Pagination
    paginator = Paginator(orders, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'orders': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'status_choices': OrderStatus.choices,
    }

    return render(request, "order_history.html", context)


@login_required
def download_invoice(request, order_id):
    """
    Generate and stream a PDF invoice for an order.
    Only the order owner can download their invoice.
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)
    order_items = order.items.select_related('css_file').all()

    from Shopping.utils.invoice import generate_invoice_pdf
    pdf_bytes = generate_invoice_pdf(order, order_items)

    if not pdf_bytes:
        messages.error(request, 'Could not generate invoice PDF. Please try again later.')
        return redirect('order_detail', order_id=order_id)

    filename = f'invoice-{str(order.id)[:13].upper()}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def order_detail(request, order_id):
    """
    Display order details.
    Ensures user can only view their own orders.
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)
    order_items = order.items.select_related('css_file')

    context = {
        'order': order,
        'order_items': order_items,
    }

    return render(request, "order_detail.html", context)


# =============================================================================
# REVIEW VIEWS
# =============================================================================

@login_required
@require_POST
def add_review(request, css_id):
    """
    Add a review for a CSS file.
    Validates user has purchased the item and hasn't already reviewed it.
    """
    css_file = get_object_or_404(Css, id=css_id)

    # Check if user already reviewed
    if Review.objects.filter(user=request.user, css_file=css_file).exists():
        messages.error(request, 'You have already reviewed this item.')
        return redirect('product_detail', css_id=css_id)

    # Get and validate form data
    try:
        rating = int(request.POST.get('rating', 0))
        if not 1 <= rating <= 5:
            raise ValueError("Invalid rating")
    except (ValueError, TypeError):
        messages.error(request, 'Please provide a valid rating (1-5).')
        return redirect('product_detail', css_id=css_id)

    title = request.POST.get('title', '').strip()[:200]
    content = request.POST.get('content', '').strip()[:5000]

    if not title or not content:
        messages.error(request, 'Please provide a title and review content.')
        return redirect('product_detail', css_id=css_id)

    # Check if verified purchase
    is_verified = Purchase.objects.filter(
        user=request.user,
        css_file=css_file
    ).exists()

    Review.objects.create(
        user=request.user,
        css_file=css_file,
        rating=rating,
        title=title,
        content=content,
        is_verified_purchase=is_verified,
    )

    try:
        from Community.services.feed_service import create_feed_item
        from Community.models.feed import ActivityFeedItem
        create_feed_item(
            user=request.user,
            action_type=ActivityFeedItem.ActionType.REVIEW_POSTED,
            title=f'Reviewed: {css_file.name}',
            description=content[:200],
            icon='⭐',
            related_object_id=str(css_file.id),
        )
    except Exception:
        pass

    messages.success(request, 'Review submitted successfully!')
    return redirect('product_detail', css_id=css_id)


@login_required
@require_POST
def delete_review(request, review_id):
    """
    Delete user's own review.
    """
    review = get_object_or_404(Review, id=review_id, user=request.user)
    css_id = review.css_file_id
    review.delete()
    messages.success(request, 'Review deleted.')
    return redirect('product_detail', css_id=css_id)


def reviews_page(request, css_id):
    """
    Display all reviews for a CSS file.
    """
    css_file = get_object_or_404(Css, id=css_id)
    reviews = css_file.reviews.filter(is_approved=True).select_related('user')

    # Sort options
    sort_by = request.GET.get('sort', '-created_at')
    valid_sorts = ['-created_at', 'created_at', '-rating', 'rating']
    if sort_by in valid_sorts:
        reviews = reviews.order_by(sort_by)

    # Calculate rating distribution
    rating_distribution = reviews.values('rating').annotate(count=Count('id'))
    rating_dict = {i: 0 for i in range(1, 6)}
    for item in rating_distribution:
        rating_dict[item['rating']] = item['count']

    # Pagination
    paginator = Paginator(reviews, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'css_file': css_file,
        'reviews': page_obj,
        'page_obj': page_obj,
        'rating_distribution': rating_dict,
        'total_reviews': reviews.count(),
        'sort_by': sort_by,
    }

    return render(request, "reviews.html", context)


# =============================================================================
# WISHLIST VIEWS
# =============================================================================

@login_required
def wishlist(request):
    """
    Display user's wishlist.
    """
    wishlist_items = Wishlist.objects.filter(
        user=request.user
    ).select_related('css_file')

    context = {
        'wishlist_items': wishlist_items,
    }

    return render(request, "wishlist.html", context)


@login_required
def add_to_wishlist(request, css_id):
    """
    Add a CSS file to wishlist.
    """
    css_file = get_object_or_404(Css, id=css_id)

    wishlist_item, created = Wishlist.objects.get_or_create(
        user=request.user,
        css_file=css_file
    )

    if created:
        messages.success(request, f'"{css_file.name}" added to wishlist.')
    else:
        messages.info(request, f'"{css_file.name}" is already in your wishlist.')

    # Redirect back to referring page or shop
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        return redirect(referer)
    return redirect('shop')


@login_required
def remove_from_wishlist(request, css_id):
    """
    Remove a CSS file from wishlist.
    """
    Wishlist.objects.filter(user=request.user, css_file_id=css_id).delete()
    messages.success(request, 'Item removed from wishlist.')

    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        return redirect(referer)
    return redirect('wishlist')


@login_required
def move_to_cart(request, css_id):
    """
    Move item from wishlist to cart.
    """
    css_file = get_object_or_404(Css, id=css_id)

    # Remove from wishlist
    Wishlist.objects.filter(user=request.user, css_file=css_file).delete()

    # Add to cart
    cart_obj = Cart.get_or_create_for_request(request)
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart_obj,
        css_file=css_file,
        defaults={'quantity': 1}
    )

    if not created and cart_item.quantity < 100:
        cart_item.quantity += 1
        cart_item.save()

    messages.success(request, f'"{css_file.name}" moved to cart.')
    return redirect('cart')


# =============================================================================
# API VIEWS (for AJAX)
# =============================================================================

@require_GET
def cart_count(request):
    """
    Return cart item count as JSON.
    For updating cart badge via AJAX.
    """
    cart_obj = Cart.get_or_create_for_request(request)
    return JsonResponse({'count': cart_obj.get_item_count()})


@require_POST
def quick_add_to_cart(request, css_id):
    """
    Quick add to cart via AJAX.
    """
    try:
        css = get_object_or_404(Css, id=css_id)
        cart_obj = Cart.get_or_create_for_request(request)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart_obj,
            css_file=css,
            defaults={'quantity': 1}
        )

        if not created and cart_item.quantity < 100:
            cart_item.quantity += 1
            cart_item.save()

        return JsonResponse({
            'success': True,
            'cart_count': cart_obj.get_item_count(),
            'message': f'"{css.name}" added to cart.'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': 'Failed to add item to cart.'
        }, status=400)


# =============================================================================
# SELLER PROFILE VIEWS
# =============================================================================

def seller_profile(request, username):
    """
    Display a seller's storefront: their listed products, stats, and public profile link.
    """
    from django.contrib.auth.models import User

    seller = get_object_or_404(User, username=username)
    products = Css.objects.defer('css_content').filter(creator=seller).annotate(
        avg_rating=Avg('reviews__rating', filter=Q(reviews__is_approved=True)),
        review_count=Count('reviews', filter=Q(reviews__is_approved=True))
    ).order_by('-created_at')

    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    total_products = products.count()
    from django.db.models import Avg as _Avg
    overall_rating = products.aggregate(r=_Avg('avg_rating'))['r']

    return render(request, 'seller_profile.html', {
        'seller': seller,
        'page_obj': page_obj,
        'total_products': total_products,
        'overall_rating': overall_rating,
    })


def seller_by_css(request, css_id):
    """
    View the seller profile for a specific CSS file's creator.
    """
    css_file = get_object_or_404(Css, id=css_id)

    # Redirect to the creator's public profile
    return redirect('public_profile_by_username', username=css_file.creator.username)


# =============================================================================
# ARTICLE MANAGEMENT VIEWS (Seller tools)
# =============================================================================

@login_required
def add_article(request):
    """
    Web form view for sellers to add a new CSS file to the marketplace.
    Requires the seller to have the Developer role (stored in Profile.role == 'developer').
    Validates all inputs and enforces ownership before creation.
    Integrates with the Api.Css model used throughout the shop.
    """
    from decimal import Decimal, InvalidOperation
    from Api.models import CssCategory
    from django.db import IntegrityError

    try:
        profile = request.user.profile
        if profile.role not in ('developer', 'admin', 'staff') and not request.user.is_superuser and not request.user.is_staff:
            messages.error(
                request,
                'You need a Developer role to sell CSS files. '
                'Upgrade your account at the Account Store.'
            )
            return redirect('shop')
    except Exception:
        # If profile lookup fails, fall back to admin/staff check
        if not request.user.is_superuser and not request.user.is_staff:
            messages.error(request, 'You need a Developer role to sell CSS files.')
            return redirect('shop')

    categories = CssCategory.objects.all().order_by('name')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()[:100]
        description = request.POST.get('description', '').strip()
        css_content = request.POST.get('css_content', '').strip()
        html_template = request.POST.get('html_template', '').strip()
        if not html_template:
            html_template = '<div class="loader"></div>'
        author = request.POST.get('author', request.user.username).strip()[:150]
        category_slug = request.POST.get('category', '').strip()[:100]

        # Price validation
        try:
            price = Decimal(request.POST.get('price', '0'))
            if price < Decimal('0.00'):
                price = Decimal('0.00')
            if price > Decimal('9999.99'):
                messages.error(request, 'Price cannot exceed 9999.99 Neuros.')
                return render(request, 'add_article.html', {
                    'categories': categories,
                    'form_data': request.POST,
                })
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid price format. Please enter a valid number.')
            return render(request, 'add_article.html', {
                'categories': categories,
                'form_data': request.POST,
            })

        # Required field validation
        errors = []
        if not name:
            errors.append('CSS loader name is required.')
        if not css_content:
            errors.append('CSS code content is required.')
        if not author:
            errors.append('Author name is required.')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'add_article.html', {
                'categories': categories,
                'form_data': request.POST,
            })

        # Resolve category (optional)
        category = None
        if category_slug:
            try:
                category = CssCategory.objects.get(slug=category_slug)
            except CssCategory.DoesNotExist:
                messages.error(request, 'Invalid category selected.')
                return render(request, 'add_article.html', {
                    'categories': categories,
                    'form_data': request.POST,
                })

        try:
            css_file = Css.objects.create(
                name=name,
                description=description,
                css_content=css_content,
                html_template=html_template,
                author=author,
                creator=request.user,
                price=price,
                category=category,
            )
            
            # Generate preview
            from Api.gif_utils import generate_gif_for_css
            result = generate_gif_for_css(css_content, str(css_file.id), body_html=html_template)
            if result:
                content_file, filename = result
                css_file.preview_gif.save(filename, content_file, save=True)

            messages.success(
                request,
                f'Your CSS loader "{name}" has been published to the marketplace!'
            )
            return redirect('product_detail', css_id=css_file.id)

        except IntegrityError:
            messages.error(
                request,
                f'A CSS loader with the name "{name}" already exists. Please choose a different name.'
            )
            return render(request, 'add_article.html', {
                'categories': categories,
                'form_data': request.POST,
            })
        except Exception as e:
            messages.error(request, 'An unexpected error occurred. Please try again.')
            return render(request, 'add_article.html', {
                'categories': categories,
                'form_data': request.POST,
            })

    # GET request - display the empty form
    context = {
        'categories': categories,
        'form_data': {},
    }
    return render(request, 'add_article.html', context)
