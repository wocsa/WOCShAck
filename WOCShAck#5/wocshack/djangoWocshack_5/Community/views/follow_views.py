from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.http import JsonResponse

from Community.models.social import UserFollow

User = get_user_model()


@login_required
@require_POST
def follow_user(request, user_id):
    target = get_object_or_404(User, id=user_id)
    if target == request.user:
        return redirect('community:user_profile', user_id=user_id)

    follow, created = UserFollow.objects.get_or_create(
        follower=request.user,
        following=target,
    )
    if created:
        # Notify the followed user
        try:
            from Community.models.notification import Notification
            from Community.services.notification_service import create_notification
            create_notification(
                user=target,
                notif_type=Notification.NotifType.NEW_FOLLOWER,
                title="New follower",
                message=f"{request.user.username} started following you.",
                action_url=f'/community/profile/{request.user.id}/',
            )
        except Exception:
            pass

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'following': True, 'followers_count': target.followers.count()})
    return redirect('community:user_profile', user_id=user_id)


@login_required
@require_POST
def unfollow_user(request, user_id):
    target = get_object_or_404(User, id=user_id)
    UserFollow.objects.filter(follower=request.user, following=target).delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'following': False, 'followers_count': target.followers.count()})
    return redirect('community:user_profile', user_id=user_id)


@login_required
def followers_list(request, user_id):
    target = get_object_or_404(User, id=user_id)
    followers_qs = UserFollow.objects.filter(following=target).select_related('follower')

    paginator = Paginator(followers_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    my_following_ids = set(
        UserFollow.objects.filter(follower=request.user).values_list('following_id', flat=True)
    )

    return render(request, 'community/follow/followers.html', {
        'target': target,
        'followers': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'my_following_ids': my_following_ids,
    })


@login_required
def following_list(request, user_id):
    target = get_object_or_404(User, id=user_id)
    following_qs = UserFollow.objects.filter(follower=target).select_related('following')

    paginator = Paginator(following_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    my_following_ids = set(
        UserFollow.objects.filter(follower=request.user).values_list('following_id', flat=True)
    )

    return render(request, 'community/follow/following.html', {
        'target': target,
        'following': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'my_following_ids': my_following_ids,
    })
