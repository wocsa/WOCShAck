"""Seed forum topics, posts, likes, and reputation for demo users."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
django.setup()

from setup.seed import SEED_TAG, get_demo_users, jitter


def seed():
    from Forum.models import Category, Topic, Post, PostLike, UserReputation
    from setup.seed import get_personas
    import random

    personas = get_personas()
    all_users = personas['users']
    developers = personas['developers'] or all_users
    designers = personas['designers'] or all_users
    staff = personas['staff'] or all_users
    business = personas['business'] or all_users

    # "General Discussion", "Feature Requests", and "Off-Topic" are already created
    # by setup_database.py → setup_forum_categories(). Look them up here instead of
    # re-creating them so there is a single source of truth for base forum structure.
    categories = {
        'general':          Category.objects.get(slug='general'),
        'feature-requests': Category.objects.get(slug='feature-requests'),
        'off-topic':        Category.objects.get(slug='off-topic'),
    }

    # This category is demo-specific (not part of the base platform setup).
    cat, _ = Category.objects.get_or_create(
        name='CSS Help & Techniques',
        defaults={
            'slug':        'css-help',
            'description': f'Ask questions and share CSS tricks.',
            'icon':        'code-bracket',
            'order':       7,
        },
    )
    categories['css-help'] = cat

    # We will pick explicit random users avoiding identical users when doing replies.
    
    def random_but(group, *exclude):
        pool = [u for u in group if u not in exclude]
        return random.choice(pool) if pool else random.choice(group)

    topic_data = [
        {
            'category': 'general',
            'author': random.choice(all_users),
            'title': 'Welcome to the VRC Community Forum!',
            'first_post': (
                'Hey everyone! Just joined the V.R.C platform and I\'m really impressed '
                'with the CSS marketplace. Looking forward to connecting with other developers '
                'and sharing some cool loader animations I\'ve been working on.\n\n'
                'What brought you here?'
            ),
            'replies': [
                (random.choice(developers), 'Welcome aboard! I\'ve been selling CSS files here for a few months now. '
                        'The developer portal is great for tracking sales and analytics. '
                        'Let me know if you need any tips on getting started!'),
                (random.choice(staff), 'Great to see new members! Feel free to explore the forum and don\'t '
                        'hesitate to ask questions. Check out the CSS Help category for tutorials.'),
            ],
        },
        {
            'category': 'css-help',
            'author': random.choice(developers),
            'title': 'How to create smooth CSS-only loading animations',
            'first_post': (
                'I wanted to share my approach to building performant CSS loaders.\n\n'
                '**Key principles:**\n'
                '1. Use `transform` and `opacity` for GPU-accelerated animations\n'
                '2. Prefer `@keyframes` over transition chains\n'
                '3. Keep the DOM structure minimal\n\n'
                'Here\'s a basic example:\n```css\n'
                '.loader { width: 40px; height: 40px; border: 3px solid #f3f3f3;\n'
                '  border-top: 3px solid #3498db; border-radius: 50%;\n'
                '  animation: spin 1s linear infinite; }\n'
                '@keyframes spin { to { transform: rotate(360deg); } }\n```\n\n'
                'What techniques do you prefer?'
            ),
            'replies': [
                (random.choice(designers), 'This is really helpful! I\'ve been struggling with jittery animations. '
                        'Switching to transform-based animations made a huge difference. Thanks!'),
                (random.choice(staff), 'Pinning this — great reference material for newcomers.'),
                (random.choice(developers), 'Quick follow-up: does `will-change: transform` actually help in modern browsers?'),
                (random.choice(developers), 'In most cases the browser already optimizes `transform` animations. '
                        'I\'d avoid `will-change` unless you notice specific performance issues — '
                        'it can actually increase memory usage unnecessarily.'),
            ],
        },
        {
            'category': 'css-help',
            'author': random.choice(designers),
            'title': 'Glassmorphism design — best practices and pitfalls',
            'first_post': (
                'I\'ve been experimenting with glassmorphism effects and ran into some issues '
                'with browser compatibility.\n\n'
                '`backdrop-filter: blur()` doesn\'t work in all browsers. Has anyone found a '
                'good fallback strategy?\n\n'
                'My current approach:\n```css\n'
                '.glass { background: rgba(255, 255, 255, 0.2);\n'
                '  backdrop-filter: blur(10px);\n'
                '  -webkit-backdrop-filter: blur(10px); }\n'
                '@supports not (backdrop-filter: blur(10px)) {\n'
                '  .glass { background: rgba(255, 255, 255, 0.8); } }\n```'
            ),
            'replies': [
                (random.choice(developers), 'Your fallback approach is solid. I also like adding a subtle gradient '
                      'as the non-blur fallback — it gives a similar frosted feel without '
                      'the performance cost.'),
            ],
        },
        {
            'category': 'feature-requests',
            'author': random.choice(developers),
            'title': 'Request: Dark mode for the developer portal',
            'first_post': (
                'The developer portal is great, but coding at night with a bright interface '
                'is tough on the eyes.\n\n'
                'Would love to see:\n'
                '- A system-preference-aware dark mode toggle\n'
                '- Dark syntax highlighting in the CSS editor\n'
                '- Persisted preference across sessions\n\n'
                'Anyone else want this?'
            ),
            'replies': [
                (random.choice(all_users),  '+1, dark mode would be amazing. My eyes would thank you.'),
                (random.choice(staff), 'This is on our roadmap! We\'re currently working on a theming system '
                        'that will support dark mode across the entire platform.'),
            ],
        },
        {
            'category': 'off-topic',
            'author': random.choice(business),
            'title': 'What\'s your favourite code editor setup?',
            'first_post': (
                'Just curious what everyone uses for their CSS workflow.\n\n'
                'I\'m currently using VS Code with these extensions:\n'
                '- CSS Peek\n'
                '- Auto Rename Tag\n'
                '- Live Server\n\n'
                'What about you?'
            ),
            'replies': [
                (random.choice(developers), 'VS Code + Tailwind CSS IntelliSense + GitHub Copilot. '
                        'The AI suggestions save me a ton of time on repetitive styles.'),
                (random.choice(staff), 'I\'m a Neovim person — LazyVim config with treesitter for CSS. '
                        'Once you go modal, you never go back! 😄'),
            ],
        },
        # Persona-based topics
        {
            'category': 'css-help',
            'author': next((u for u in all_users if u.username == 'davidwilson'), random.choice(developers)),
            'title': 'BEM vs Utility-first CSS in 2026',
            'first_post': (
                'I have been leading custom frontend builds and I keep going back and forth between BEM and utility-first frameworks like Tailwind.\n\n'
                'While utility-first is great for speed, BEM feels more maintainable for very complex, bespoke UI components. Here is a quick side-by-side:\n\n'
                '```css\n'
                '/* BEM — explicit component scope */\n'
                '.loader { display: inline-block; width: 48px; height: 48px; }\n'
                '.loader--neon { border: 4px solid #0ff; border-top-color: transparent;\n'
                '  border-radius: 50%; animation: spin .8s linear infinite; }\n'
                '.loader--neon.loader--lg { width: 64px; height: 64px; }\n\n'
                '/* Utility-first equivalent */\n'
                '.w-12 { width: 3rem; } .h-12 { height: 3rem; }\n'
                '.rounded-full { border-radius: 9999px; }\n'
                '.border-4 { border-width: 4px; }\n'
                '.animate-spin { animation: spin 1s linear infinite; }\n'
                '```\n\n'
                'Are you still authoring your own CSS using BEM architecture, or have you fully moved to utility-first?'
            ),
            'replies': [
                (next((u for u in all_users if u.username == 'emilydavis'), random.choice(designers)),
                 'Yes! For design systems BEM is incredibly powerful. It forces you to think about component boundaries. '
                 'I also combine it with CSS custom properties for theming:\n\n'
                 '```css\n'
                 '.loader { --loader-size: 48px; --loader-color: #3b82f6;\n'
                 '  width: var(--loader-size); height: var(--loader-size); }\n'
                 '.loader--accent { --loader-color: #f59e0b; }\n'
                 '```'),
                (next((u for u in all_users if u.username == 'lisaadams'), random.choice(staff)),
                 'BEM heavily simplifies our documentation of UI components because the scope is perfectly isolated. '
                 'Naming conventions like `.block__element--modifier` are self-documenting.'),
            ],
        },
        {
            'category': 'css-help',
            'author': next((u for u in all_users if u.username == 'emilydavis'), random.choice(designers)),
            'title': 'Best practices for overriding third-party CSS and UI libraries?',
            'first_post': (
                'When you inevitably have to use a 3rd-party library (like a complex datepicker or charting library), '
                'what is your strategy for overriding its styles without writing horrible messy CSS filled with `!important` tags?\n\n'
                'Do you prefer CSS modules, scoping with BEM, or native CSS layers?\n\n'
                'Here is what I have been trying lately with `@layer`:\n\n'
                '```css\n'
                '/* Declare layer order — higher layers win */\n'
                '@layer base, vendor, overrides;\n\n'
                '@layer vendor {\n'
                '  /* Paste / import third-party styles here */\n'
                '  .flatpickr-input { border: 1px solid #ccc; border-radius: 4px; }\n'
                '}\n\n'
                '@layer overrides {\n'
                '  /* Your styles always beat vendor without !important */\n'
                '  .flatpickr-input { border-radius: 8px; border-color: var(--color-primary); }\n'
                '}\n'
                '```'
            ),
            'replies': [
                (next((u for u in all_users if u.username == 'davidwilson'), random.choice(developers)),
                 'I strictly use CSS `@layer` now for this exact reason. You can place all the 3rd-party stuff in a layer '
                 'with a lower specificity than your custom styles, avoiding `!important` altogether. Full example:\n\n'
                 '```css\n'
                 '@layer base, vendor, theme;\n\n'
                 '@layer vendor { /* chart.js or similar */ }\n'
                 '@layer theme {\n'
                 '  .chartjs-render-monitor { border-radius: 12px !important; }\n'
                 '  /* !important is still needed inside the same layer, but never to beat vendor */\n'
                 '}\n'
                 '```'),
                (random.choice(developers),
                 'If CSS layers aren\'t an option, I usually scope overrides within a strong BEM parent selector and use CSS variables where possible:\n\n'
                 '```css\n'
                 '.my-date-picker .flatpickr-day.selected {\n'
                 '  background: var(--color-primary, #3b82f6);\n'
                 '  border-color: var(--color-primary, #3b82f6);\n'
                 '}\n'
                 '```'),
            ],
        },
        {
            'category': 'general',
            'author': next((u for u in all_users if u.username == 'robertlee'), random.choice(developers)),
            'title': 'Experiences with Cloud Infrastructure CI/CD pipelines',
            'first_post': (
                'Hey everyone!\n\nI just finished deploying our new Kubernetes cluster and setting up the CI/CD pipeline using GitHub Actions. I am looking for ways to optimize deployment speed.\n\nWhat are your go-to strategies for caching Docker layers in cloud environments?'
            ),
            'replies': [
                (next((u for u in all_users if u.username == 'michaeljohnson'), random.choice(developers)), 'We use Buildah for rootless builds, and heavily rely on remote caching with S3. It shaved off about 40% of our build times.'),
                (next((u for u in all_users if u.username == 'jenniferwhite'), random.choice(all_users)), 'Just make sure your caching doesn\'t cause test flakiness! We had a bug where stale cached assets passed QA accidentally.'),
            ],
        },
        {
            'category': 'general',
            'author': next((u for u in all_users if u.username == 'jenniferwhite'), random.choice(staff)),
            'title': 'Automated End-to-End Testing Strategies',
            'first_post': (
                'As we scale the platform, I want to ensure software quality remains top-notch.\n\nI\'m evaluating Cypress vs Playwright for our E2E testing framework. Cypress has been our go-to, but Playwright\'s multi-tab support is tempting.\n\nThoughts from the frontend and backend teams?'
            ),
            'replies': [
                (next((u for u in all_users if u.username == 'davidwilson'), random.choice(developers)), 'Playwright is amazing. The API is robust and it works flawlessly with our modern stack.'),
            ],
        },
        {
            'category': 'off-topic',
            'author': next((u for u in all_users if u.username == 'thomasgreen'), random.choice(developers)),
            'title': 'Best resources to learn about preventing XSS and CSRF?',
            'first_post': (
                'I am organizing an internal workshop on cybersecurity, specifically protecting digital assets from cross-site scripting and request forgery.\n\nDoes anyone have recommended reading or interactive labs for the team?'
            ),
            'replies': [
                (next((u for u in all_users if u.username == 'lisaadams'), random.choice(staff)), 'I document these APIs regularly, and I highly recommend the official OWASP Cheat Sheets. They are straight to the point.'),
                (random.choice(business), 'Security is paramount for our business strategy. Glad to see this initiative!'),
            ],
        },
        {
            'category': 'general',
            'author': next((u for u in all_users if u.username == 'sarahmiller'), random.choice(staff)),
            'title': 'Agile Methodologies: Best Practices for sprint retrospectives',
            'first_post': (
                'Our product team has been finding recent retrospectives a bit repetitive.\n\nHow do you keep them engaging while still extracting actionable feedback from the developers and designers?'
            ),
            'replies': [
                (next((u for u in all_users if u.username == 'bobsmith'), random.choice(business)), 'We try to focus heavily on the "What could go better" but we gamify the root cause analysis using the 5 Whys.'),
                (next((u for u in all_users if u.username == 'janedoe'), random.choice(designers)), 'As a designer, I appreciate when we visualize the sprint metrics before starting the meeting so everyone has context.'),
            ],
        },
    ]

    topics_created = 0
    for td in topic_data:
        cat = categories[td['category']]
        if Topic.objects.filter(title=td['title'], category=cat).exists():
            continue
        jitter(1.0, 4.0)
        topic = Topic.objects.create(category=cat, author=td['author'], title=td['title'])
        Post.objects.create(topic=topic, author=td['author'], content=td['first_post'])
        for reply_author, reply_content in td['replies']:
            jitter(0.5, 2.0)
            reply = Post.objects.create(topic=topic, author=reply_author, content=reply_content)
            # Add random likes from other personas
            liker1 = random_but(all_users, reply_author)
            liker2 = random_but(all_users, reply_author, liker1)
            PostLike.objects.get_or_create(user=liker1, post=reply)
            PostLike.objects.get_or_create(user=liker2, post=reply)
        topics_created += 1

    # Give varying realistic reputation to EVERY user based on their persona
    for user in all_users:
        defaults = {'reputation_points': 5, 'posts_count': 1, 'topics_count': 0, 'likes_received': 0, 'likes_given': 0}
        
        if user in staff:
            defaults = {'reputation_points': random.randint(300, 600), 'posts_count': random.randint(20, 50), 'topics_count': random.randint(5, 10), 'likes_received': random.randint(100, 200), 'likes_given': random.randint(50, 100)}
        elif user in developers:
            defaults = {'reputation_points': random.randint(150, 350), 'posts_count': random.randint(10, 30), 'topics_count': random.randint(2, 6), 'likes_received': random.randint(40, 90), 'likes_given': random.randint(20, 60)}
        elif user in designers:
            defaults = {'reputation_points': random.randint(100, 250), 'posts_count': random.randint(8, 20), 'topics_count': random.randint(1, 4), 'likes_received': random.randint(30, 70), 'likes_given': random.randint(30, 80)}
        elif user in business:
            defaults = {'reputation_points': random.randint(20, 100), 'posts_count': random.randint(2, 10), 'topics_count': random.randint(0, 2), 'likes_received': random.randint(5, 30), 'likes_given': random.randint(10, 40)}
        else:
            defaults = {'reputation_points': random.randint(5, 40), 'posts_count': random.randint(1, 5), 'topics_count': random.randint(0, 1), 'likes_received': random.randint(0, 10), 'likes_given': random.randint(2, 15)}

        rep, created = UserReputation.objects.get_or_create(user=user, defaults=defaults)
        if not created and rep.reputation_points == 0:
            for field, val in defaults.items():
                setattr(rep, field, val)
            rep.save()

    print(f'[+] Forum: {topics_created} topics created and reputation initialized for all users.')


if __name__ == '__main__':
    seed()

