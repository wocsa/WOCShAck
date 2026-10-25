import json
import time
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from Api.models import Css, CssCategory, Purchase
from Shopping.models import Order, OrderItem, OrderStatus, Cart, CartItem, Review, Coupon, CouponUsage
from Bank.models import BankCard, Transaction as BankTransaction
from Bank.Utils import client

from .views import api_success, api_error, api_auth_required, paginate_queryset


@require_http_methods(["GET"])
def products_view(request, css_id=None):
    """
    List products or get details of a specific product.
    Supports search, category filtering, and sorting.
    """
    if css_id:
        try:
            css = Css.objects.select_related('category', 'creator').get(id=css_id)
            reviews = Review.objects.filter(css_file=css, is_approved=True)
            avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0.0
            
            data = {
                "id": str(css.id),
                "name": css.name,
                "author": css.author,
                "creator": css.creator.username,
                "price": float(css.price),
                "category": css.category.name if css.category else None,
                "created_at": css.created_at.isoformat(),
                "stats": {
                    "avg_rating": float(avg_rating),
                    "review_count": reviews.count(),
                    "purchase_count": Purchase.objects.filter(css_file=css).count()
                }
            }
            return api_success({"product": data})
        except Css.DoesNotExist:
            return api_error("Product not found.", status=404)

    # List all products
    queryset = Css.objects.select_related('category', 'creator').all()
    
    # Filter by category
    category_slug = request.GET.get('category')
    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)
        
    # Search by name
    search = request.GET.get('q')
    if search:
        queryset = queryset.filter(name__icontains=search)
        
    # Sorting
    sort_by = request.GET.get('sort', '-created_at')
    valid_sorts = ['created_at', '-created_at', 'price', '-price', 'name', '-name']
    if sort_by in valid_sorts:
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by('-created_at')

    paginated = paginate_queryset(queryset, request)
    products_data = []
    
    for css in paginated['items']:
        products_data.append({
            "id": str(css.id),
            "name": css.name,
            "author": css.author,
            "creator": css.creator.username,
            "price": float(css.price),
            "category": css.category.name if css.category else None,
        })

    return api_success({
        "products": products_data,
        "pagination": paginated['pagination']
    })


@require_http_methods(["POST"])
@api_auth_required
def cart_add_view(request):
    """
    Add a product to cart.
    Accepts {"css_id": "uuid", "quantity": 1}
    """
    try:
        data = json.loads(request.body)
        css_id = data.get('css_id')
        quantity = int(data.get('quantity', 1))
    except (json.JSONDecodeError, ValueError, TypeError):
        return api_error("Invalid payload structure.", status=400)

    if not css_id:
        return api_error("css_id is required.", status=400)
        
    if quantity < 1 or quantity > 100:
        return api_error("Quantity must be between 1 and 100.", status=400)

    try:
        css = Css.objects.get(id=css_id)
    except Css.DoesNotExist:
        return api_error("Product not found.", status=404)

    cart_obj = Cart.get_or_create_for_request(request)
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart_obj,
        css_file=css,
        defaults={'quantity': quantity}
    )

    if not created:
        new_quantity = cart_item.quantity + quantity
        if new_quantity <= 100:
            cart_item.quantity = new_quantity
            cart_item.save()
        else:
            return api_error("Cannot exceed maximum quantity of 100 for a single item.", status=400)

    return api_success({"message": "Item added to cart", "cart_count": cart_obj.get_item_count()})


@require_http_methods(["GET"])
@api_auth_required
def cart_view(request):
    """
    View cart items and total.
    """
    cart_obj = Cart.get_or_create_for_request(request)
    items = cart_obj.cart_items.select_related('css_file')
    
    data = []
    for item in items:
        data.append({
            "item_id": str(item.id),
            "css_id": str(item.css_file.id),
            "name": item.css_file.name,
            "price": float(item.css_file.price),
            "quantity": item.quantity,
            "total": float(item.get_total())
        })
        
    return api_success({
        "items": data,
        "total": float(cart_obj.get_total()),
        "item_count": cart_obj.get_item_count()
    })


