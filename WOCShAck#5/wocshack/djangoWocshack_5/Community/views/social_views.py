from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.html import escape
from Community.models.social import FriendRequest, Friendship
from Community.forms import FriendRequestActionForm
from Community.functions import are_friends, request_exists, list_of_friends


User = get_user_model()



@login_required
@require_POST
def send_friend_request(request):
    user_id = request.POST.get("user_id")
    receiver = get_object_or_404(User, id=user_id)

    if receiver == request.user:
        messages.error(request, "You cannot send a friend request to yourself.")
        return redirect("community:add_friends")

    if are_friends(request.user, receiver):
        messages.error(request, "You are already friends with this user.")
        return redirect("community:add_friends")

    # If current user already sent a pending request, cancel it before re-sending
    existing_from_me = FriendRequest.objects.filter(
        sender=request.user, receiver=receiver, status='pending'
    ).first()
    if existing_from_me:
        existing_from_me.delete()

    # If other user already sent us a request, inform the sender
    existing_from_them = FriendRequest.objects.filter(
        sender=receiver, receiver=request.user, status='pending'
    ).first()
    if existing_from_them:
        messages.info(request, escape(receiver.username) + " has already sent you a friend request. Check your pending requests.")
        return redirect("community:friend_requests")

    FriendRequest.objects.create(
        sender=request.user,
        receiver=receiver
    )

    messages.success(request, "Friend request sent to " + escape(receiver.username) + ".")
    return redirect("community:add_friends")

@login_required
@require_POST
def suppress_friend_request(request):
    user_id = request.POST.get("user_id")
    receiver = get_object_or_404(User, id=user_id)

    if receiver == request.user:
        messages.error(request, "Invalid request.")
        return redirect("community:friends_list")

    if request_exists(request.user, receiver):
        FriendRequest.objects.filter(
            Q(sender=request.user, receiver=receiver) |
            Q(sender=receiver, receiver=request.user)
        ).first().delete()
        messages.success(request, "Friend request cancelled.")

    return redirect("community:add_friends")


@login_required
def handle_friend(request, friend_id):

    friend = get_object_or_404(User, id=friend_id)
    if friend == request.user:
        return redirect("community:friends_list")

    
    if not are_friends(request.user, friend):
        return redirect("community:friends_list")
    
    friendship = Friendship.objects.filter(
        Q(user1=request.user, user2=friend) | Q(user1=friend, user2=request.user)
    ).first()

    if friendship.user1 == request.user:
        is_friend_blocked = friendship.user2_blocked
        are_you_blocked = friendship.user1_blocked
    else:
        is_friend_blocked = friendship.user1_blocked
        are_you_blocked = friendship.user2_blocked



    return render(request, "community/social/handle_friend.html", {
        "friend": friend,
        "is_friend_blocked": is_friend_blocked,
        "are_you_blocked": are_you_blocked,
    })

@login_required
@require_POST
def suppr_friend(request):
    user_id = request.POST.get("user_id")
    receiver = get_object_or_404(User, id=user_id)

    if receiver == request.user:
        messages.error(request, "Invalid request.")
        return redirect("community:friends_list")

    if not are_friends(request.user, receiver):
        messages.error(request, "This user is not your friend.")
        return redirect("community:friends_list")

    if request_exists(request.user, receiver):
        FriendRequest.objects.filter(
            Q(sender=request.user, receiver=receiver) |
            Q(sender=receiver, receiver=request.user)
        ).first().delete()

    Friendship.objects.filter(
        Q(user1=request.user, user2=receiver) | Q(user1=receiver, user2=request.user)
    ).first().delete()

    messages.success(request, "User " + escape(receiver.username) + " removed from friends.")
    return redirect("community:friends_list")

