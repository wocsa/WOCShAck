from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET

from Community.models.reactions import ReactionType, Reaction, ReactionSummary


@login_required
@require_POST
def react(request):
    """Add or remove a reaction on any content object."""
    ct_id = request.POST.get('content_type_id')
    object_id = request.POST.get('object_id', '').strip()
    reaction_type_id = request.POST.get('reaction_type_id')

    try:
        content_type = ContentType.objects.get(id=ct_id)
        reaction_type = ReactionType.objects.get(id=reaction_type_id, is_active=True)
    except (ContentType.DoesNotExist, ReactionType.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid content type or reaction type.'}, status=400)

    with transaction.atomic():
        existing = Reaction.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=object_id,
            reaction_type=reaction_type,
        ).first()

        if existing:
            existing.delete()
            delta = -1
            action = 'removed'
        else:
            Reaction.objects.create(
                user=request.user,
                content_type=content_type,
                object_id=object_id,
                reaction_type=reaction_type,
            )
            delta = 1
            action = 'added'

        summary, _ = ReactionSummary.objects.get_or_create(
            content_type=content_type,
            object_id=object_id,
            reaction_type=reaction_type,
        )
        summary.count = max(0, summary.count + delta)
        summary.save()

    return JsonResponse({
        'action': action,
        'count': summary.count,
        'reaction_type_id': str(reaction_type.id),
    })


@require_GET
def get_reactions(request):
    """Return reaction summaries for a content object."""
    ct_id = request.GET.get('content_type_id')
    object_id = request.GET.get('object_id', '').strip()

    try:
        content_type = ContentType.objects.get(id=ct_id)
    except (ContentType.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid content type.'}, status=400)

    summaries = ReactionSummary.objects.filter(
        content_type=content_type,
        object_id=object_id,
        count__gt=0,
    ).select_related('reaction_type')

    user_reactions = set()
    if request.user.is_authenticated:
        user_reactions = set(
            Reaction.objects.filter(
                user=request.user,
                content_type=content_type,
                object_id=object_id,
            ).values_list('reaction_type_id', flat=True)
        )

    data = [
        {
            'reaction_type_id': str(s.reaction_type.id),
            'emoji': s.reaction_type.emoji,
            'name': s.reaction_type.name,
            'count': s.count,
            'reacted': s.reaction_type.id in user_reactions,
        }
        for s in summaries
    ]
    return JsonResponse({'reactions': data})
