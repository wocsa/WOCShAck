"""Seed reviews, coupons, orders, and wishlists."""
import os
import django
from datetime import timedelta
from decimal import Decimal
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
django.setup()

from django.utils import timezone
from setup.seed import SEED_TAG, get_demo_users, jitter

# Product names as seeded by marketplace/seed.py — used to look up objects from the DB.
_PRODUCT_NAMES = [
    'Neon Pulse Loader', 'Glassmorphism Card', 'Ripple Button',
    'Aurora Background', 'Skeleton Screen', 'Neumorphic Toggle', 'Typewriter Effect',
]


def seed():
    from Api.models import Css
    from Shopping.models import Review, Order, OrderItem, Coupon, Wishlist
    from setup.seed import get_personas
    import random

    personas = get_personas()
    all_users = personas['users']
    business = personas['business'] or all_users
    designers = personas['designers'] or all_users
    now = timezone.now()

    # Look up CSS products created by marketplace/seed.py
    css_products = list(Css.objects.filter(name__in=_PRODUCT_NAMES).order_by('name'))

    # -- Reviews --
    review_data = [
        (0, 5, 'Absolutely love this!',  'Clean code, smooth animation, works perfectly on all browsers. Best loader I\'ve purchased.'),
        (1, 4, 'Great design',            'Beautiful glassmorphism effect. Only minor issue — needed a small tweak for Safari.'),
        (2, 5, 'Simple and effective',    'The ripple effect is buttery smooth. Integrated it into my landing page in minutes.'),
        (0, 4, 'Very professional',       'High quality CSS with clean keyframes. Recommended for any project.'),
        (3, 5, 'Stunning backgrounds',    'The aurora gradient is gorgeous. Exactly what my portfolio needed.'),
        (4, 4, 'Nice skeleton loader',    'Good implementation. The wave effect is convincing and performant.'),
        (6, 5, 'Clever typewriter CSS',   'No JS needed — pure CSS typewriter effect that actually works well.'),
    ]

    for idx, rating, title, content in review_data:
        if idx >= len(css_products):
            continue
        css_file = css_products[idx]
        # Choose a random reviewer who is not the creator
        possible_reviewers = [u for u in all_users if u != css_file.creator]
        if not possible_reviewers:
            continue
        reviewer = random.choice(possible_reviewers)
        
        jitter(0.5, 2.0)
        Review.objects.get_or_create(
            css_file=css_file,
            user=reviewer,
            defaults={
                'rating': rating, 'title': title, 'content': content,
                'is_approved': True, 'is_verified_purchase': True,
            },
        )

    # -- Coupons --
    Coupon.objects.get_or_create(
        code='SEEDWELCOME10',
        defaults={
            'description': 'Welcome discount — 10% off your first order',
            'discount_type': Coupon.DiscountType.PERCENTAGE,
            'discount_value': Decimal('10.00'),
            'max_uses': 100,
            'minimum_order_amount': Decimal('5.00'),
            'is_active': True,
            'valid_from': now - timedelta(days=30),
            'valid_until': now + timedelta(days=90),
        },
    )
    Coupon.objects.get_or_create(
        code='SEEDFLAT3',
        defaults={
            'description': '3 Neuros off any purchase over 10 NE',
            'discount_type': Coupon.DiscountType.FIXED,
            'discount_value': Decimal('3.00'),
            'max_uses': 50,
            'minimum_order_amount': Decimal('10.00'),
            'is_active': True,
            'valid_from': now - timedelta(days=7),
            'valid_until': now + timedelta(days=60),
        },
    )
    Coupon.objects.get_or_create(
        code='SEEDDEV20',
        defaults={
            'description': 'Developer appreciation — 20% off',
            'discount_type': Coupon.DiscountType.PERCENTAGE,
            'discount_value': Decimal('20.00'),
            'max_uses': 25,
            'minimum_order_amount': Decimal('0.00'),
            'is_active': True,
            'valid_from': now,
            'valid_until': now + timedelta(days=30),
        },
    )

    # -- Orders --
    # Create random orders for several users
    buyer1 = random.choice(designers)
    jitter(1.0, 3.0)
    if not Order.objects.filter(user=buyer1, coupon_code='SEEDWELCOME10').exists() and len(css_products) >= 3:
        order = Order.objects.create(
            user=buyer1, status='completed',
            total_amount=css_products[0].price + css_products[2].price,
            discount_amount=Decimal('0.00'), coupon_code='SEEDWELCOME10',
            billing_first_name=buyer1.first_name or 'Alex', billing_last_name=buyer1.last_name or 'Chen',
            billing_email=buyer1.email or 'demo_user@vrc-platform.local',
            completed_at=now - timedelta(days=5),
        )
        for prod in [css_products[0], css_products[2]]:
            OrderItem.objects.create(
                order=order, css_file=prod, css_name=prod.name, css_author=prod.author,
                price_at_purchase=prod.price, quantity=1,
            )

    buyer2 = random.choice(business)
    jitter(1.0, 3.0)
    if not Order.objects.filter(user=buyer2).exists() and len(css_products) >= 4:
        order2 = Order.objects.create(
            user=buyer2, status='completed',
            total_amount=css_products[3].price, discount_amount=Decimal('0.00'),
            billing_first_name=buyer2.first_name or 'Riley', billing_last_name=buyer2.last_name or 'Park',
            billing_email=buyer2.email or 'demo_ads@vrc-platform.local',
            completed_at=now - timedelta(days=2),
        )
        OrderItem.objects.create(
            order=order2, css_file=css_products[3], css_name=css_products[3].name,
            css_author=css_products[3].author, price_at_purchase=css_products[3].price, quantity=1,
        )

    # -- Wishlists --
    if len(css_products) >= 5:
        # Give random users some wishlist items
        for user in all_users:
            wish_count = random.randint(0, 3)
            if wish_count > 0:
                wish_choices = random.sample(css_products, wish_count)
                for prod in wish_choices:
                    Wishlist.objects.get_or_create(user=user, css_file=prod)

    print('[+] Shopping: reviews, coupons, orders, and wishlists seeded across multiple personas.')


if __name__ == '__main__':
    seed()

