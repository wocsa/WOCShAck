from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Q
from Community.models.communication import Conversation, Message, MessageReport
from Community.models.social import Friendship, UserFollow, FriendRequest
from Community.forms import MessageForm
from Community.services.notification_service import unread_count

User = get_user_model()


def index(request):
    context = {}
    if request.user.is_authenticated:
        context['notif_count'] = unread_count(request.user)
    return render(request, 'community.html', context)

def profile(request, user_id):
    user = get_object_or_404(User, id=user_id)

    is_authenticated = request.user.is_authenticated
    is_own_profile = is_authenticated and request.user == user

    is_following = False
    is_friend = False
    pending_request = False

    if is_authenticated and not is_own_profile:
        is_following = UserFollow.objects.filter(
            follower=request.user, following=user
        ).exists()
        is_friend = Friendship.objects.filter(
            Q(user1=request.user, user2=user) | Q(user1=user, user2=request.user)
        ).exists()
        pending_request = FriendRequest.objects.filter(
            sender=request.user, receiver=user, status='pending'
        ).exists()

    progress = None
    followers_count = user.followers.count()
    following_count = user.following.count()

    return render(request, 'community/profil.html', {
        "user": user,
        "is_authenticated": is_authenticated,
        "is_own_profile": is_own_profile,
        "is_following": is_following,
        "is_friend": is_friend,
        "pending_request": pending_request,
        "progress": progress,
        "followers_count": followers_count,
        "following_count": following_count,
    })
