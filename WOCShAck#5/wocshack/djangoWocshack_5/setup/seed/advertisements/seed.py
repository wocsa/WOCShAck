"""Seed demo advertisements."""
import os
import django
from datetime import timedelta
from decimal import Decimal
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
django.setup()

from django.utils import timezone
from setup.seed import SEED_TAG, get_demo_users, jitter


def seed():
    from Advertisement.models import Advertisement
    from setup.seed import get_personas
    import random

    personas = get_personas()
    business = personas['business'] or personas['users']
    staff = personas['staff'] or personas['users']
    now = timezone.now()

    ads_data = [
        {
            'title': 'New CSS Loaders Collection — 50+ Animations',
            'body': (
                f'Discover our premium collection of **50+ pure CSS loaders**.\n\n'
                f'- Lightweight & performant\n'
                f'- No JavaScript required\n'
                f'- Fully customisable\n\n'
                f'Use code **SEEDWELCOME10** for 10% off!'
            ),
            'target_url': '/shop',
            'placement_zone': Advertisement.PlacementZone.SHOP_SIDEBAR,
            'budget_neuros': Decimal('200.00'),
            'status': Advertisement.Status.ACTIVE,
            'start_date': now - timedelta(days=3),
            'end_date': now + timedelta(days=27),
        },
        {
            'title': 'Developer Portal — Start Selling Your CSS',
            'body': (
                f'Turn your CSS skills into **passive income**.\n\n'
                f'The VRC Developer Portal offers:\n'
                f'- Built-in code editor\n'
                f'- Sales analytics dashboard\n'
                f'- Automated payouts\n\n'
                f'Sign up today and publish your first CSS file for free!'
            ),
            'target_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'placement_zone': Advertisement.PlacementZone.HOMEPAGE_BANNER,
            'budget_neuros': Decimal('300.00'),
            'status': Advertisement.Status.ACTIVE,
            'start_date': now - timedelta(days=5),
            'end_date': now + timedelta(days=25),
        },
    ]

    created = 0
    for ad in ads_data:
        if Advertisement.objects.filter(title=ad['title']).exists():
            continue
        jitter(1.0, 3.0)
        Advertisement.objects.create(
            advertiser=random.choice(business),
            reviewed_by=random.choice(staff),
            reviewed_at=now - timedelta(days=1),
            **ad,
        )
        created += 1

    print(f'[+] Advertisements: {created} created.')


if __name__ == '__main__':
    seed()

