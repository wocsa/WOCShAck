"""
Seed orchestrator — runs all seed scripts in order.

Each sub-script is invoked as a separate process so it can also be run
standalone (e.g. python setup/seed/forum/seed.py).

Usage:
    python setup/seed/seed_all.py           # seed everything
    python setup/seed/seed_all.py --flush   # wipe seeded data then re-seed
"""
import argparse
import os
import subprocess
import sys

BASE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))

SCRIPTS = [
    ('setup/seed/forum/seed.py',          'Forum'),
    ('setup/seed/community/seed.py',      'Community'),
    ('setup/seed/marketplace/seed.py',    'CSS marketplace'),
    ('setup/seed/shopping/seed.py',       'Shopping'),
    ('setup/seed/advertisements/seed.py', 'Advertisements'),
    ('setup/seed/developer/seed.py',      'Developer portal'),
    ('setup/seed/chatbot/seed.py',        'Chatbot knowledge base'),
    ('setup/seed/missions/seed.py',       'Missions'),
]


def _env():
    env = os.environ.copy()
    env['PYTHONPATH'] = BASE_DIR + os.pathsep + env.get('PYTHONPATH', '')
    return env


def run(script, description):
    print(f'\n  [{description}]')
    result = subprocess.run([sys.executable, script], cwd=BASE_DIR, env=_env())
    if result.returncode != 0:
        print(f'[X] Failed: {description} (exit {result.returncode})')
        sys.exit(result.returncode)


def flush():
    """Delete all objects previously created by any seed script."""
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
    sys.path.insert(0, BASE_DIR)
    django.setup()

    from setup.seed import SEED_TAG
    from setup.seed import get_personas
    from django.contrib.auth.models import User

    print('  Flushing previous seed data ...')

    from Shopping.models import Wishlist, Review, OrderItem, Order, CouponUsage, Coupon
    from Advertisement.models import Advertisement
    from Developer.models import (
        Promotion, PricingTier, CssListing, CssVersion, CssProject,
        DeveloperSubscription, DeveloperProfile, DeveloperPlan, DeveloperBalance,
    )
    from Chatbot.models import KnowledgeBase
    from Todo.models import Mission
    from Forum.models import PostLike, Post, Topic, Category, UserReputation
    from Community.models.content import (
        EventRegistration, Event, ShowcaseVote, ShowcaseItem,
        TutorialQuiz, TutorialStep, TutorialProgress, Tutorial,
        BlogComment, BlogPost, BlogCategory,
    )
    from Api.models import Css, CssCategory

    # Include all non-admin users since they received seeds
    # + old standalone demo accounts
    personas = get_personas()
    seed_users = User.objects.filter(is_superuser=False)

    Mission.objects.filter(user__in=seed_users).delete()
    KnowledgeBase.objects.all().delete()
    Advertisement.objects.filter(advertiser__in=seed_users).delete()

    Promotion.objects.filter(code__startswith='SEED').delete()
    PricingTier.objects.filter(listing__developer__in=seed_users).delete()
    CssListing.objects.filter(developer__in=seed_users).delete()
    CssVersion.objects.filter(project__developer__in=seed_users).delete()
    CssProject.objects.filter(developer__in=seed_users).delete()
    DeveloperSubscription.objects.filter(user__in=seed_users).delete()
    DeveloperSubscription.objects.filter(plan__slug__startswith='seed-').delete()
    DeveloperProfile.objects.filter(user__in=seed_users).delete()
    DeveloperBalance.objects.filter(developer__in=seed_users).delete()
    DeveloperPlan.objects.filter(slug__startswith='seed-').delete()

    Wishlist.objects.filter(user__in=seed_users).delete()
    Review.objects.filter(user__in=seed_users).delete()
    CouponUsage.objects.filter(user__in=seed_users).delete()
    OrderItem.objects.filter(order__user__in=seed_users).delete()
    Order.objects.filter(user__in=seed_users).delete()
    Coupon.objects.filter(code__startswith='SEED').delete()

    PostLike.objects.filter(user__in=seed_users).delete()
    Post.objects.filter(author__in=seed_users).delete()
    Topic.objects.filter(author__in=seed_users).delete()
    Category.objects.filter(slug__in=['platform-announcements', 'developer-chat', 'css-help']).delete()
    UserReputation.objects.filter(user__in=seed_users).delete()

    EventRegistration.objects.filter(user__in=seed_users).delete()
    Event.objects.filter(organizer__in=seed_users).delete()
    ShowcaseVote.objects.filter(user__in=seed_users).delete()
    ShowcaseItem.objects.filter(author__in=seed_users).delete()
    
    tutorials = Tutorial.objects.filter(author__in=seed_users)
    TutorialQuiz.objects.filter(step__tutorial__in=tutorials).delete()
    TutorialStep.objects.filter(tutorial__in=tutorials).delete()
    TutorialProgress.objects.filter(tutorial__in=tutorials).delete()
    tutorials.delete()
    
    BlogComment.objects.filter(author__in=seed_users).delete()
    BlogPost.objects.filter(author__in=seed_users).delete()
    BlogCategory.objects.filter(slug__in=['css-techniques', 'platform-news']).delete()

    from setup.seed.marketplace.seed import CSS_PRODUCTS
    Css.objects.filter(name__in=[p['name'] for p in CSS_PRODUCTS]).delete()
    CssCategory.objects.filter(slug__in=['loaders', 'buttons', 'components', 'backgrounds', 'animations']).delete()

    # Delete old standalone demo accounts that are no longer used
    _OLD_DEMO_USERNAMES = ['demo_user', 'demo_developer', 'demo_staff', 'demo_advertiser']
    User.objects.filter(username__in=_OLD_DEMO_USERNAMES).delete()

    print('  Flushed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flush', action='store_true', help='Delete previously seeded data before re-seeding.')
    args = parser.parse_args()

    print('=' * 60)
    print('  Seeding demo data')
    print('=' * 60)

    if args.flush:
        flush()

    for script, description in SCRIPTS:
        run(script, description)

    print()
    print('=' * 60)
    print('  [+] Demo data seeded successfully.')
    print('=' * 60)


if __name__ == '__main__':
    main()