@require_http_methods(["POST"])
@api_auth_required
def cart_update_view(request):
    """
    Update item quantity in cart.
    Accepts {"css_id": "uuid", "quantity": 5}
    """
    try:
        data = json.loads(request.body)
        css_id = data.get('css_id')
        quantity = int(data.get('quantity', 1))
    except (json.JSONDecodeError, ValueError, TypeError):
        return api_error("Invalid payload structure.", status=400)

    if not css_id:
        return api_error("css_id is required.", status=400)

    cart_obj = Cart.get_or_create_for_request(request)
    
    if quantity <= 0:
        CartItem.objects.filter(cart=cart_obj, css_file_id=css_id).delete()
        return api_success({"message": "Item removed from cart"})
        
    quantity = min(quantity, 100)
    updated = CartItem.objects.filter(cart=cart_obj, css_file_id=css_id).update(quantity=quantity)
    
    if updated:
        return api_success({"message": "Cart updated"})
    return api_error("Item not found in cart.", status=404)


@require_http_methods(["DELETE"])
@api_auth_required
def cart_remove_view(request, css_id):
    """
    Remove an item from the cart.
    """
    cart_obj = Cart.get_or_create_for_request(request)
    deleted, _ = CartItem.objects.filter(cart=cart_obj, css_file_id=css_id).delete()
    if deleted:
        return api_success({"message": "Item removed from cart"})
    return api_error("Item not found in cart.", status=404)


