from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST, require_http_methods
from django.core.paginator import Paginator

from Community.models.notification import Notification, NotificationPreference
from Community.services.notification_service import (
    mark_read, mark_all_read, unread_count, purge_expired
)


@login_required
def notifications_list(request):
    """Display paginated list of notifications for the current user."""
    purge_expired(request.user)
    
    # Get all notifications for the user
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    
    # Set up pagination
    paginator = Paginator(notifications, 20)  # 20 notifications per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    unread = unread_count(request.user)

    try:
        prefs = request.user.notif_preferences
    except NotificationPreference.DoesNotExist:
        prefs = None

    return render(request, 'community/notifications/list.html', {
        'page_obj': page_obj,
        'notifications': page_obj,  # Keep for compatibility
        'unread_count': unread,
        'prefs': prefs,
    })


@login_required
@require_POST
def mark_notification_read(request, notif_id):
    """Mark a specific notification as read."""
    notification = get_object_or_404(Notification, id=notif_id, user=request.user)
    mark_read(notif_id, request.user)
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'unread': unread_count(request.user)})
    
    messages.success(request, "Notification marked as read.")
    return redirect('community:notifications_list')


@login_required
@require_POST
def mark_all_notifications_read(request):
    """Mark all notifications as read for the current user."""
    mark_all_read(request.user)
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'unread': 0})
    
    messages.success(request, "All notifications marked as read.")
    return redirect('community:notifications_list')


@login_required
def notifications_unread_count(request):
    """Endpoint JSON pour le badge de la navbar."""
    return JsonResponse({'unread': unread_count(request.user)})


@login_required
def notifications_recent(request):
    """JSON endpoint returning last 5 unread notifications for the dropdown."""
    purge_expired(request.user)
    recent = Notification.objects.filter(
        user=request.user, is_read=False
    ).order_by('-created_at')[:5]

    items = []
    for n in recent:
        items.append({
            'id': str(n.id),
            'type': n.notif_type,
            'title': n.title,
            'message': n.message,
            'action_url': n.action_url,
            'created_at': n.created_at.isoformat(),
        })

    return JsonResponse({'notifications': items, 'unread': unread_count(request.user)})


@login_required
@require_http_methods(['GET', 'POST'])
def notification_preferences(request):
    """Handle notification preferences form (GET/POST)."""
    prefs, created = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # Update preferences based on form checkboxes
        prefs.friend_requests = request.POST.get('friend_requests') == 'on'
        prefs.messages        = request.POST.get('messages') == 'on'
        prefs.level_ups       = request.POST.get('level_ups') == 'on'
        prefs.achievements    = request.POST.get('achievements') == 'on'
        prefs.followers       = request.POST.get('followers') == 'on'
        prefs.system          = request.POST.get('system') == 'on'
        prefs.blog            = request.POST.get('blog') == 'on'
        prefs.forum           = request.POST.get('forum') == 'on'
        prefs.orders          = request.POST.get('orders') == 'on'
        prefs.advertisements  = request.POST.get('advertisements') == 'on'
        prefs.save()
        
        messages.success(request, "Notification preferences updated successfully.")
        return redirect('community:notifications_list')

    return render(request, 'community/notifications/preferences.html', {
        'prefs': prefs,
        'created': created,
    })
