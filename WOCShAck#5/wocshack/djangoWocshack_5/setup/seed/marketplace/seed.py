"""Seed CSS marketplace categories and demo products."""
import os
import django
from decimal import Decimal
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
django.setup()

from setup.seed import SEED_TAG, get_demo_users, jitter

# Product definitions shared with shopping/seed.py (used there to look up objects by name).
CSS_PRODUCTS = [
    {
        'name': 'Neon Pulse Loader',
        'author': 'CSSWizard',
        'price': Decimal('4.99'),
        'category_slug': 'loaders',
        'css': (
            '.neon-pulse{width:48px;height:48px;border-radius:50%;'
            'border:4px solid #0ff;border-top-color:transparent;'
            'animation:neon-spin .8s linear infinite}'
            '@keyframes neon-spin{to{transform:rotate(360deg)}}'
        ),
        'html_template': '<div class="neon-pulse"></div>',
    },
    {
        'name': 'Glassmorphism Card',
        'author': 'PixelArtisan',
        'price': Decimal('7.50'),
        'category_slug': 'components',
        'css': (
            '.glass-card{background:rgba(255,255,255,.15);'
            'backdrop-filter:blur(12px);border-radius:16px;'
            'border:1px solid rgba(255,255,255,.2);padding:2rem;'
            'box-shadow:0 8px 32px rgba(0,0,0,.1)}'
        ),
        'html_template': '<div class="glass-card">Glassmorphism Content</div>',
    },
    {
        'name': 'Ripple Button',
        'author': 'UIForge',
        'price': Decimal('3.00'),
        'category_slug': 'buttons',
        'css': (
            '.ripple-btn{position:relative;overflow:hidden;padding:.75rem 1.5rem;'
            'border:none;border-radius:8px;background:#6366f1;color:#fff;'
            'cursor:pointer;transition:background .3s}'
            '.ripple-btn:hover{background:#4f46e5}'
        ),
        'html_template': '<button class="ripple-btn">Click Me</button>',
    },
    {
        'name': 'Aurora Background',
        'author': 'CSSWizard',
        'price': Decimal('9.99'),
        'category_slug': 'backgrounds',
        'css': (
            '.aurora{background:linear-gradient(135deg,#667eea 0%,#764ba2 50%,#f093fb 100%);'
            'background-size:400% 400%;animation:aurora-shift 8s ease infinite}'
            '@keyframes aurora-shift{0%,100%{background-position:0% 50%}'
            '50%{background-position:100% 50%}}'
        ),
        'html_template': '<div class="aurora" style="width: 200px; height: 100px; border-radius: 8px;"></div>',
    },
    {
        'name': 'Skeleton Screen',
        'author': 'PixelArtisan',
        'price': Decimal('5.25'),
        'category_slug': 'loaders',
        'css': (
            '.skeleton{background:linear-gradient(90deg,#e2e8f0 25%,#f1f5f9 50%,#e2e8f0 75%);'
            'background-size:200% 100%;animation:skeleton-wave 1.5s infinite}'
            '@keyframes skeleton-wave{to{background-position:-200% 0}}'
        ),
        'html_template': '<div class="skeleton" style="width: 200px; height: 20px; border-radius: 4px; margin-bottom: 8px;"></div><div class="skeleton" style="width: 150px; height: 20px; border-radius: 4px;"></div>',
    },
    {
        'name': 'Neumorphic Toggle',
        'author': 'UIForge',
        'price': Decimal('2.50'),
        'category_slug': 'components',
        'css': (
            '.neu-toggle{width:60px;height:30px;border-radius:15px;'
            'background:#e0e5ec;box-shadow:inset 3px 3px 6px #b8bec7,'
            'inset -3px -3px 6px #fff;position:relative;cursor:pointer}'
        ),
        'html_template': '<div class="neu-toggle"></div>',
    },
    {
        'name': 'Typewriter Effect',
        'author': 'CSSWizard',
        'price': Decimal('6.00'),
        'category_slug': 'animations',
        'css': (
            '.typewriter{font-family:monospace;overflow:hidden;'
            'white-space:nowrap;border-right:3px solid #333;'
            'animation:typing 3s steps(30) 1s forwards,'
            'blink .75s step-end infinite}'
            '@keyframes typing{from{width:0}to{width:100%}}'
            '@keyframes blink{50%{border-color:transparent}}'
        ),
        'html_template': '<div class="typewriter" style="width: 250px;">Hello World!</div>',
    },
]


def seed():
    from Api.models import CssCategory, Css
    from Api.gif_utils import generate_gif_for_css
    from setup.seed import get_personas
    import random

    personas = get_personas()
    developers = personas['developers'] or personas['users']
    designers = personas['designers'] or personas['users']

    cat_map = {}
    for name, slug, desc in [
        ('Loaders & Spinners',     'loaders',     f'CSS loading animations and spinners.'),
        ('Buttons & Interactions', 'buttons',     f'Interactive button styles and effects.'),
        ('Components',             'components',  f'Reusable UI components built with pure CSS.'),
        ('Backgrounds',            'backgrounds', f'Animated and static background effects.'),
        ('Animations',             'animations',  f'General purpose CSS animations.'),
    ]:
        cat, _ = CssCategory.objects.get_or_create(name=name, defaults={'slug': slug, 'description': desc})
        cat_map[slug] = cat

    created = 0
    for p in CSS_PRODUCTS:
        jitter(0.5, 2.0)
        # Assign developers to tech-heavy themes, designers to others
        creator = random.choice(developers) if p['author'] in ('CSSWizard', 'UIForge') else random.choice(designers)
        author_name = creator.get_full_name() or creator.username.title()
        css_obj, new = Css.objects.get_or_create(
            name=p['name'],
            defaults={
                'css_content':   p['css'],
                'html_template': p['html_template'],
                'author':        author_name,
                'creator':       creator,
                'price':         p['price'],
                'category':      cat_map.get(p['category_slug']),
                'is_active':     True,
            },
        )
        if new:
            created += 1
            # Generate preview gif using the specified template
            try:
                result = generate_gif_for_css(css_obj.css_content, str(css_obj.id), body_html=css_obj.html_template)
                if result:
                    content_file, filename = result
                    css_obj.preview_gif.save(filename, content_file, save=True)
                else:
                    print(f"[!] Warning: gif generation returned no result for {css_obj.name}")
            except Exception as e:
                print(f"[!] Warning: failed to generate gif for {css_obj.name}: {e}")

    print(f'[+] Marketplace: {len(cat_map)} categories, {created} products created ({len(CSS_PRODUCTS) - created} already existed).')


if __name__ == '__main__':
    seed()

