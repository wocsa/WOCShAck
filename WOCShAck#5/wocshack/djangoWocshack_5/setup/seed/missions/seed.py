"""Seed shared onboarding missions."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
django.setup()

from setup.seed import SEED_TAG, get_demo_users, jitter


def seed():
    from Todo.models import Mission
    from setup.seed import get_personas
    import random

    personas = get_personas()
    all_users = personas['users']
    staff = personas['staff'] or all_users
    developers = personas['developers'] or all_users

    missions_data = [
        {
            'title': 'Complete your profile',
            'description': f'Fill in your biography, upload a profile picture, and enable 2FA for full access.',
            'priority': Mission.Priority.MEDIUM,
            'category': 'onboarding',
            'is_staff_shared': True,
        },
        {
            'title': 'Explore the CSS Marketplace',
            'description': f'Browse the shop, check out at least 3 CSS files, and leave a review on one you like.',
            'priority': Mission.Priority.LOW,
            'category': 'exploration',
            'is_staff_shared': True,
        },
        {
            'title': 'Post in the Community Forum',
            'description': f'Introduce yourself in the General Discussion category and reply to at least one existing topic.',
            'priority': Mission.Priority.LOW,
            'category': 'community',
            'is_staff_shared': False,
        },
        {
            'title': 'Complete the Beginner CSS Tutorial',
            'description': f'Work through the "Build Your First CSS Loader" tutorial and pass all quizzes.',
            'priority': Mission.Priority.HIGH,
            'category': 'learning',
            'is_staff_shared': True,
        },
        {
            'title': 'Set up banking & claim welcome bonus',
            'description': f'Create your VRC bank account, set a PIN, and claim your welcome bonus Neuros.',
            'priority': Mission.Priority.HIGH,
            'category': 'onboarding',
            'is_staff_shared': False,
        },
    ]

    created = 0
    for user in all_users:
        # Give everyone 1-4 random missions
        count = random.randint(1, len(missions_data))
        user_missions = random.sample(missions_data, count)
        for md in user_missions:
            # Only staff share staff_shared missions literally if they are staff
            is_staff_shared = md['is_staff_shared'] and user in staff
            
            jitter(0.1, 0.3)
            _, new = Mission.objects.get_or_create(title=md['title'], user=user, defaults={**md, 'is_staff_shared': is_staff_shared})
            if new:
                created += 1

    print(f'[+] Missions: {created} missions created across {len(all_users)} users.')


if __name__ == '__main__':
    seed()

