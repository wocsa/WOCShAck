from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.db.models import F
from django.core.paginator import Paginator

from Community.models.content import ShowcaseItem, ShowcaseVote
from Community.services.feed_service import create_feed_item
from Community.models.feed import ActivityFeedItem


def showcase_list(request):
    sort = request.GET.get('sort', 'votes')
    category = request.GET.get('category')

    items = ShowcaseItem.objects.filter(is_approved=True).select_related('author')
    if category:
        items = items.filter(category=category)

    if sort == 'new':
        items = items.order_by('-created_at')
    else:
        items = items.order_by('-is_featured', '-vote_score', '-created_at')

    paginator = Paginator(items, 12)
    page = paginator.get_page(request.GET.get('page'))

    user_votes = {}
    if request.user.is_authenticated:
        for v in ShowcaseVote.objects.filter(user=request.user, item__in=[i.pk for i in page.object_list]):
            user_votes[str(v.item_id)] = v.vote_type

    return render(request, 'community/showcase/list.html', {
        'page_obj': page,
        'categories': ShowcaseItem.Category.choices,
        'active_category': category,
        'sort': sort,
        'user_votes': user_votes,
    })


def showcase_detail(request, item_id):
    item = get_object_or_404(ShowcaseItem, id=item_id, is_approved=True)
    ShowcaseItem.objects.filter(pk=item.pk).update(view_count=F('view_count') + 1)
    item.refresh_from_db(fields=['view_count'])

    user_vote = None
    if request.user.is_authenticated:
        vote = ShowcaseVote.objects.filter(user=request.user, item=item).first()
        user_vote = vote.vote_type if vote else None

    return render(request, 'community/showcase/detail.html', {
        'item': item,
        'user_vote': user_vote,
    })


@login_required
@require_POST
def showcase_vote(request, item_id):
    item = get_object_or_404(ShowcaseItem, id=item_id, is_approved=True)
    vote_type = request.POST.get('vote_type')
    if vote_type not in (ShowcaseVote.VoteType.UPVOTE, ShowcaseVote.VoteType.DOWNVOTE):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Invalid vote type'}, status=400)
        messages.error(request, "Invalid vote type.")
        return redirect('community:showcase_detail', item_id=item_id)

    with transaction.atomic():
        existing = ShowcaseVote.objects.filter(user=request.user, item=item).first()
        if existing:
            if existing.vote_type == vote_type:
                # Cancel vote
                delta = -1 if vote_type == ShowcaseVote.VoteType.UPVOTE else 1
                existing.delete()
                ShowcaseItem.objects.filter(pk=item.pk).update(vote_score=F('vote_score') + delta)
                new_vote = None
            else:
                # Switch vote
                delta = 2 if vote_type == ShowcaseVote.VoteType.UPVOTE else -2
                existing.vote_type = vote_type
                existing.save(update_fields=['vote_type'])
                ShowcaseItem.objects.filter(pk=item.pk).update(vote_score=F('vote_score') + delta)
                new_vote = vote_type
        else:
            delta = 1 if vote_type == ShowcaseVote.VoteType.UPVOTE else -1
            ShowcaseVote.objects.create(user=request.user, item=item, vote_type=vote_type)
            ShowcaseItem.objects.filter(pk=item.pk).update(vote_score=F('vote_score') + delta)
            new_vote = vote_type

    item.refresh_from_db(fields=['vote_score'])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'vote_score': item.vote_score, 'user_vote': new_vote})

    messages.success(request, "Vote recorded.")
    return redirect('community:showcase_detail', item_id=item_id)


@login_required
def showcase_submit(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        demo_css = request.POST.get('demo_css', '').strip()
        category = request.POST.get('category', ShowcaseItem.Category.OTHER)

        if title and demo_css:
            item = ShowcaseItem.objects.create(
                title=title,
                description=description,
                author=request.user,
                demo_css=demo_css,
                category=category,
                is_approved=False,
            )

            try:
                from Api.gif_utils import generate_gif_for_css
                result = generate_gif_for_css(item.demo_css, str(item.id))
                if result:
                    gif_file, gif_name = result
                    item.preview_gif.save(gif_name, gif_file, save=True)
            except Exception:
                pass

            try:
                create_feed_item(
                    user=request.user,
                    action_type=ActivityFeedItem.ActionType.SHOWCASE_ADDED,
                    title=f'Submitted a showcase: {item.title}',
                    description=item.description[:200] if item.description else '',
                    icon='🎨',
                    related_object_id=str(item.id),
                )
            except Exception:
                pass
            messages.success(request, "Your creation has been submitted! It will appear after moderation approval.")
            return redirect('community:showcase_list')
        else:
            messages.error(request, "Title and CSS code are required.")

    return render(request, 'community/showcase/submit.html', {
        'categories': ShowcaseItem.Category.choices,
    })
