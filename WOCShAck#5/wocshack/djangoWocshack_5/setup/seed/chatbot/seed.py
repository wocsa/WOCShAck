"""Seed chatbot knowledge base entries."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
django.setup()

from setup.seed import SEED_TAG, jitter


def seed():
    from Chatbot.models import KnowledgeBase

    entries = [
        {
            'question': 'How do I create an account on VRC?',
            'answer': f'Click the "Sign Up" button on the homepage. Fill in your username, email, and password. You\'ll receive a confirmation email to activate your account.',
            'category': 'account',
            'keywords': 'account, sign up, register, create account',
        },
        {
            'question': 'How do I buy a CSS file?',
            'answer': f'Browse the Shop, find a CSS file you like, add it to your cart, and proceed to checkout. You can pay using your VRC Neuros balance.',
            'category': 'shopping',
            'keywords': 'buy, purchase, shop, css, cart, checkout',
        },
        {
            'question': 'What are Neuros?',
            'answer': f'Neuros (NE) are the virtual currency on the VRC platform. You can use them to buy CSS files, run ad campaigns, and more. You receive a bonus when you first create your banking account.',
            'category': 'banking',
            'keywords': 'neuros, currency, money, balance, NE',
        },
        {
            'question': 'How do I become a developer?',
            'answer': f'Visit the Developer Portal and sign up for a developer plan. Once registered, you can create CSS projects, publish listings, and earn Neuros from sales.',
            'category': 'developer',
            'keywords': 'developer, sell, create, publish, portal',
        },
        {
            'question': 'How does the forum reputation system work?',
            'answer': f'You earn reputation points by posting, receiving likes, and helping others. Ranks: New User → Newcomer (10+) → Member (100+) → Advanced (500+) → Expert (1000+).',
            'category': 'forum',
            'keywords': 'reputation, points, rank, forum, likes',
        },
        {
            'question': 'How do I set up 2FA?',
            'answer': f'Go to your Account Settings → Security. You can enable TOTP-based two-factor authentication or email-based 2FA. We recommend using an authenticator app for better security.',
            'category': 'security',
            'keywords': '2fa, two-factor, totp, security, authentication',
        },
        {
            'question': 'How do I transfer Neuros to another user?',
            'answer': f'Go to your Bank dashboard, click "Transfer", enter the recipient\'s account number and the amount. You\'ll need to verify with your PIN.',
            'category': 'banking',
            'keywords': 'transfer, send, neuros, bank, payment',
        },
        {
            'question': 'Can I get a refund?',
            'answer': f'Refund policies depend on the individual CSS seller. Contact the seller through the platform or reach out to support for assistance. Digital products are generally non-refundable.',
            'category': 'shopping',
            'keywords': 'refund, return, money back, cancel order',
        },
    ]

    created = 0
    for entry in entries:
        jitter(0.3, 1.0)
        _, new = KnowledgeBase.objects.get_or_create(
            question=entry['question'],
            defaults={
                'answer':   entry['answer'],
                'category': entry['category'],
                'keywords': entry['keywords'],
                'is_active': True,
            },
        )
        if new:
            created += 1

    print(f'[+] Chatbot: {created} knowledge base entries created.')


if __name__ == '__main__':
    seed()
