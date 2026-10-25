# CommunityEngagement/views/messaging_views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q, Max, Count, Exists, OuterRef
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.views.decorators.http import require_POST

from Community.models.communication import Conversation, Message, MessageReport, MessageRead
from Community.models.social import Friendship
from Community.forms import MessageForm
from Community.functions import are_friends, request_exists, list_of_friends
from Community.services.notification_service import create_notification
from Community.models.notification import Notification

User = get_user_model()


@login_required
def inbox(request):
    """List all conversations for the current user, ordered by most recent message."""
    # Only show conversations where the two participants are still friends.
    active_friendship = Friendship.objects.filter(
        Q(user1=OuterRef('user1'), user2=OuterRef('user2')) |
        Q(user1=OuterRef('user2'), user2=OuterRef('user1'))
    )
    conversations = Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).filter(
        Exists(active_friendship)
    ).annotate(
        last_message_time=Max('messages__timestamp'),
        unread_count=Count(
            'messages',
            filter=Q(messages__is_deleted=False) & ~Q(messages__sender=request.user) & ~Q(messages__reads__user=request.user)
        )
    ).order_by('-last_message_time')

    conversation_data = []
    for conv in conversations:
        other_user = conv.user2 if conv.user1 == request.user else conv.user1
        last_message = conv.messages.order_by('-timestamp').first()
        conversation_data.append({
            'conversation': conv,
            'other_user': other_user,
            'last_message': last_message,
            'unread_count': conv.unread_count,
        })

    paginator = Paginator(conversation_data, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'community/messaging/inbox.html', {
        'page_obj': page_obj,
    })


@login_required
def start_conversation(request, user_id):
    other_user = get_object_or_404(User, id=user_id)

    if not are_friends(request.user, other_user):
        return redirect("community:friends_list")

    conversation = Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).filter(
        Q(user1=other_user) | Q(user2=other_user)
    ).first()

    if not conversation:
        conversation = Conversation.objects.create( 
        user1=request.user,
        user2=other_user
        )

        

    return redirect("community:conversation_detail", conversation_id=conversation.id)


@login_required
def conversation_detail(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)

    if request.user not in [conversation.user1, conversation.user2]:
        return redirect("community:friends_list")
    
    if not are_friends(conversation.user1, conversation.user2):
        return redirect("community:friends_list")
    friendship = Friendship.objects.filter(
        Q(user1=conversation.user1, user2=conversation.user2) | Q(user1=conversation.user2, user2=conversation.user1)
    ).first()

    if friendship.user1 == request.user:
        is_friend_blocked = friendship.user2_blocked
        are_you_blocked = friendship.user1_blocked
    else:
        is_friend_blocked = friendship.user1_blocked
        are_you_blocked = friendship.user2_blocked

    messages = conversation.messages.all().order_by("-timestamp")

    paginator = Paginator(messages, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    form = MessageForm()

    # Mark received messages as read
    other_user = conversation.user2 if conversation.user1 == request.user else conversation.user1
    unread_msgs = conversation.messages.filter(sender=other_user, is_deleted=False).exclude(reads__user=request.user)
    MessageRead.objects.bulk_create(
        [MessageRead(message=msg, user=request.user) for msg in unread_msgs],
        ignore_conflicts=True
    )

    # Build set of message IDs read by the other user (for showing ✓✓)
    read_by_other_ids = set(
        MessageRead.objects.filter(
            message__conversation=conversation,
            user=other_user,
        ).values_list('message_id', flat=True)
    )

    friends = list_of_friends(request.user)

    return render(request, "community/messaging/conversation_detail.html", {
        "conversation": conversation,
        "page_obj": page_obj,
        "form": form,
        "is_friend_blocked": is_friend_blocked,
        "are_you_blocked": are_you_blocked,
        "friends": friends,
        "read_by_other_ids": read_by_other_ids,
        "other_user": other_user,
    })


@login_required
@require_POST
def send_message(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)

    if not are_friends(conversation.user1, conversation.user2):
        return redirect("community:friends_list")

    if conversation.user1 == request.user:
        receiver = conversation.user2
    elif conversation.user2 == request.user :
        receiver = conversation.user1
    else :
        return redirect("community:friends_list")
    
    friendship = Friendship.objects.filter(Q(user1 = receiver, user2 = request.user) | Q(user1 = request.user, user2 = receiver)).first()

    if friendship.user1 == request.user:
        if friendship.user1_blocked :
            messages.warning(
                    request,
                    mark_safe(
                        "<strong>⚠️You are blocked by "+escape(friendship.user2.username)+".</strong>"
                        "You can't send messages to user that have blocked you"
                        ))
            return redirect("community:conversation_detail", conversation_id=conversation.id)
        elif friendship.user2_blocked :
            messages.warning(
                    request,
                    mark_safe(
                        "<strong>⚠️You have blocked "+escape(friendship.user2.username)+".</strong>"
                        "You can't send messages to user that have blocked you"
                        ))
            return redirect("community:conversation_detail", conversation_id=conversation.id)
    else:
        if friendship.user2_blocked :
            messages.warning(
                    request,
                    mark_safe(
                        "<strong>⚠️You are blocked by "+escape(friendship.user1.username)+".</strong>"
                        "You can't send messages to user that have blocked you"
                        ))
            return redirect("community:conversation_detail", conversation_id=conversation.id)
        elif friendship.user1_blocked :
            messages.warning(
                    request,
                    mark_safe(
                        "<strong>⚠️You have blocked "+escape(friendship.user1.username)+".</strong>"
                        "You can't send messages to user that have blocked you"
                        ))
            return redirect("community:conversation_detail", conversation_id=conversation.id)


    form = MessageForm(request.POST)
    if form.is_valid():
        Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=form.cleaned_data["content"]
        )
        messages.success(request, "Message sent successfully.")
    else:
        messages.error(request, "Invalid message content.")

    return redirect("community:conversation_detail", conversation_id=conversation.id)

