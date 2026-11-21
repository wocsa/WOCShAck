
from Community.models.social import Friendship, FriendRequest
from django.contrib.auth import get_user_model
from django.db.models import Q
from Community.models.communication import Conversation, Message, MessageReport
User = get_user_model()


def _check_developer_role(user):
    """Check if user has the developer_role purchased feature."""
    try:
        from Account.models import PurchasedFeature
        return PurchasedFeature.has_feature(user, 'developer_role')
    except Exception:
        return False


def is_content_creator(user):
    """
    True if the user is a developer, staff, or superuser.
    Content creators can create blog posts, events, and tutorials.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff or user.is_superuser:
        return True
    return _check_developer_role(user)


def are_friends(user1, user2):
    users = sorted([user1, user2], key=lambda u: str(u.id))
    return Friendship.objects.filter(user1=users[0], user2=users[1]).exists()

def request_exists(user1, user2):
    return FriendRequest.objects.filter(
        Q(sender=user1, receiver=user2) | Q(sender=user2, receiver=user1)
    ).exists()

def list_of_friends(user):
    friendships = Friendship.objects.filter(
        Q(user1=user) | Q(user2=user)
    ).select_related('user1', 'user2')

    friends = []
    for friendship in friendships:
        if friendship.user1 == user:
            friends.append(friendship.user2)
        else:
            friends.append(friendship.user1)

    return friends