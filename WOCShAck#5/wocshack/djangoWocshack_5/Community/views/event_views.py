from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.paginator import Paginator

from Community.models.content import Event, EventRegistration
from Community.functions import is_content_creator
from Community.services.feed_service import create_feed_item
from Community.models.feed import ActivityFeedItem


def event_list(request):
    event_type = request.GET.get('type')
    fmt = request.GET.get('format')
    show_past = request.GET.get('past') == '1'

    events = Event.objects.filter(status=Event.Status.PUBLISHED).select_related('organizer')
    if not show_past:
        events = events.filter(start_datetime__gte=timezone.now())
    if event_type:
        events = events.filter(event_type=event_type)
    if fmt:
        events = events.filter(format=fmt)

    paginator = Paginator(events, 10)
    page = paginator.get_page(request.GET.get('page'))

    user_registrations = {}
    my_drafts = []
    if request.user.is_authenticated:
        for reg in EventRegistration.objects.filter(user=request.user, event__in=[e.pk for e in page.object_list]):
            user_registrations[str(reg.event_id)] = reg.status
        my_drafts = list(
            Event.objects.filter(organizer=request.user, status=Event.Status.DRAFT)
                         .order_by('start_datetime')
        )

    return render(request, 'community/events/list.html', {
        'page_obj': page,
        'event_types': Event.EventType.choices,
        'formats': Event.Format.choices,
        'active_type': event_type,
        'active_format': fmt,
        'show_past': show_past,
        'user_registrations': user_registrations,
        'my_drafts': my_drafts,
    })


def event_detail(request, event_id):
    from django.http import Http404
    event = get_object_or_404(Event, id=event_id)
    if event.status != Event.Status.PUBLISHED:
        # Draft/cancelled events only visible to organizer or staff
        if not request.user.is_authenticated or (event.organizer != request.user and not request.user.is_staff):
            raise Http404
    registration = None
    if request.user.is_authenticated:
        registration = EventRegistration.objects.filter(user=request.user, event=event).first()

    attendees_count = event.registration_count()

    return render(request, 'community/events/detail.html', {
        'event': event,
        'registration': registration,
        'attendees_count': attendees_count,
        'is_full': event.is_full(),
        'is_upcoming': event.is_upcoming(),
    })


@login_required
@require_POST
def event_register(request, event_id):
    event = get_object_or_404(Event, id=event_id, status=Event.Status.PUBLISHED)

    if not event.is_upcoming():
        messages.error(request, "This event has already started.")
        return redirect('community:event_detail', event_id=event_id)

    if event.is_full():
        messages.error(request, "This event is at full capacity.")
        return redirect('community:event_detail', event_id=event_id)

    reg, created = EventRegistration.objects.get_or_create(
        user=request.user,
        event=event,
        defaults={'status': EventRegistration.Status.REGISTERED},
    )
    if not created and reg.status == EventRegistration.Status.CANCELLED:
        reg.status = EventRegistration.Status.REGISTERED
        reg.save(update_fields=['status'])
        messages.success(request, f"You have re-registered for \"{event.title}\".")
    elif created:
        try:
            create_feed_item(
                user=request.user,
                action_type=ActivityFeedItem.ActionType.EVENT_JOINED,
                title=f'Registered for event: {event.title}',
                description=event.description[:200] if event.description else '',
                icon='📅',
                related_object_id=str(event.id),
            )
        except Exception:
            pass
        messages.success(request, f"You are now registered for \"{event.title}\".")
    else:
        messages.info(request, "You are already registered for this event.")

    return redirect('community:event_detail', event_id=event_id)