@login_required
@require_POST
def report_message(request, message_id):
    message = get_object_or_404(Message, id=message_id)
    
    # Verify user is participant in conversation
    if request.user not in [message.conversation.user1, message.conversation.user2]:
        messages.error(request, "Access denied.")
        return redirect("community:friends_list")
    
    # Can't report your own message
    if message.sender == request.user:
        messages.error(request, "You cannot report your own message.")
        return redirect("community:conversation_detail", conversation_id=message.conversation.id)
    
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Please provide a reason for reporting.")
        return redirect("community:conversation_detail", conversation_id=message.conversation.id)
    
    # Check if already reported by this user
    if MessageReport.objects.filter(reporter=request.user, message=message).exists():
        messages.warning(request, "You have already reported this message.")
    else:
        MessageReport.objects.create(
            reporter=request.user,
            message=message,
            reason=reason
        )
        message.is_reported = True
        message.save()
        messages.success(request, "Message reported successfully.")

    return redirect("community:conversation_detail", conversation_id=message.conversation.id)

@login_required
@require_POST
def edit_message(request, message_id):
    message = get_object_or_404(Message, id=message_id, sender=request.user)
    
    # Verify user is participant in conversation
    if request.user not in [message.conversation.user1, message.conversation.user2]:
        messages.error(request, "Access denied.")
        return redirect("community:friends_list")
    
    # Can't edit reported or deleted messages
    if message.is_reported or message.is_deleted:
        messages.error(request, "This message cannot be edited.")
        return redirect("community:conversation_detail", conversation_id=message.conversation.id)
    
    new_content = request.POST.get("new_content", "").strip()
    if new_content:
        message.content = new_content
        message.is_edited = True
        message.save()
        messages.success(request, "Message updated successfully.")
    else:
        messages.error(request, "Message content cannot be empty.")
    
    return redirect("community:conversation_detail", conversation_id=message.conversation.id)


@login_required
@require_POST
def delete_message(request, message_id):
    message = get_object_or_404(Message, id=message_id, sender=request.user)
    
    # Verify user is participant in conversation
    if request.user not in [message.conversation.user1, message.conversation.user2]:
        messages.error(request, "Access denied.")
        return redirect("community:friends_list")
    
    # Can't delete reported messages
    if message.is_reported:
        messages.error(request, "Reported messages cannot be deleted.")
        return redirect("community:conversation_detail", conversation_id=message.conversation.id)
    
    if not message.is_deleted:
        message.is_deleted = True
        message.content = "[Deleted message]"
        message.save()
        messages.success(request, "Message deleted successfully.")
    
    return redirect("community:conversation_detail", conversation_id=message.conversation.id)



@login_required
@require_POST
def transfer_message(request, message_id):
    """Forward a message to another conversation."""
    message = get_object_or_404(Message, id=message_id)

    if message.is_deleted:
        messages.error(request, "Deleted messages cannot be forwarded.")
        return redirect("community:conversation_detail", conversation_id=message.conversation.id)

    # Verify user is participant in conversation
    if request.user not in [message.conversation.user1, message.conversation.user2]:
        messages.error(request, "Access denied.")
        return redirect("community:friends_list")
    
    target_user_id = request.POST.get("target_user_id")
    if not target_user_id:
        messages.error(request, "Please select a user to forward the message to.")
        return redirect("community:conversation_detail", conversation_id=message.conversation.id)
    
    try:
        target_user = User.objects.get(id=target_user_id)
    except User.DoesNotExist:
        messages.error(request, "Target user not found.")
        return redirect("community:conversation_detail", conversation_id=message.conversation.id)
    
    # Check if users are friends
    if not are_friends(request.user, target_user):
        messages.error(request, "You can only forward messages to friends.")
        return redirect("community:conversation_detail", conversation_id=message.conversation.id)
    
    # Find or create conversation with target user
    target_conversation = Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).filter(
        Q(user1=target_user) | Q(user2=target_user)
    ).first()
    
    if not target_conversation:
        target_conversation = Conversation.objects.create(
            user1=request.user,
            user2=target_user
        )
    
    # Create forwarded message
    forwarded_content = f"[Forwarded message from {message.sender.username}]: {message.content}"
    Message.objects.create(
        conversation=target_conversation,
        sender=request.user,
        content=forwarded_content
    )
    
    messages.success(request, f"Message forwarded to {target_user.username}.")
    return redirect("community:conversation_detail", conversation_id=message.conversation.id)


@login_required
@require_POST
def answer_message(request, message_id):
    """Reply to a specific message in a conversation."""
    message = get_object_or_404(Message, id=message_id)
    
    # Verify user is participant in conversation
    if request.user not in [message.conversation.user1, message.conversation.user2]:
        messages.error(request, "Access denied.")
        return redirect("community:friends_list")
    
    reply_content = request.POST.get("reply_content", "").strip()
    if not reply_content:
        messages.error(request, "Reply content cannot be empty.")
        return redirect("community:conversation_detail", conversation_id=message.conversation.id)
    
    # Create reply message with reference to original
    reply_text = f"Reply to {message.sender.username}: {reply_content}"
    Message.objects.create(
        conversation=message.conversation,
        sender=request.user,
        content=reply_text
    )
    
    
    messages.success(request, "Reply sent successfully.")
    return redirect("community:conversation_detail", conversation_id=message.conversation.id)