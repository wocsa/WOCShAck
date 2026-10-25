"""Seed blog posts, tutorials, showcase items, events, friend requests, and messages."""
import os
import django
from datetime import timedelta, datetime
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
django.setup()

from django.utils import timezone
from setup.seed import SEED_TAG, get_demo_users, jitter


def seed():
    from Community.models.content import (
        BlogCategory, BlogPost, BlogComment,
        Tutorial, TutorialStep, TutorialQuiz,
        ShowcaseItem, ShowcaseVote,
        Event, EventRegistration,
    )
    from setup.seed import get_personas
    import random

    personas = get_personas()
    all_users = personas['users']
    developers = personas['developers'] or all_users
    designers = personas['designers'] or all_users
    staff = personas['staff'] or all_users
    business = personas['business'] or all_users
    now = timezone.now()

    def random_but(group, *exclude):
        pool = [u for u in group if u not in exclude]
        return random.choice(pool) if pool else random.choice(group)

    # -- Blog categories --
    blog_cats = {}
    for name, slug, desc in [
        ('CSS Techniques', 'css-techniques', f'Articles about modern CSS patterns and tricks.'),
        ('Platform News',  'platform-news',  f'Announcements and updates about the VRC platform.'),
    ]:
        cat, _ = BlogCategory.objects.get_or_create(name=name, defaults={'slug': slug, 'description': desc})
        blog_cats[slug] = cat

    # -- Blog posts --
    posts_data = [
        {
            'title': 'Mastering CSS Grid: A Complete Visual Guide',
            'slug': 'mastering-css-grid',
            'author': random.choice(developers),
            'category': blog_cats['css-techniques'],
            'content': (
                f'CSS Grid has revolutionised web layout design, offering a two-dimensional '
                f'system that handles both columns and rows.\n\n'
                f'## Why CSS Grid?\n\n'
                f'Unlike Flexbox (which is one-dimensional), Grid lets you control both axes '
                f'simultaneously. This makes complex layouts trivially simple.\n\n'
                f'## Basic Setup\n\n'
                f'```css\n.container {{\n  display: grid;\n'
                f'  grid-template-columns: repeat(3, 1fr);\n'
                f'  gap: 1rem;\n}}\n```\n\n'
                f'## Advanced Patterns\n\n'
                f'- **Auto-fill vs auto-fit**: Use `auto-fill` to maintain empty tracks, `auto-fit` to collapse them.\n'
                f'- **Named areas**: Use `grid-template-areas` for semantic layouts.\n'
                f'- **Subgrid**: Inherit parent grid tracks in child containers.\n\n'
                f'Stay tuned for Part 2 where we build a responsive dashboard layout!'
            ),
            'is_featured': True,
        },
        {
            'title': 'VRC Platform v5 — What\'s New',
            'slug': 'vrc-platform-v5-whats-new',
            'author': random.choice(staff),
            'category': blog_cats['platform-news'],
            'content': (
                f'We\'re thrilled to announce **VRC Platform v5** — the biggest update yet!\n\n'
                f'## Key Highlights\n\n'
                f'- 🏪 **CSS Marketplace** — Buy, sell, and review CSS files\n'
                f'- 💬 **Community Forum** — Discussion boards with reputation system\n'
                f'- 🤖 **AI Chatbot** — RAG-powered support assistant\n'
                f'- 📊 **Developer Portal** — Full analytics and payout dashboard\n'
                f'- 📢 **Ad Platform** — Promote your creations across the platform\n\n'
                f'## Getting Started\n\n'
                f'Create an account, explore the marketplace, and start building. '
                f'Developers can apply for a seller account in the Developer Portal.\n\n'
                f'Happy coding! 🚀'
            ),
            'is_pinned': True,
        },
        {
            'title': 'Creating Accessible CSS Animations',
            'slug': 'accessible-css-animations',
            'author': random.choice(developers),
            'category': blog_cats['css-techniques'],
            'content': (
                f'Beautiful animations shouldn\'t come at the cost of accessibility.\n\n'
                f'## The `prefers-reduced-motion` Media Query\n\n'
                f'```css\n@media (prefers-reduced-motion: reduce) {{\n'
                f'  *, *::before, *::after {{\n'
                f'    animation-duration: 0.01ms !important;\n'
                f'    transition-duration: 0.01ms !important;\n'
                f'  }}\n}}\n```\n\n'
                f'## Best Practices\n\n'
                f'- Provide pause/stop controls for looping animations\n'
                f'- Keep animation durations reasonable (< 5 seconds)\n'
                f'- Avoid rapidly flashing content\n'
                f'- Test with screen readers\n\n'
                f'Accessibility is a feature, not an afterthought.'
            ),
        },
        {
            'title': 'Crafting Your Own CSS Utility Library',
            'slug': 'crafting-css-utility-library',
            'author': next((u for u in all_users if u.username == 'davidwilson'), random.choice(developers)),
            'category': blog_cats['css-techniques'],
            'content': (
                f'Utility-first CSS is incredibly popular, but sometimes you don\'t need a massive framework.\n\n'
                f'## Starting with Custom Properties\n\n'
                f'```css\n:root {{\n'
                f'  --spacing-1: 0.25rem;\n  --spacing-2: 0.5rem;\n'
                f'  --color-primary: #3b82f6;\n}}\n```\n\n'
                f'## The Core Utilities\n\n'
                f'Generate the most common classes for your design system:\n'
                f'```css\n.mt-1 {{ margin-top: var(--spacing-1); }}\n.text-primary {{ color: var(--color-primary); }}\n```\n\n'
                f'Building your own system gives you complete understanding of your styling architecture.'
            ),
        },
        {
            'title': 'The Power of CSS Subgrid',
            'slug': 'power-of-css-subgrid',
            'author': next((u for u in all_users if u.username == 'davidwilson'), random.choice(developers)),
            'category': blog_cats['css-techniques'],
            'content': (
                f'CSS Subgrid is finally supported across all major browsers, and it changes everything.\n\n'
                f'## The Problem\n\n'
                f'Nested grid items couldn\'t previously align with the parent grid\'s tracks. You had to recreate the grid or use fixed sizes.\n\n'
                f'## The Solution\n\n'
                f'```css\n.parent {{\n  display: grid;\n  grid-template-columns: repeat(3, 1fr);\n}}\n\n'
                f'.child {{\n  grid-column: span 3;\n  display: grid;\n  grid-template-columns: subgrid;\n}}\n```\n\n'
                f'Now, children elements inside `.child` will perfectly align with the columns of `.parent`. It is essential for card layouts!'
            ),
        },
    ]

    posts_created = 0
    for pd in posts_data:
        if BlogPost.objects.filter(slug=pd['slug']).exists():
            continue
        jitter(1.0, 3.0)
        post = BlogPost.objects.create(
            title=pd['title'],
            slug=pd['slug'],
            content=pd['content'],
            author=pd['author'],
            category=pd['category'],
            status=BlogPost.Status.PUBLISHED,
            is_featured=pd.get('is_featured', False),
            is_pinned=pd.get('is_pinned', False),
            published_at=now - timedelta(days=len(posts_data)),
        )
        jitter(0.5, 1.5)
        
        # Add random comments
        # 1 user comment, 1 staff comment if author is not staff
        commenter1 = random_but(all_users, pd['author'])
        BlogComment.objects.create(
            post=post, author=commenter1,
            content='Great article! Very well explained.',
            status=BlogComment.Status.APPROVED,
        )
        
        if pd['author'] not in staff:
            jitter(0.5, 1.5)
            # Find a staff member
            staff_member = random_but(staff, pd['author'], commenter1)
            BlogComment.objects.create(
                post=post, author=staff_member,
                content='Nice work — pinning this for the community.',
                status=BlogComment.Status.APPROVED,
            )
        posts_created += 1

    # -- Tutorials --
    tutorials_created = 0

    def get_specific_user(username_str, default_pool):
        return next((u for u in all_users if u.username == username_str), random.choice(default_pool))

    if not Tutorial.objects.filter(slug='beginner-css-loaders').exists():
        tut1 = Tutorial.objects.create(
            title='Build Your First CSS Loader',
            slug='beginner-css-loaders',
            description=f'Learn to build pure CSS loading animations from scratch.',
            author=random.choice(developers),
            difficulty=Tutorial.Difficulty.BEGINNER,
            estimated_minutes=20,
            prerequisites='Basic HTML and CSS knowledge',
            category='CSS Animations',
            is_published=True,
        )
        s2 = TutorialStep.objects.create(
            tutorial=tut1, order=1, title='Setting up the HTML structure',
            content='Create a simple `<div>` element that will become our loader.',
            code_example='<div class="loader"></div>',
        )
        s3 = TutorialStep.objects.create(
            tutorial=tut1, order=2, title='Styling the base shape',
            content='Style the div as a circle with a visible border.',
            code_example='.loader { width: 48px; height: 48px; border-radius: 50%; border: 4px solid #e2e8f0; border-top-color: #3b82f6; }',
        )
        s4 = TutorialStep.objects.create(
            tutorial=tut1, order=3, title='Adding the spin animation',
            content='Use `@keyframes` to rotate the element infinitely.',
            code_example='@keyframes spin { to { transform: rotate(360deg); } }\n.loader { animation: spin 0.8s linear infinite; }',
        )
        TutorialQuiz.objects.create(
            step=s3,
            question='Which CSS property makes an element circular?',
            question_type=TutorialQuiz.QuestionType.MULTIPLE_CHOICE,
            options=['border-radius: 50%', 'display: circle', 'shape: round', 'clip-path: circle()'],
            correct_answer='border-radius: 50%',
            hint='Think about rounding the corners to their maximum.',
        )
        TutorialQuiz.objects.create(
            step=s4,
            question='True or False: CSS animations require JavaScript to run.',
            question_type=TutorialQuiz.QuestionType.TRUE_FALSE,
            options=['True', 'False'],
            correct_answer='False',
            hint='CSS has its own animation system with @keyframes.',
        )
        tutorials_created += 1

    if not Tutorial.objects.filter(slug='intermediate-glassmorphism').exists():
        tut2 = Tutorial.objects.create(
            title='Glassmorphism UI Components',
            slug='intermediate-glassmorphism',
            description=f'Create modern frosted-glass UI components with CSS.',
            author=random.choice(designers),
            difficulty=Tutorial.Difficulty.INTERMEDIATE,
            estimated_minutes=30,
            prerequisites='Comfortable with CSS transforms and transitions',
            category='UI Design',
            is_published=True,
        )
        TutorialStep.objects.create(
            tutorial=tut2, order=1, title='Understanding backdrop-filter',
            content='`backdrop-filter` applies effects to the area behind an element.',
            code_example='.glass { backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); }',
        )
        TutorialStep.objects.create(
            tutorial=tut2, order=2, title='Building the card component',
            content='Combine semi-transparent background with blur for the glass effect.',
            code_example='.glass-card { background: rgba(255,255,255,0.15); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.2); border-radius: 16px; padding: 2rem; }',
        )
        TutorialStep.objects.create(
            tutorial=tut2, order=3, title='Adding browser fallbacks',
            content='Use @supports to provide graceful degradation.',
            code_example='@supports not (backdrop-filter: blur(10px)) { .glass-card { background: rgba(255,255,255,0.85); } }',
        )
        tutorials_created += 1

    if not Tutorial.objects.filter(slug='accessibility-color-contrast').exists():
        tut3 = Tutorial.objects.create(
            title='Mastering Accessibility & Color Contrast',
            slug='accessibility-color-contrast',
            description='Ensure your designs meet WCAG guidelines for color contrast and accessibility.',
            author=get_specific_user('emilydavis', designers),
            difficulty=Tutorial.Difficulty.INTERMEDIATE,
            estimated_minutes=25,
            prerequisites='Basic understanding of hex codes and CSS colors',
            category='UI Design',
            is_published=True,
        )
        TutorialStep.objects.create(
            tutorial=tut3, order=1, title='Understanding WCAG Guidelines',
            content='WCAG 2.1 requires a contrast ratio of at least 4.5:1 for normal text.',
            code_example='/* Good Contrast */\n.text-primary { color: #1a202c; background-color: #ffffff; }',
        )
        pt3_step = TutorialStep.objects.create(
            tutorial=tut3, order=2, title='Testing with DevTools',
            content='Learn to test contrast directly from Chrome or Firefox DevTools.',
            code_example='/* Click the color square in DevTools to see the contrast ratio */',
        )
        TutorialQuiz.objects.create(
            step=pt3_step,
            question='What is the minimum WCAG AA contrast ratio for normal text?',
            question_type=TutorialQuiz.QuestionType.MULTIPLE_CHOICE,
            options=['3.0:1', '4.5:1', '7.0:1', '2.5:1'],
            correct_answer='4.5:1',
            hint='It is between 4 and 5.',
        )
        tutorials_created += 1

    if not Tutorial.objects.filter(slug='securing-web-apps').exists():
        tut4 = Tutorial.objects.create(
            title='Securing Your Web Application',
            slug='securing-web-apps',
            description='Learn essential cybersecurity practices to protect user data and APIs.',
            author=get_specific_user('thomasgreen', developers),
            difficulty=Tutorial.Difficulty.ADVANCED,
            estimated_minutes=45,
            prerequisites='Experience with backend deployment and HTTP headers',
            category='Backend',
            is_published=True,
        )
        TutorialStep.objects.create(
            tutorial=tut4, order=1, title='Preventing XSS',
            content='Always sanitize user inputs and safely escape content effectively to prevent Cross-Site Scripting.',
            code_example='<!-- Example: Vue/React auto-escapes, but use caution with innerHTML -->',
        )
        TutorialStep.objects.create(
            tutorial=tut4, order=2, title='Setting Security Headers',
            content='Use Content-Security-Policy and HSTS headers. If caching, configure Cache-Control properly.',
            code_example='Strict-Transport-Security: max-age=31536000; includeSubDomains',
        )
        tutorials_created += 1

    if not Tutorial.objects.filter(slug='django-rest-framework-basics').exists():
        tut5 = Tutorial.objects.create(
            title='Django REST Framework Basics',
            slug='django-rest-framework-basics',
            description='Build your first set of RESTful endpoints in Python & Django.',
            author=get_specific_user('michaeljohnson', developers),
            difficulty=Tutorial.Difficulty.INTERMEDIATE,
            estimated_minutes=40,
            prerequisites='Python & Django familiarity',
            category='Backend',
            is_published=True,
        )
        TutorialStep.objects.create(
            tutorial=tut5, order=1, title='Creating a ModelSerializer',
            content='ModelSerializers provide a shortcut for creating serializers that deal with model instances.',
            code_example='class UserSerializer(serializers.ModelSerializer):\n    class Meta:\n        model = User\n        fields = ["id", "username", "email"]',
        )
        TutorialStep.objects.create(
            tutorial=tut5, order=2, title='Building ViewSets',
            content='ViewSets allow coupling logic for list/create/retrieve/update into one class.',
            code_example='class UserViewSet(viewsets.ModelViewSet):\n    queryset = User.objects.all()\n    serializer_class = UserSerializer',
        )
        tutorials_created += 1

    if not Tutorial.objects.filter(slug='mobile-first-css-approaches').exists():
        tut6 = Tutorial.objects.create(
            title='Mobile-First CSS Approaches',
            slug='mobile-first-css-approaches',
            description='Adopt a mobile-first strategy to CSS for more robust and maintainable responsive apps.',
            author=get_specific_user('danielclark', developers),
            difficulty=Tutorial.Difficulty.BEGINNER,
            estimated_minutes=25,
            prerequisites='Basic CSS Media Queries',
            category='UI Design',
            is_published=True,
        )
        TutorialStep.objects.create(
            tutorial=tut6, order=1, title='Write Mobile CSS First',
            content='Define your base styles for smaller screens outside of any media queries.',
            code_example='.container { width: 100%; padding: 1rem; }',
        )
        TutorialStep.objects.create(
            tutorial=tut6, order=2, title='Scale Up for Desktop',
            content='Use `min-width` queries to progressively enhance the UI as screen size increases.',
            code_example='@media (min-width: 768px) {\n  .container { max-width: 720px; margin: 0 auto; }\n}',
        )
        tutorials_created += 1

    if not Tutorial.objects.filter(slug='advanced-css-grid-layouts').exists():
        tut7 = Tutorial.objects.create(
            title='Advanced CSS Grid Layouts',
            slug='advanced-css-grid-layouts',
            description='Master CSS Grid to create complex, magazine-style web layouts without hacks.',
            author=get_specific_user('davidwilson', developers),
            difficulty=Tutorial.Difficulty.ADVANCED,
            estimated_minutes=35,
            prerequisites='Intermediate knowledge of CSS Grid',
            category='UI Design',
            is_published=True,
        )
        TutorialStep.objects.create(
            tutorial=tut7, order=1, title='Using minmax() for Responsive Tracks',
            content='The `minmax()` function allows a grid track to be responsive while defining clear boundaries.',
            code_example='.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }',
        )
        TutorialStep.objects.create(
            tutorial=tut7, order=2, title='Grid Areas for Explicit Placement',
            content='Define visual layouts declaratively using `grid-template-areas`.',
            code_example='.grid { grid-template-areas: "header header" "sidebar main"; }',
        )
        tutorials_created += 1

    if not Tutorial.objects.filter(slug='css-variables-theming').exists():
        tut8 = Tutorial.objects.create(
            title='Creating CSS Custom Variable Themes',
            slug='css-variables-theming',
            description='Build a robust theming system using native CSS variables.',
            author=get_specific_user('emilydavis', designers),
            difficulty=Tutorial.Difficulty.INTERMEDIATE,
            estimated_minutes=30,
            prerequisites='Understanding of CSS root selector',
            category='UI Design',
            is_published=True,
        )
        TutorialStep.objects.create(
            tutorial=tut8, order=1, title='Defining Base Variables',
            content='Set your default theme properties on the :root pseudo-class.',
            code_example=':root {\n  --bg-color: #ffffff;\n  --text-color: #1a1a1a;\n  --primary: #3b82f6;\n}',
        )
        TutorialStep.objects.create(
            tutorial=tut8, order=2, title='Creating the Dark Theme',
            content='Override variables using a data attribute or class.',
            code_example='[data-theme="dark"] {\n  --bg-color: #1a1a1a;\n  --text-color: #ffffff;\n  --primary: #60a5fa;\n}',
        )
        tutorials_created += 1

    # -- Showcase items --
    showcase_data = [
        ('Neon Ring Spinner',     'loaders',    '.ring{width:64px;height:64px;border:4px solid transparent;border-top:4px solid #0ff;border-radius:50%;animation:neon 1s ease-in-out infinite}@keyframes neon{to{transform:rotate(360deg)}}', designers,   '<div class="ring"></div>'),
        ('Gradient Button Hover', 'buttons',    '.grad-btn{padding:.75rem 2rem;background:linear-gradient(135deg,#667eea,#764ba2);border:none;color:#fff;border-radius:8px;cursor:pointer;transition:transform .2s}.grad-btn:hover{transform:scale(1.05)}', developers, '<button class="grad-btn">Hover me</button>'),
        ('Floating Card Layout',  'cards',      '.float-card{background:#fff;border-radius:12px;padding:1.5rem;box-shadow:0 4px 20px rgba(0,0,0,.08);transition:transform .3s,box-shadow .3s}.float-card:hover{transform:translateY(-4px);box-shadow:0 12px 40px rgba(0,0,0,.15)}', developers, '<div class="float-card">Card content</div>'),
        ('Pure CSS Sunset',       'art',        '.sunset{width:200px;height:200px;background:linear-gradient(180deg,#ff6b6b 0%,#ffa07a 30%,#ffd700 60%,#87ceeb 100%);border-radius:50%;position:relative}', designers,   '<div class="sunset"></div>'),
        ('Text Shimmer Effect',   'animations', '.shimmer{background:linear-gradient(90deg,#333 0%,#fff 50%,#333 100%);background-size:200% 100%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:shimmer 2s infinite}@keyframes shimmer{to{background-position:-200% 0}}', developers, '<span class="shimmer">WOCSA</span>'),
        ('Dark Mode Toggle',      'dark_mode',  '.dm-toggle{width:56px;height:28px;border-radius:14px;background:#1e293b;position:relative;cursor:pointer;transition:background .3s}.dm-toggle.light{background:#e2e8f0}', developers, '<div class="dm-toggle"></div>'),
        ('CSS Cube Animation',    'animations', '.cube{width:50px;height:50px;transform-style:preserve-3d;animation:rotate 3s linear infinite}@keyframes rotate{100%{transform:rotateX(360deg) rotateY(360deg)}}', developers,   '<div class="cube"></div>'),
        ('Glowing Input Field',   'forms',      '.glow-input{padding:10px;border:2px solid transparent;border-radius:5px;background:#222;color:#fff;transition:box-shadow .3s}.glow-input:focus{outline:none;box-shadow:0 0 10px #0ff,inset 0 0 5px #0ff}', designers,   '<input class="glow-input" placeholder="Type here...">'),
        ('Neumorphism Card',      'cards',      '.neomorph{background:#e0e5ec;border-radius:15px;padding:2rem;box-shadow:9px 9px 16px rgb(163,177,198,0.6),-9px -9px 16px rgba(255,255,255, 0.5);}', designers,   '<div class="neomorph">Neumorphic</div>'),
        ('Cyberpunk Glitch',      'animations', '.glitch{position:relative;color:#fff;font-size:2rem;font-weight:bold;}.glitch::before,.glitch::after{content:attr(data-text);position:absolute;top:0;left:0;opacity:0.8;}.glitch::before{left:2px;text-shadow:-1px 0 red;animation:glitch-anim 2s infinite linear alternate-reverse;}.glitch::after{left:-2px;text-shadow:-1px 0 blue;animation:glitch-anim2 3s infinite linear alternate-reverse;}', developers, '<div class="glitch" data-text="HACK">HACK</div>'),
    ]

    showcase_created = 0
    for title, cat_key, css, allowed_authors, item_html in showcase_data:
        if ShowcaseItem.objects.filter(title=title).exists():
            continue
        jitter(0.5, 2.0)
        item_author = random.choice(allowed_authors)
        item = ShowcaseItem.objects.create(
            title=title,
            description=f'A community-submitted {cat_key} demo.',
            author=item_author,
            demo_css=css,
            demo_html=item_html,
            category=cat_key,
            is_approved=True,
            is_featured=title in ('Neon Ring Spinner', 'Floating Card Layout'),
        )
        # Generate GIF preview (requires Selenium + headless Chrome)
        try:
            from Api.gif_utils import generate_gif_for_css
            result = generate_gif_for_css(item.demo_css, str(item.id), body_html=item.demo_html)
            if result:
                gif_file, gif_name = result
                item.preview_gif.save(gif_name, gif_file, save=True)
        except Exception:
            pass
        # Give random votes
        random_voters = random.sample(all_users, min(len(all_users), random.randint(3, 8)))
        for voter in random_voters:
            ShowcaseVote.objects.get_or_create(
                user=voter,
                item=item,
                defaults={'vote_type': ShowcaseVote.VoteType.UPVOTE},
            )
        showcase_created += 1

    # -- Events (fixed May 2026 dates so they remain upcoming until at least 2026-05-30) --
    events_created = 0

    event_specs = [
        {
            'title': 'CSS Animation Workshop',
            'description': 'Hands-on workshop covering keyframe animations, transitions, and performance optimisation. We build a spinner, a progress bar, and a skeleton screen live. Beginners welcome.',
            'event_type': Event.EventType.WORKSHOP,
            'format': Event.Format.ONLINE,
            'start_datetime': timezone.make_aware(datetime(2026, 5, 10, 14, 0)),
            'end_datetime':   timezone.make_aware(datetime(2026, 5, 10, 16, 0)),
            'capacity': 50,
            'meeting_link': 'https://meet.vrc-platform.local/css-workshop',
            'organizer_pool': staff,
        },
        {
            'title': 'Modern CSS Meetup: Grid, Layers & Container Queries',
            'description': 'Monthly community meetup exploring the latest CSS features — subgrid, @layer, container queries, and new colour spaces. Share what you are building and get feedback.',
            'event_type': Event.EventType.MEETUP,
            'format': Event.Format.ONLINE,
            'start_datetime': timezone.make_aware(datetime(2026, 5, 17, 11, 0)),
            'end_datetime':   timezone.make_aware(datetime(2026, 5, 17, 13, 0)),
            'capacity': 80,
            'meeting_link': 'https://meet.vrc-platform.local/css-meetup',
            'organizer_pool': staff or developers,
        },
        {
            'title': 'Accessible UI Design Webinar',
            'description': 'WCAG 2.2 compliance walkthrough focused on colour contrast, focus management, motion sensitivity, and keyboard navigation. Includes live audit of community-submitted CSS.',
            'event_type': Event.EventType.WEBINAR,
            'format': Event.Format.ONLINE,
            'start_datetime': timezone.make_aware(datetime(2026, 5, 24, 15, 0)),
            'end_datetime':   timezone.make_aware(datetime(2026, 5, 24, 16, 30)),
            'capacity': 120,
            'meeting_link': 'https://meet.vrc-platform.local/a11y-webinar',
            'organizer_pool': designers or developers,
        },
    ]

    for spec in event_specs:
        if Event.objects.filter(title=spec['title']).exists():
            continue
        jitter(0.5, 1.5)
        evt = Event.objects.create(
            title=spec['title'],
            description=spec['description'],
            organizer=random.choice(spec['organizer_pool']),
            event_type=spec['event_type'],
            format=spec['format'],
            start_datetime=spec['start_datetime'],
            end_datetime=spec['end_datetime'],
            capacity=spec['capacity'],
            meeting_link=spec.get('meeting_link', ''),
            status=Event.Status.PUBLISHED,
        )
        random_attendees = random.sample(all_users, min(len(all_users), random.randint(5, 12)))
        for attendee in random_attendees:
            EventRegistration.objects.get_or_create(event=evt, user=attendee)
        events_created += 1

    # -- Friend requests & friendships --
    from Community.models.social import FriendRequest, Friendship

    # Build pairs: (sender_idx, receiver_idx, status)
    friend_specs = [
        (0, 1, 'accepted'),
        (0, 2, 'accepted'),
        (1, 3, 'accepted'),
        (2, 4, 'accepted'),
        (3, 5, 'accepted'),
        (0, 3, 'pending'),
        (1, 4, 'pending'),
        (5, 2, 'pending'),
        (4, 0, 'rejected'),
        (3, 1, 'rejected'),
    ]

    fr_created = 0
    friendship_created = 0
    accepted_pairs = []

    for si, ri, status in friend_specs:
        if si >= len(all_users) or ri >= len(all_users):
            continue
        sender, receiver = all_users[si], all_users[ri]
        if sender == receiver:
            continue
        fr, created = FriendRequest.objects.get_or_create(
            sender=sender,
            receiver=receiver,
            defaults={
                'status': status,
                'created_at': now - timedelta(days=random.randint(1, 30)),
            },
        )
        if created:
            fr_created += 1
        if status == 'accepted':
            u1, u2 = (sender, receiver) if sender.id < receiver.id else (receiver, sender)
            _, fc = Friendship.objects.get_or_create(user1=u1, user2=u2)
            if fc:
                friendship_created += 1
            accepted_pairs.append((sender, receiver))

    # -- Conversations & messages --
    from Community.models.communication import Conversation, Message

    dm_scripts = [
        [
            ("Hey! I really liked your CSS Grid article.", 0),
            ("Thanks! Let me know if you have questions.", 1),
            ("Will do. Also working on a dark-mode tutorial.", 0),
            ("Cool — share it when it's ready!", 1),
        ],
        [
            ("Did you check the new showcase items?", 0),
            ("Yeah, that neon spinner is wild!", 1),
            ("I know right, submitted one too.", 0),
        ],
        [
            ("Hey, want to co-host the CSS workshop?", 0),
            ("Absolutely! I can cover animations.", 1),
            ("Perfect, I'll handle glassmorphism then.", 0),
            ("Deal. Let's sync Thursday.", 1),
        ],
        [
            ("Quick question about your loader tutorial.", 0),
            ("Sure, what's up?", 1),
            ("Does it work without a build step?", 0),
            ("Yes — pure CSS, no JS needed.", 1),
            ("That's exactly what I needed, cheers!", 0),
        ],
        # Persona enhanced scripts based on their bios
        [
            ("I've been thinking about integrating more automated tests. Any tips?", 0),
            ("Definitely! Start with API endpoints using Django's test client.", 1),
            ("That makes sense. I'll get my QA strategy aligned.", 0),
            ("Let me know if you run into any flakiness.", 1),
        ],
        [
            ("Have you seen the recent changes to the cloud infrastructure?", 0),
            ("Yes, the downtime was minimal though! DevOps handled it well.", 1),
        ],
        [
            ("I wanted your opinion on security practices for mobile apps.", 0),
            ("Sure. Always use certificate pinning and store tokens securely.", 1),
            ("I'm using Keychain on iOS right now.", 0),
            ("Perfect. That's the right approach.", 1),
        ],
        [
            ("Are we prioritizing accessibility in the next sprint?", 0),
            ("Yes, the PM team wants it handled by Q3.", 1),
            ("Great, I'll prepare some designs with improved contrast.", 0),
            ("Awesome. Let's make sure it's WCAG compliant.", 1),
        ],
    ]

    conv_created = 0
    msg_created = 0

    for idx, (u_a, u_b) in enumerate(accepted_pairs[:len(dm_scripts)]):
        u1, u2 = (u_a, u_b) if u_a.id < u_b.id else (u_b, u_a)
        conv, c_new = Conversation.objects.get_or_create(user1=u1, user2=u2)
        if c_new:
            conv_created += 1
        if conv.messages.exists():
            continue
        script = dm_scripts[idx % len(dm_scripts)]
        participants = [u_a, u_b]
        for line_offset, (text, speaker_idx) in enumerate(script):
            Message.objects.create(
                conversation=conv,
                sender=participants[speaker_idx % 2],
                content=text,
                message_type=Message.MessageType.TEXT,
            )
            msg_created += 1

    print(
        f'[+] Community: {posts_created} posts, {tutorials_created} tutorials, '
        f'{showcase_created} showcase items, {events_created} events, '
        f'{fr_created} friend requests, {friendship_created} friendships, '
        f'{conv_created} conversations, {msg_created} messages.'
    )


if __name__ == '__main__':
    seed()