@require_http_methods(["POST"])
@api_auth_required
def checkout_view(request):
    """
    Process checkout for current cart.
    Requires password, pin, card_number and billing info.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return api_error("Invalid JSON format.", status=400)

    password = str(data.get("password", "")).strip()
    pin = str(data.get("pin", "")).strip()
    card_number = str(data.get("card_number", "")).strip()[:16]
    first_name = str(data.get("first_name", "")).strip()[:100]
    last_name = str(data.get("last_name", "")).strip()[:100]
    email = str(data.get("email", "")).strip()[:254]
    
    if not all([password, pin, card_number, first_name, last_name, email]):
        return api_error("All billing and authentication fields are required.", status=400)

    # Validate Auth
    if not request.user.check_password(password):
        return api_error("Incorrect account password.", status=403)

    from Bank.Utils.external_calls import verify_user_pin
    if not verify_user_pin(request.user.id, pin):
        return api_error("Incorrect bank PIN.", status=403)

    try:
        card = BankCard.objects.get(user=request.user, payment_number=card_number)
        if card.status == 'frozen':
            return api_error("Card is frozen.", status=403)
        if card.status == 'cancelled':
            return api_error("Card is cancelled.", status=403)
    except BankCard.DoesNotExist:
        return api_error("Invalid or unknown bank card.", status=404)

    # Cart check
    cart_obj = Cart.get_or_create_for_request(request)
    cart_items = cart_obj.cart_items.select_related('css_file')
    if not cart_items.exists():
        return api_error("Your cart is empty.", status=400)

    # Reject self-purchases and already-owned items before touching the bank.
    self_products = [ci.css_file.name for ci in cart_items if ci.css_file.creator == request.user]
    if self_products:
        return api_error(
            f"You cannot purchase your own product(s): {', '.join(self_products)}. "
            "Remove them from your cart before checking out.",
            status=400,
        )

    already_owned = [
        ci.css_file.name for ci in cart_items
        if Purchase.objects.filter(user=request.user, css_file=ci.css_file).exists()
    ]
    if already_owned:
        return api_error(
            f"You already own: {', '.join(already_owned)}. "
            "Remove already-purchased items from your cart before checking out.",
            status=400,
        )

    total = cart_obj.get_total()

    # Apply coupon if provided
    coupon_code = str(data.get("coupon_code", "")).strip().upper()
    coupon_discount = Decimal('0.00')
    applied_coupon = None
    if coupon_code:
        try:
            coupon = Coupon.objects.get(code__iexact=coupon_code)
            is_valid, _msg = coupon.is_valid(order_total=total, user=request.user)
            if is_valid:
                coupon_discount = coupon.calculate_discount(total)
                applied_coupon = coupon
            else:
                return api_error(f"Coupon invalid: {_msg}", status=400)
        except Coupon.DoesNotExist:
            return api_error("Coupon code not found.", status=404)

    final_total = max(total - coupon_discount, Decimal('0.00'))

    cli, sid = client.make_connection()
    if not cli or not sid:
        return api_error("Banking system offline. Try again later.", status=503)

    try:
        user_response = cli.get_user(sid, request.user.id)
        time.sleep(0.3)
        if not (isinstance(user_response, dict) and user_response.get("success")):
            return api_error("Bank account not recognized.", status=404)

        user_data = user_response.get("user", {})
        current_balance = Decimal(str(user_data.get("balance", 0)))
        user_id = user_data.get("id")

        if final_total > current_balance:
            return api_error("Insufficient funds in bank account.", status=400)

        # Process the payments — one transaction per seller
        payment_success = True
        transaction_errors = []

        for cart_item in cart_items:
            css = cart_item.css_file
            seller_id = css.creator.id
            item_total = float(css.price * cart_item.quantity)

            result = cli.transaction(sid=sid, from_user=user_id, to_user=seller_id, amount=item_total)
            time.sleep(0.3)

            if not result or result.get('status') != 'success':
                payment_success = False
                err = result.get('message', 'Failed') if result else 'No response'
                transaction_errors.append(f"{css.name}: {err}")
                break

        if not payment_success:
            BankTransaction.objects.create(
                user=request.user, card=card, transaction_type='payment',
                amount=final_total, counterpart_label='API Marketplace Checkout',
                note=f"Failed payment: {', '.join(transaction_errors)}"[:500], status='failed'
            )
            return api_error("Payment failed. Some items may have failed to process.", status=400)

        # Success — create order, purchase records, and record coupon usage
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user, total_amount=final_total,
                discount_amount=coupon_discount,
                coupon_code=applied_coupon.code if applied_coupon else None,
                billing_first_name=first_name, billing_last_name=last_name, billing_email=email,
                status=OrderStatus.COMPLETED, completed_at=timezone.now()
            )

            for cart_item in cart_items:
                css = cart_item.css_file
                OrderItem.objects.create(
                    order=order, css_file=css, css_name=css.name, css_author=css.author,
                    price_at_purchase=css.price, quantity=cart_item.quantity
                )
                Purchase.objects.create(user=request.user, css_file=css, price_paid=css.price)

            if applied_coupon:
                CouponUsage.objects.create(coupon=applied_coupon, user=request.user, order=order)

            cart_obj.clear()

        BankTransaction.objects.create(
            user=request.user, card=card, transaction_type='payment',
            amount=final_total, counterpart_label='API Marketplace Checkout',
            note=f'Order #{order.id} - API Checkout', status='completed'
        )

        return api_success({"order_id": str(order.id)}, message="Checkout completed successfully.", status=201)
    finally:
        try:
            cli.close_session(sid)
            cli.close()
        except:
            pass


@require_http_methods(["GET"])
@api_auth_required
def orders_view(request, order_id=None):
    """
    List past orders or view details of a specific order.
    """
    if order_id:
        order = get_object_or_404(Order, id=order_id, user=request.user)
        items_data = []
        for item in order.items.all():
            items_data.append({
                "css_name": item.css_name,
                "quantity": item.quantity,
                "price": float(item.price_at_purchase),
                "total": float(item.get_total())
            })
            
        return api_success({
            "order": {
                "id": str(order.id),
                "status": order.status,
                "total": float(order.get_final_total()),
                "discount": float(order.discount_amount),
                "coupon": order.coupon_code,
                "created_at": order.created_at.isoformat(),
                "billing": {
                    "first_name": order.billing_first_name,
                    "last_name": order.billing_last_name,
                    "email": order.billing_email,
                },
                "items": items_data
            }
        })

    orders = Order.objects.filter(user=request.user).prefetch_related('items').order_by('-created_at')
    paginated = paginate_queryset(orders, request)
    
    orders_data = []
    for order in paginated['items']:
        items_data = []
        for item in order.items.all():
            items_data.append({
                "css_name": item.css_name,
                "quantity": item.quantity,
                "price": float(item.price_at_purchase),
                "total": float(item.get_total())
            })
            
        orders_data.append({
            "id": str(order.id),
            "status": order.status,
            "total": float(order.get_final_total()),
            "created_at": order.created_at.isoformat(),
            "items": items_data
        })

    return api_success({
        "orders": orders_data,
        "pagination": paginated['pagination']
    })

@require_http_methods(["POST"])
@api_auth_required
def coupon_apply_view(request):
    """
    Validate and apply a coupon to an API cart checkout session.
    """
    try:
        data = json.loads(request.body)
        code = data.get('code', '').strip().upper()
    except (json.JSONDecodeError, AttributeError):
        return api_error("Invalid payload.", status=400)
        
    if not code:
        return api_error("Coupon code required.", status=400)
        
    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        return api_error("Invalid coupon code.", status=404)
        
    cart_obj = Cart.get_or_create_for_request(request)
    cart_total = cart_obj.get_total()
    
    is_valid, msg = coupon.is_valid(order_total=cart_total, user=request.user)
    if not is_valid:
        return api_error(msg, status=400)
        
    discount = coupon.calculate_discount(cart_total)
    # The actual API client will have to send the coupon code in the checkout payload.
    # This endpoint is just for calculating validity and discounts dynamically.
    return api_success({
        "valid": True,
        "discount_amount": float(discount),
        "code": coupon.code,
        "message": f"Coupon valid. Applies a discount of {discount} Neuros."
    })


from Shopping.models import Wishlist

@require_http_methods(["GET", "POST"])
@api_auth_required
def wishlist_view(request, css_id=None):
    """
    Manage the user's wishlist via API.
    """
    if request.method == "GET":
        items = Wishlist.objects.filter(user=request.user).select_related('css_file')
        data = []
        for item in items:
            data.append({
                "css_id": str(item.css_file.id),
                "name": item.css_file.name,
                "price": float(item.css_file.price),
                "added_at": item.added_at.isoformat()
            })
        return api_success({"wishlist": data})
        
    elif request.method == "POST":
        if not css_id:
            try:
                data = json.loads(request.body)
                css_id = data.get('css_id')
            except:
                return api_error("css_id is required.", status=400)
                
        try:
            css = Css.objects.get(id=css_id)
        except Css.DoesNotExist:
            return api_error("Product not found.", status=404)
            
        Wishlist.objects.get_or_create(user=request.user, css_file=css)
        return api_success({"message": "Product added to wishlist."})
        
@require_http_methods(["POST"])
@api_auth_required
def wishlist_add_view(request, css_id):
    """POST-only wishlist add alias."""
    return wishlist_view(request, css_id=css_id)


@require_http_methods(["DELETE"])
@api_auth_required
def wishlist_remove_view(request, css_id):
    """DELETE-only wishlist remove alias."""
    deleted, _ = Wishlist.objects.filter(user=request.user, css_file_id=css_id).delete()
    if deleted:
        return api_success({"message": "Product removed from wishlist."})
    return api_error("Product not in wishlist.", status=404)


@require_http_methods(["GET", "POST"])
def reviews_view(request, css_id):
    """
    View and submit reviews for a product.
    """
    try:
        css_file = Css.objects.get(id=css_id)
    except Css.DoesNotExist:
        return api_error("Product not found.", status=404)

    if request.method == "GET":
        reviews = css_file.reviews.filter(is_approved=True).select_related('user').order_by('-created_at')
        paginated = paginate_queryset(reviews, request)
        
        data = []
        for r in paginated['items']:
            data.append({
                "id": str(r.id),
                "user": r.user.username,
                "rating": r.rating,
                "title": r.title,
                "content": r.content,
                "verified": r.is_verified_purchase,
                "created_at": r.created_at.isoformat()
            })
        return api_success({"reviews": data, "pagination": paginated['pagination']})

    elif request.method == "POST":
        if not request.user.is_authenticated:
            return api_error("Authentication required.", status=401)
            
        if Review.objects.filter(user=request.user, css_file=css_file).exists():
            return api_error("You have already reviewed this product.", status=400)
            
        try:
            data = json.loads(request.body)
            rating = int(data.get('rating', 0))
            title = str(data.get('title', '')).strip()[:200]
            content = str(data.get('content', '')).strip()[:5000]
        except (json.JSONDecodeError, ValueError, TypeError):
            return api_error("Invalid payload format.", status=400)
            
        if not 1 <= rating <= 5:
            return api_error("Rating must be between 1 and 5.", status=400)
        if not title or not content:
            return api_error("Title and content are required.", status=400)
            
        is_verified = Purchase.objects.filter(user=request.user, css_file=css_file).exists()
        
        Review.objects.create(
            user=request.user,
            css_file=css_file,
            rating=rating,
            title=title,
            content=content,
            is_verified_purchase=is_verified
        )
        return api_success({"message": "Review submitted successfully"}, status=201)
