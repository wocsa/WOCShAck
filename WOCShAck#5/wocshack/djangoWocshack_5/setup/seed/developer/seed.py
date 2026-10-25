"""Seed developer portal: plans, profile, subscription, balance, projects, and promotions."""
import os
import django
from datetime import timedelta
from decimal import Decimal
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
django.setup()

from django.utils import timezone
from setup.seed import SEED_TAG, get_demo_users, jitter


def seed():
    from Developer.models import (
        DeveloperPlan, DeveloperProfile, DeveloperSubscription,
        DeveloperBalance, CssProject, CssVersion, CssListing,
        PricingTier, Promotion,
    )
    from setup.seed import get_personas
    import random

    personas = get_personas()
    developers = personas['developers'] or personas['users']
    now = timezone.now()

    # -- Plans --
    free_plan, _ = DeveloperPlan.objects.get_or_create(
        slug='seed-free',
        defaults={
            'name': 'Free', 'price_monthly': Decimal('0.00'), 'price_yearly': Decimal('0.00'),
            'css_limit': 5, 'api_calls_limit': 1000, 'commission_rate': Decimal('0.60'),
            'features': {'editor': True, 'analytics_basic': True}, 'is_active': True,
        },
    )
    pro_plan, _ = DeveloperPlan.objects.get_or_create(
        slug='seed-pro',
        defaults={
            'name': 'Pro', 'price_monthly': Decimal('9.99'), 'price_yearly': Decimal('99.99'),
            'css_limit': 50, 'api_calls_limit': 50000, 'commission_rate': Decimal('0.80'),
            'features': {'editor': True, 'analytics_advanced': True, 'priority_review': True, 'webhooks': True},
            'is_active': True,
        },
    )

    projects_data = [
        {
            'name': 'Neon Loaders Pack',
            'description': 'A collection of neon-themed CSS loading animations.',
            'css': '.neon-loader{width:48px;height:48px;border-radius:50%;border:4px solid #0ff;border-top-color:transparent;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}',
            'html': '<div class="neon-loader"></div>',
            'version': '2.1.0',
            'price': Decimal('4.99'),
            'tags': 'loaders, neon, animation',
        },
        {
            'name': 'Glassmorphism UI Kit',
            'description': 'Modern frosted-glass components for web applications.',
            'css': '.glass-card{background:rgba(255,255,255,.15);backdrop-filter:blur(12px);border-radius:16px;border:1px solid rgba(255,255,255,.2);padding:2rem}',
            'html': '<div class="glass-card"><h3>Glass Card</h3><p>Content here</p></div>',
            'version': '1.3.0',
            'price': Decimal('7.50'),
            'tags': 'glassmorphism, ui, components',
        },
    ]

    created = 0
    
    # Iterate over all developers to give them profiles and balances
    for i, dev in enumerate(developers):
        # -- Profile --
        DeveloperProfile.objects.get_or_create(
            user=dev,
            defaults={
                'display_name': dev.get_full_name() or dev.username.title(),
                'tagline': dev.profile.biography[:100] if dev.profile.biography else 'Crafting beautiful CSS, one keyframe at a time.',
                'website': f'https://{dev.username.lower()}.dev',
                'github_url': f'https://github.com/{dev.username.lower()}',
                'specialties': random.sample(['animations', 'glassmorphism', 'loaders', 'dark-mode', 'grids', 'buttons'], k=random.randint(2, 4)),
                'commission_rate': Decimal('0.80') if i % 2 == 0 else Decimal('0.60'),
                'is_verified': True,
                'verified_at': now - timedelta(days=random.randint(1, 30)),
            },
        )

        # -- Subscription --
        DeveloperSubscription.objects.get_or_create(
            user=dev, plan=pro_plan if i % 2 == 0 else free_plan,
            defaults={
                'status': DeveloperSubscription.Status.ACTIVE,
                'current_period_start': now - timedelta(days=15),
                'current_period_end':   now + timedelta(days=15),
            },
        )

        # -- Balance --
        DeveloperBalance.objects.get_or_create(
            developer=dev,
            defaults={
                'available': Decimal(str(random.randint(10, 100))) + Decimal('0.50'), 'pending': Decimal(str(random.randint(5, 50))) + Decimal('0.00'),
                'total_earned': Decimal(str(random.randint(100, 500))) + Decimal('0.75'), 'total_paid': Decimal(str(random.randint(50, 400))) + Decimal('0.25'),
            },
        )
        
        pd = projects_data[i % len(projects_data)]  # distribute projects across developers
        if not CssProject.objects.filter(developer=dev, name=pd['name']).exists():
            jitter(0.5, 1.5)
            project, new = CssProject.objects.get_or_create(
                developer=dev, name=pd['name'],
                defaults={'description': pd['description'], 'status': CssProject.Status.PUBLISHED},
            )
            if new:
                CssVersion.objects.create(
                    project=project, version_number=pd['version'],
                    css_content=pd['css'], html_template=pd['html'],
                    commit_message=f'Release {pd["version"]}', is_current=True,
                )
                listing = CssListing.objects.create(
                    project=project, developer=dev, title=pd['name'],
                    description=pd['description'], license_type=CssListing.LicenseType.PERSONAL,
                    tags=pd['tags'], status=CssListing.Status.PUBLISHED,
                    published_at=now - timedelta(days=random.randint(1, 10)),
                )
                PricingTier.objects.create(
                    listing=listing, name='Personal License', price=pd['price'],
                    scope=PricingTier.Scope.PERSONAL, includes_source=True,
                )
                PricingTier.objects.create(
                    listing=listing, name='Commercial License', price=pd['price'] * 3,
                    scope=PricingTier.Scope.COMMERCIAL, includes_source=True, includes_support=True,
                )
                created += 1

    # -- Promotions --
    Promotion.objects.get_or_create(
        code='SEEDDEVLAUNCH',
        defaults={
            'discount_percent': Decimal('15.00'),
            'start_date': now - timedelta(days=5),
            'end_date': now + timedelta(days=25),
            'usage_limit': 30,
            'is_active': True,
        },
    )

    print(f'[+] Developer: plans, profiles, subscriptions, balances created for {len(developers)} devs, with {created} projects.')


if __name__ == '__main__':
    seed()