@login_required
@require_POST
def block_friend(request):
    user_id = request.POST.get("user_id")
    receiver = get_object_or_404(User, id=user_id)

    if receiver == request.user:
        messages.error(request, "Invalid request.")
        return redirect("community:friends_list")

    
    if not are_friends(request.user, receiver):
        return redirect("community:friends_list")
    
    friendship = Friendship.objects.filter(
        Q(user1=request.user, user2=receiver) | Q(user1=receiver, user2=request.user)
    ).first()


    if friendship.user1 == request.user:
        if friendship.user2_blocked:
            return redirect("community:friends_list")
        else:
            friendship.user2_blocked=True
            friendship.save()
    else:
        if friendship.user1_blocked:
            return redirect("community:friends_list")
        else:
            friendship.user1_blocked=True
            friendship.save()
    messages.success(request, "User " + escape(receiver.username) + " blocked successfully.")

    return redirect("community:handle_friend", friend_id=receiver.id)



@login_required
@require_POST
def unblock_friend(request):
    user_id = request.POST.get("user_id")
    receiver = get_object_or_404(User, id=user_id)

    if receiver == request.user:
        messages.error(request, "Invalid request.")
        return redirect("community:friends_list")



    if not are_friends(request.user, receiver):
        return redirect("community:friends_list")
    
    friendship = Friendship.objects.filter(
        Q(user1=request.user, user2=receiver) | Q(user1=receiver, user2=request.user)
    ).first()

    if friendship.user1 == request.user:
        if not friendship.user2_blocked:
            return redirect("community:friends_list")
        else:
            friendship.user2_blocked=False
            friendship.save()
    else:
        if not friendship.user1_blocked:
            return redirect("community:friends_list")
        else:
            friendship.user1_blocked=False
            friendship.save()

    messages.success(request, "User " + escape(receiver.username) + " unblocked successfully.")
    return redirect("community:handle_friend", friend_id=receiver.id)


@login_required
def friend_requests(request):
    requests_received = FriendRequest.objects.filter(
        receiver=request.user,
        status="pending"
    )
    requests_sent = FriendRequest.objects.filter(
        sender=request.user,
        status="pending"
    )

    return render(request, "community/social/friend_requests.html", {
        "requests_received": requests_received,
        "requests_sent": requests_sent
    })


@login_required
@require_POST
def handle_friend_request(request, request_id):
    friend_request = get_object_or_404(
        FriendRequest,
        id=request_id,
        receiver=request.user
    )

    form = FriendRequestActionForm(request.POST)
    if form.is_valid():
        action = form.cleaned_data["action"]
        friend_request.status = action
        friend_request.save()
        if action == "accepted":
            messages.success(request, "Friend request accepted successfully.")
        else:
            messages.success(request, "Friend request rejected successfully.")

    return redirect("community:friend_requests")




@login_required
def friends_list(request):

    friends = list_of_friends(request.user)

    return render(request, "community/social/friends_list.html", {
        "friends": friends
    })


@login_required
def add_friends(request):
    query = request.GET.get("q", "").strip()

    users = []
    sent_ids = set(
        FriendRequest.objects.filter(sender=request.user, status="pending")
        .values_list("receiver_id", flat=True)
    )

    sent_requests = set(
        FriendRequest.objects.filter(sender=request.user, status="pending")
    )

    receiv_ids= set(FriendRequest.objects.filter(receiver=request.user, status="pending").values_list("sender_id", flat=True)
    )
    receiv_users = User.objects.filter(id__in=receiv_ids)
    
    receiv_reqs = set (FriendRequest.objects.filter(receiver=request.user, status="pending"))

    if query:
        friend_ids_as_user1 = set(
            Friendship.objects.filter(user1=request.user).values_list('user2_id', flat=True)
        )
        friend_ids_as_user2 = set(
            Friendship.objects.filter(user2=request.user).values_list('user1_id', flat=True)
        )
        friend_ids = friend_ids_as_user1 | friend_ids_as_user2

        users = User.objects.filter(username__icontains=query) \
            .exclude(id=request.user.id) \
            .exclude(id__in=friend_ids) \
            .exclude(id__in=sent_ids)

    context = {
        "query": query,
        "users": users,
        "sent_requests": sent_requests,
        "receiv_users": receiv_users,
        "receiv_reqs": receiv_reqs
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(
            request,
            "community/social/partials/add_friends_results.html",
            context
        )

    return render(
        request,
        "community/social/add_friends.html",
        context
    )