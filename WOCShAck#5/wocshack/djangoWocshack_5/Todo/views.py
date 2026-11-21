from django.shortcuts import render, get_object_or_404, redirect, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from .models import Mission


def index(request):
    return render(request, "index.html")


@login_required
def mission_list(request):
    """List missions for the authenticated user, with filtering, sorting, and pagination."""
    missions = Mission.objects.filter(user=request.user)

    # Include staff-shared missions
    staff_shared = Mission.objects.filter(is_staff_shared=True).exclude(user=request.user)
    missions = (missions | staff_shared).distinct()

    # --- Filtering ---
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('search', '')

    if status_filter:
        missions = missions.filter(status=status_filter)
    if priority_filter:
        missions = missions.filter(priority=priority_filter)
    if category_filter:
        missions = missions.filter(category=category_filter)
    if search_query:
        missions = missions.filter(
            models_Q(title__icontains=search_query) |
            models_Q(description__icontains=search_query)
        )

    # --- Sorting ---
    sort_by = request.GET.get('sort', 'created_at')
    order = request.GET.get('order', 'desc')

    valid_sort_fields = ['title', 'status', 'priority', 'due_date', 'created_at', 'updated_at']
    if sort_by not in valid_sort_fields:
        sort_by = 'created_at'

    order_prefix = '-' if order == 'desc' else ''
    missions = missions.order_by(f'{order_prefix}{sort_by}')

    # --- Pagination ---
    paginator = Paginator(missions, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get distinct categories for the filter dropdown
    categories = (
        Mission.objects.filter(user=request.user)
        .exclude(category='')
        .values_list('category', flat=True)
        .distinct()
        .order_by('category')
    )

    context = {
        'page_obj': page_obj,
        'status_choices': Mission.Status.choices,
        'priority_choices': Mission.Priority.choices,
        'categories': categories,
        'current_status': status_filter,
        'current_priority': priority_filter,
        'current_category': category_filter,
        'current_search': search_query,
        'current_sort': sort_by,
        'current_order': order,
        'now': timezone.now(),
    }
    return render(request, 'missions/mission_list.html', context)


# Import Q for search
from django.db.models import Q as models_Q


@login_required
def mission_create(request):
    """Create a new mission."""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        priority = request.POST.get('priority', Mission.Priority.MEDIUM)
        status = request.POST.get('status', Mission.Status.PENDING)
        category = request.POST.get('category', '').strip()
        due_date_str = request.POST.get('due_date', '').strip()
        is_staff_shared = request.POST.get('is_staff_shared') == 'on'

        if not title:
            messages.error(request, 'Mission title is required.')
            return render(request, 'missions/mission_form.html', {
                'action': 'create',
                'status_choices': Mission.Status.choices,
                'priority_choices': Mission.Priority.choices,
                'form_data': request.POST,
            })

        # Only staff can create shared missions
        if is_staff_shared and not request.user.is_staff:
            is_staff_shared = False

        # Validate priority and status
        if priority not in dict(Mission.Priority.choices):
            priority = Mission.Priority.MEDIUM
        if status not in dict(Mission.Status.choices):
            status = Mission.Status.PENDING

        due_date = None
        if due_date_str:
            try:
                from datetime import datetime
                due_date = timezone.make_aware(datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M'))
            except (ValueError, TypeError):
                try:
                    from datetime import datetime
                    due_date = timezone.make_aware(datetime.strptime(due_date_str, '%Y-%m-%d'))
                except (ValueError, TypeError):
                    messages.warning(request, 'Invalid due date format, ignoring.')

        mission = Mission.objects.create(
            user=request.user,
            title=title,
            description=description,
            priority=priority,
            status=status,
            category=category,
            due_date=due_date,
            is_staff_shared=is_staff_shared,
        )
        messages.success(request, f'Mission "{mission.title}" created successfully.')
        return redirect('mission_detail', mission_id=mission.id)

    context = {
        'action': 'create',
        'status_choices': Mission.Status.choices,
        'priority_choices': Mission.Priority.choices,
    }
    return render(request, 'missions/mission_form.html', context)


@login_required
def mission_detail(request, mission_id):
    """View mission details."""
    mission = get_object_or_404(Mission, id=mission_id)

    # Check ownership or staff-shared visibility
    if mission.user != request.user and not mission.is_staff_shared:
        messages.error(request, 'You do not have permission to view this mission.')
        return redirect('mission_list')

    return render(request, 'missions/mission_detail.html', {
        'mission': mission,
        'now': timezone.now(),
    })


@login_required
def mission_update(request, mission_id):
    """Update an existing mission."""
    mission = get_object_or_404(Mission, id=mission_id)

    # Only the owner can edit
    if mission.user != request.user:
        messages.error(request, 'You can only edit your own missions.')
        return redirect('mission_list')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if not title:
            messages.error(request, 'Mission title is required.')
            return render(request, 'missions/mission_form.html', {
                'action': 'edit',
                'mission': mission,
                'status_choices': Mission.Status.choices,
                'priority_choices': Mission.Priority.choices,
                'form_data': request.POST,
            })

        mission.title = title
        mission.description = request.POST.get('description', '').strip()
        priority = request.POST.get('priority', mission.priority)
        status = request.POST.get('status', mission.status)
        mission.category = request.POST.get('category', '').strip()

        if priority in dict(Mission.Priority.choices):
            mission.priority = priority
        if status in dict(Mission.Status.choices):
            mission.status = status

        # Staff-shared toggle
        if request.user.is_staff:
            mission.is_staff_shared = request.POST.get('is_staff_shared') == 'on'

        due_date_str = request.POST.get('due_date', '').strip()
        if due_date_str:
            try:
                from datetime import datetime
                mission.due_date = timezone.make_aware(datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M'))
            except (ValueError, TypeError):
                try:
                    from datetime import datetime
                    mission.due_date = timezone.make_aware(datetime.strptime(due_date_str, '%Y-%m-%d'))
                except (ValueError, TypeError):
                    messages.warning(request, 'Invalid due date format, ignoring.')
        else:
            mission.due_date = None

        mission.save()
        messages.success(request, f'Mission "{mission.title}" updated successfully.')
        return redirect('mission_detail', mission_id=mission.id)

    context = {
        'action': 'edit',
        'mission': mission,
        'status_choices': Mission.Status.choices,
        'priority_choices': Mission.Priority.choices,
    }
    return render(request, 'missions/mission_form.html', context)


@login_required
@require_POST
def mission_delete(request, mission_id):
    """Delete a mission (POST only)."""
    mission = get_object_or_404(Mission, id=mission_id)

    if mission.user != request.user:
        messages.error(request, 'You can only delete your own missions.')
        return redirect('mission_list')

    title = mission.title
    mission.delete()
    messages.success(request, f'Mission "{title}" deleted successfully.')
    return redirect('mission_list')


@login_required
@require_POST
def mission_toggle_status(request, mission_id):
    """AJAX endpoint to cycle mission status: pending → in_progress → completed → pending."""
    mission = get_object_or_404(Mission, id=mission_id)

    if mission.user != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Cycle status
    status_cycle = {
        Mission.Status.PENDING: Mission.Status.IN_PROGRESS,
        Mission.Status.IN_PROGRESS: Mission.Status.COMPLETED,
        Mission.Status.COMPLETED: Mission.Status.PENDING,
        Mission.Status.CANCELLED: Mission.Status.PENDING,
    }
    mission.status = status_cycle.get(mission.status, Mission.Status.PENDING)
    mission.save(update_fields=['status', 'updated_at'])

    return JsonResponse({
        'id': mission.id,
        'status': mission.status,
        'status_display': mission.get_status_display(),
    })



def todos(request):
    """Legacy todos view — redirects to mission board for authenticated users, login for guests."""
    if request.user.is_authenticated:
        return redirect('mission_list')
    return redirect('login')


@require_GET
def terms_of_service(request):
    """Easter egg — returns HTTP 418 I'm a Teapot for the Terms of Service page."""
    return render(request, 'terms_of_service.html', status=418)


@require_GET
def privacy_policy(request):
    return render(request, 'privacy_policy.html')
