"""
Context processor that provides ``current_app`` to every template.

``current_app`` is derived from the resolved URL namespace / prefix so that
header navigation links can highlight the active section.

Mapping (URL prefix → app key):
    /banking/   → bank
    /shop/      → shop
    /forum/     → forum
    /account/   → account
    /developer/ → developer
    /community/ → community
    /chatbot/   → chatbot
    /advertisement/ → advertisement
    /api/       → api
    /admin-panel/ → moderation
    /todos/     → todos
"""


def current_app(request):
    """Return ``{'current_app': '<key>'}`` based on ``request.path``."""
    path = request.path

    # Ordered most-specific first to avoid prefix collisions
    mapping = [
        ('/admin-panel/', 'moderation'),
        ('/banking/', 'bank'),
        ('/shop/', 'shop'),
        ('/forum/', 'forum'),
        ('/developer/', 'developer'),
        ('/community/', 'community'),
        ('/chatbot/', 'chatbot'),
        ('/advertisement/', 'advertisement'),
        ('/api/', 'api'),
        ('/account/', 'account'),
        ('/todos/', 'todos'),
    ]

    for prefix, app_key in mapping:
        if path.startswith(prefix):
            return {'current_app': app_key}

    return {'current_app': ''}
