#!/usr/bin/env python
"""
Forum setup script.
Creates initial categories for the forum module.
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings')
django.setup()

from Forum.models import Category


def create_categories():
    """Create initial forum categories"""
    categories = [
        {
            'name': 'General Discussion',
            'slug': 'general',
            'description': 'General discussions about V.R.C platform and community topics.',
            'icon': 'chat-bubble-left-right',
            'order': 1,
        },
        {
            'name': 'CSS Showcase',
            'slug': 'css-showcase',
            'description': 'Share your CSS creations and get feedback from the community.',
            'icon': 'sparkles',
            'order': 2,
        },
        {
            'name': 'Help & Support',
            'slug': 'help-support',
            'description': 'Get help with using the platform or creating CSS files.',
            'icon': 'question-mark-circle',
            'order': 3,
        },
        {
            'name': 'Bug Reports',
            'slug': 'bug-reports',
            'description': 'Report bugs and issues with the V.R.C platform.',
            'icon': 'exclamation-triangle',
            'order': 4,
        },
        {
            'name': 'Feature Requests',
            'slug': 'feature-requests',
            'description': 'Suggest new features and improvements for the platform.',
            'icon': 'light-bulb',
            'order': 5,
        },
        {
            'name': 'Off-Topic',
            'slug': 'off-topic',
            'description': 'Casual conversations and discussions not related to V.R.C.',
            'icon': 'chat-bubble-oval-left-ellipsis',
            'order': 6,
        },
    ]

    created_count = 0
    for cat_data in categories:
        category, created = Category.objects.get_or_create(
            slug=cat_data['slug'],
            defaults=cat_data
        )
        if created:
            print(f"Created category: {category.name}")
            created_count += 1
        else:
            print(f"Category already exists: {category.name}")

    print(f"\nTotal categories created: {created_count}")
    print(f"Total categories in database: {Category.objects.count()}")


if __name__ == '__main__':
    print("Setting up Forum categories...")
    print("=" * 50)
    create_categories()
    print("=" * 50)
    print("Forum setup complete!")
