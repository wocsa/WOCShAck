from django.db.models.signals import post_save
from django.dispatch import receiver
from Community.models.social import FriendRequest, Friendship
from Community.models.communication import Message
from Community.models.content import BlogPost, BlogComment
from Community.models.social import UserFollow


@receiver(post_save, sender=FriendRequest)
def create_friendship(sender, instance, **kwargs):
    if instance.status == "accepted":
        users = sorted([instance.sender, instance.receiver], key=lambda u: str(u.id))
        Friendship.objects.get_or_create(user1=users[0], user2=users[1])


@receiver(post_save, sender=FriendRequest)
def friend_request_notification(sender, instance, created, **kwargs):
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if created:
        create_notification(
            user=instance.receiver,
            notif_type=Notification.NotifType.FRIEND_REQUEST,
            title="New friend request",
            message=f"{instance.sender.username} sent you a friend request.",
            action_url='/community/friends/requests/',
        )
    elif instance.status == "accepted":
        create_notification(
            user=instance.sender,
            notif_type=Notification.NotifType.FRIEND_ACCEPT,
            title="Friend request accepted",
            message=f"{instance.receiver.username} accepted your friend request.",
            action_url='/community/friends/',
        )


@receiver(post_save, sender=Message)
def message_notification(sender, instance, created, **kwargs):
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if not created or instance.is_deleted:
        return

    conv = instance.conversation
    recipient = conv.user2 if conv.user1 == instance.sender else conv.user1
    create_notification(
        user=recipient,
        notif_type=Notification.NotifType.NEW_MESSAGE,
        title="New message",
        message=f"{instance.sender.username} sent you a message.",
        action_url=f'/community/messages/{conv.id}/',
    )


@receiver(post_save, sender=BlogPost)
def blog_post_notification(sender, instance, created, **kwargs):
    """Notify followers when a blog post is published."""
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if instance.status != BlogPost.Status.PUBLISHED:
        return

    if not instance.author:
        return

    followers = UserFollow.objects.filter(
        following=instance.author,
        notify_new_content=True
    ).select_related('follower')

    for follow in followers:
        create_notification(
            user=follow.follower,
            notif_type=Notification.NotifType.NEW_BLOG_POST,
            title="New blog post",
            message=f"{instance.author.username} published \"{instance.title}\".",
            action_url=f'/community/blog/{instance.slug}/',
        )


@receiver(post_save, sender=BlogComment)
def blog_comment_notification(sender, instance, created, **kwargs):
    """Notify blog post author when a comment is added."""
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if not created:
        return

    post_author = instance.post.author
    if not post_author or post_author == instance.author:
        return

    create_notification(
        user=post_author,
        notif_type=Notification.NotifType.BLOG_COMMENT,
        title="New comment on your post",
        message=f"{instance.author.username} commented on \"{instance.post.title}\".",
        action_url=f'/community/blog/{instance.post.slug}/',
    )


@receiver(post_save, sender='Forum.Post')
def forum_reply_notification(sender, instance, created, **kwargs):
    """Notify topic author when someone replies."""
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if not created:
        return

    topic = instance.topic
    if not topic.author or topic.author == instance.author:
        return

    create_notification(
        user=topic.author,
        notif_type=Notification.NotifType.FORUM_REPLY,
        title="New reply to your topic",
        message=f"{instance.author.username} replied to \"{topic.title}\".",
        action_url=f'/forum/topic/{topic.id}/',
    )


@receiver(post_save, sender='Forum.Post')
def forum_mention_notification(sender, instance, created, **kwargs):
    """Notify users mentioned with @username in a forum post."""
    import re
    from django.contrib.auth import get_user_model
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if not created:
        return

    User = get_user_model()
    mentions = set(re.findall(r'@(\w+)', instance.content or ''))

    for username in mentions:
        if username == instance.author.username:
            continue
        try:
            mentioned_user = User.objects.get(username=username)
            create_notification(
                user=mentioned_user,
                notif_type=Notification.NotifType.FORUM_MENTION,
                title="You were mentioned",
                message=f"{instance.author.username} mentioned you in \"{instance.topic.title}\".",
                action_url=f'/forum/topic/{instance.topic.id}/',
            )
        except User.DoesNotExist:
            continue


@receiver(post_save, sender='Shopping.Order')
def order_status_notification(sender, instance, created, **kwargs):
    """Notify buyer when order status changes."""
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if created:
        return

    status_messages = {
        'processing': 'Your order is now being processed.',
        'completed': 'Your order has been completed!',
        'cancelled': 'Your order has been cancelled.',
    }
    msg = status_messages.get(instance.status)
    if not msg:
        return

    create_notification(
        user=instance.user,
        notif_type=Notification.NotifType.ORDER_UPDATE,
        title="Order update",
        message=msg,
        action_url='/shop/orders/',
    )


@receiver(post_save, sender='Advertisement.Advertisement')
def ad_status_notification(sender, instance, created, **kwargs):
    """Notify advertiser when ad status changes to approved or rejected."""
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if created:
        return

    if instance.status in ('approved', 'active'):
        create_notification(
            user=instance.advertiser,
            notif_type=Notification.NotifType.AD_STATUS,
            title="Advertisement approved",
            message=f"Your ad \"{instance.title}\" has been approved!",
            action_url='/advertisement/',
        )
    elif instance.status == 'rejected':
        create_notification(
            user=instance.advertiser,
            notif_type=Notification.NotifType.AD_STATUS,
            title="Advertisement rejected",
            message=f"Your ad \"{instance.title}\" was not approved.",
            action_url='/advertisement/',
        )


@receiver(post_save, sender='Shopping.Review')
def review_notification(sender, instance, created, **kwargs):
    """Notify the CSS product author when a review is posted."""
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if not created:
        return

    css_product = instance.css_file
    if not css_product or not hasattr(css_product, 'creator') or css_product.creator == instance.user:
        return

    create_notification(
        user=css_product.creator,
        notif_type=Notification.NotifType.NEW_REVIEW,
        title="New review on your CSS",
        message=f"{instance.user.username} left a review on \"{css_product.name}\".",
        action_url=f'/shop/product/{css_product.id}/',
    )


@receiver(post_save, sender='Todo.Mission')
def mission_notification(sender, instance, created, **kwargs):
    """Notify user when a mission is created/assigned."""
    from Community.models.notification import Notification
    from Community.services.notification_service import create_notification

    if not created:
        return

    if not instance.user:
        return

    create_notification(
        user=instance.user,
        notif_type=Notification.NotifType.MISSION_ASSIGNED,
        title="New mission assigned",
        message=f"You have a new mission: \"{instance.title}\".",
        action_url='/todos/missions/',
    )
