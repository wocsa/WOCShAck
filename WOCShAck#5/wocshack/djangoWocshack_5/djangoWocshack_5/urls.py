"""
URL configuration for djangoWocshack_5 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.http import HttpResponse


def robots_txt(request):
    content = (
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Disallow: /api/users/\n"
        "Disallow: /banking/api/\n"
        "Disallow: /debug/\n"
        "Disallow: /backup/db.sqlite3\n"
        "Disallow: /banking/pin-skip/\n"
        "Disallow: /banking/webhook/\n"
    )
    return HttpResponse(content, content_type='text/plain')


urlpatterns = [
    path('robots.txt', robots_txt, name='robots_txt'),
    path('admin/', admin.site.urls),
    path('', include("Todo.urls")),
    path('account/', include("Account.urls")),
    path('shop/', include("Shopping.urls")),
    path("account/", include("django.contrib.auth.urls")),
    path('banking/', include("Bank.urls")),
    path('advertisement/', include("Advertisement.urls")),
    path('api/', include("Api.urls")),
    path('chatbot/', include("Chatbot.urls")),
    path('forum/', include("Forum.urls")),
    path('community/', include("Community.urls", namespace="community")),
    path('developer/', include("Developer.urls")),
    path('admin-panel/', include("Moderation.urls", namespace="admin_panel")),
]

# Serve media files even in production (DEBUG=False) because BunkerWeb
# lacks volume mounts to serve them directly.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

handler404 = 'django.views.defaults.page_not_found'