@login_required
@require_POST
def event_cancel_registration(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    updated = EventRegistration.objects.filter(
        user=request.user, event=event, status=EventRegistration.Status.REGISTERED
    ).update(status=EventRegistration.Status.CANCELLED)

    if updated:
        messages.success(request, f"Your registration for \"{event.title}\" has been cancelled.")
    else:
        messages.error(request, "No active registration found to cancel.")
    return redirect('community:event_detail', event_id=event_id)


@login_required
def event_create(request):
    if not is_content_creator(request.user):
        messages.error(request, "You don't have permission to create events.")
        return redirect('community:event_list')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        event_type = request.POST.get('event_type', Event.EventType.WORKSHOP)
        fmt = request.POST.get('format', Event.Format.ONLINE)
        start_str = request.POST.get('start_datetime', '').strip()
        end_str = request.POST.get('end_datetime', '').strip()
        tz = request.POST.get('timezone', 'UTC').strip()
        capacity = request.POST.get('capacity', '').strip()
        meeting_link = request.POST.get('meeting_link', '').strip()
        status = request.POST.get('status', Event.Status.DRAFT)
        if status not in dict(Event.Status.choices):
            status = Event.Status.DRAFT

        if not title or not description or not start_str or not end_str:
            messages.error(request, "Title, description, start and end dates are required.")
        else:
            from datetime import datetime
            try:
                start_dt = timezone.make_aware(datetime.strptime(start_str, '%Y-%m-%dT%H:%M'))
                end_dt = timezone.make_aware(datetime.strptime(end_str, '%Y-%m-%dT%H:%M'))
            except (ValueError, TypeError):
                messages.error(request, "Invalid date format.")
            else:
                if end_dt <= start_dt:
                    messages.error(request, "End date must be after start date.")
                else:
                    cap = None
                    if capacity:
                        try:
                            cap = int(capacity)
                        except ValueError:
                            pass

                    event = Event.objects.create(
                        title=title,
                        description=description,
                        organizer=request.user,
                        event_type=event_type if event_type in dict(Event.EventType.choices) else Event.EventType.WORKSHOP,
                        format=fmt if fmt in dict(Event.Format.choices) else Event.Format.ONLINE,
                        start_datetime=start_dt,
                        end_datetime=end_dt,
                        timezone=tz or 'UTC',
                        capacity=cap,
                        meeting_link=meeting_link,
                        status=status,
                    )
                    messages.success(request, f'Event "{event.title}" created successfully.')
                    return redirect('community:event_detail', event_id=event.id)

    return render(request, 'community/events/create_edit.html', {
        'action': 'Create',
        'event': None,
        'event_types': Event.EventType.choices,
        'formats': Event.Format.choices,
        'statuses': Event.Status.choices,
    })


@login_required
def event_edit(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    # Only the organizer (who is a content creator) or staff/admin can edit
    is_owner = event.organizer == request.user
    if not (request.user.is_staff or (is_owner and is_content_creator(request.user))):
        messages.error(request, "You don't have permission to edit this event.")
        return redirect('community:event_list')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        event_type = request.POST.get('event_type', event.event_type)
        fmt = request.POST.get('format', event.format)
        start_str = request.POST.get('start_datetime', '').strip()
        end_str = request.POST.get('end_datetime', '').strip()
        tz = request.POST.get('timezone', 'UTC').strip()
        capacity = request.POST.get('capacity', '').strip()
        meeting_link = request.POST.get('meeting_link', '').strip()
        status = request.POST.get('status', event.status)
        if status not in dict(Event.Status.choices):
            status = event.status

        if not title or not description or not start_str or not end_str:
            messages.error(request, "Title, description, start and end dates are required.")
        else:
            from datetime import datetime
            try:
                start_dt = timezone.make_aware(datetime.strptime(start_str, '%Y-%m-%dT%H:%M'))
                end_dt = timezone.make_aware(datetime.strptime(end_str, '%Y-%m-%dT%H:%M'))
            except (ValueError, TypeError):
                messages.error(request, "Invalid date format.")
            else:
                if end_dt <= start_dt:
                    messages.error(request, "End date must be after start date.")
                else:
                    cap = None
                    if capacity:
                        try:
                            cap = int(capacity)
                        except ValueError:
                            pass

                    event.title = title
                    event.description = description
                    event.event_type = event_type if event_type in dict(Event.EventType.choices) else event.event_type
                    event.format = fmt if fmt in dict(Event.Format.choices) else event.format
                    event.start_datetime = start_dt
                    event.end_datetime = end_dt
                    event.timezone = tz or 'UTC'
                    event.capacity = cap
                    event.meeting_link = meeting_link
                    event.status = status
                    event.save()
                    messages.success(request, f'Event "{event.title}" updated successfully.')
                    return redirect('community:event_detail', event_id=event.id)

    return render(request, 'community/events/create_edit.html', {
        'action': 'Edit',
        'event': event,
        'event_types': Event.EventType.choices,
        'formats': Event.Format.choices,
        'statuses': Event.Status.choices,
    })


@login_required
@require_POST
def event_delete(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    # Only the organizer (who is a content creator) or staff/admin can delete
    is_owner = event.organizer == request.user
    if not (request.user.is_staff or (is_owner and is_content_creator(request.user))):
        messages.error(request, "You don't have permission to delete this event.")
        return redirect('community:event_list')

    title = event.title
    event.delete()
    messages.success(request, f'Event "{title}" deleted.')
    return redirect('community:event_list')
