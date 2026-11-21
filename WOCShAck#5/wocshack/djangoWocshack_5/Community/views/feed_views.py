from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from Community.services.feed_service import get_feed_for_user
from Community.models.feed import FeedPreferences, ActivityFeedItem


@login_required
def activity_feed(request):
    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    page_size = 20
    offset = (page - 1) * page_size

    feed = list(get_feed_for_user(request.user, page_size=page_size + 1, offset=offset))
    has_next = len(feed) > page_size
    feed = feed[:page_size]

    prefs, _ = FeedPreferences.objects.get_or_create(user=request.user)

    return render(request, 'community/feed/activity_feed.html', {
        'feed': feed,
        'page': page,
        'has_next': has_next,
        'has_prev': page > 1,
        'prefs': prefs,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def feed_preferences(request):
    prefs, _ = FeedPreferences.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        prefs.show_friends      = request.POST.get('show_friends') == 'on'
        prefs.show_blog_posts   = request.POST.get('show_blog_posts') == 'on'
        prefs.show_forum_posts  = request.POST.get('show_forum_posts') == 'on'
        prefs.show_showcases    = request.POST.get('show_showcases') == 'on'
        prefs.show_tutorials    = request.POST.get('show_tutorials') == 'on'
        prefs.show_css          = request.POST.get('show_css') == 'on'
        prefs.show_reviews      = request.POST.get('show_reviews') == 'on'
        prefs.show_events       = request.POST.get('show_events') == 'on'
        prefs.default_visibility = request.POST.get('default_visibility', ActivityFeedItem.Visibility.PUBLIC)
        prefs.save()
        messages.success(request, 'Feed preferences updated.')
        return redirect('community:activity_feed')

    return render(request, 'community/feed/preferences.html', {'prefs': prefs})
