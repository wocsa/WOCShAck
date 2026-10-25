from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.text import slugify
from django.core.paginator import Paginator

from Community.models.content import Tutorial, TutorialStep, TutorialProgress, TutorialQuiz
from Community.forms import TutorialStepFormSet
from Community.functions import is_content_creator
from Community.services.feed_service import create_feed_item
from Community.models.feed import ActivityFeedItem


def tutorial_list(request):
    difficulty = request.GET.get('difficulty')
    category = request.GET.get('category')
    tutorials = Tutorial.objects.filter(is_published=True).select_related('author')

    if difficulty:
        tutorials = tutorials.filter(difficulty=difficulty)
    if category:
        tutorials = tutorials.filter(category__iexact=category)

    paginator = Paginator(tutorials, 12)
    page = paginator.get_page(request.GET.get('page'))

    user_progress = {}
    if request.user.is_authenticated:
        for p in TutorialProgress.objects.filter(user=request.user, tutorial__in=[t.pk for t in page.object_list]):
            user_progress[str(p.tutorial_id)] = p

    categories = Tutorial.objects.filter(is_published=True).values_list('category', flat=True).distinct().exclude(category='')

    my_drafts = []
    if request.user.is_authenticated and is_content_creator(request.user):
        my_drafts = list(
            Tutorial.objects.filter(author=request.user, is_published=False)
                            .order_by('-created_at')
        )

    return render(request, 'community/tutorials/list.html', {
        'page_obj': page,
        'difficulties': Tutorial.Difficulty.choices,
        'active_difficulty': difficulty,
        'categories': sorted(categories),
        'active_category': category,
        'user_progress': user_progress,
        'my_drafts': my_drafts,
    })


def tutorial_detail(request, slug):
    tutorial = get_object_or_404(Tutorial, slug=slug)
    if not tutorial.is_published:
        # Unpublished tutorials only visible to the author or staff
        if not request.user.is_authenticated or (tutorial.author != request.user and not request.user.is_staff):
            raise Http404

    if tutorial.is_premium and not (request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'is_developer', False))):
        return render(request, 'community/tutorials/premium_locked.html', {'tutorial': tutorial})

    steps = tutorial.steps.all()
    progress = None
    if request.user.is_authenticated:
        progress, _ = TutorialProgress.objects.get_or_create(user=request.user, tutorial=tutorial)

    return render(request, 'community/tutorials/detail.html', {
        'tutorial': tutorial,
        'steps': steps,
        'progress': progress,
    })


@login_required
def tutorial_step(request, slug, step_order):
    tutorial = get_object_or_404(Tutorial, slug=slug)
    if not tutorial.is_published:
        # Unpublished tutorials only visible to the author or staff
        if not request.user.is_authenticated or (tutorial.author != request.user and not request.user.is_staff):
            raise Http404

    step = get_object_or_404(TutorialStep, tutorial=tutorial, order=step_order)
    quiz = step.quizzes.first()

    progress, _ = TutorialProgress.objects.get_or_create(user=request.user, tutorial=tutorial)
    if not progress.current_step or progress.current_step.order < step.order:
        progress.current_step = step
        progress.save(update_fields=['current_step'])

    total_steps = tutorial.steps.count()
    prev_step = TutorialStep.objects.filter(tutorial=tutorial, order=step_order - 1).first()
    next_step = TutorialStep.objects.filter(tutorial=tutorial, order=step_order + 1).first()

    return render(request, 'community/tutorials/step.html', {
        'tutorial': tutorial,
        'step': step,
        'quiz': quiz,
        'progress': progress,
        'prev_step': prev_step,
        'next_step': next_step,
        'total_steps': total_steps,
        'step_number': step_order,
    })


@login_required
@require_POST
def tutorial_quiz_submit(request, slug, step_order):
    tutorial = get_object_or_404(Tutorial, slug=slug)
    if not tutorial.is_published:
        # Unpublished tutorials only visible to the author or staff
        if not request.user.is_authenticated or (tutorial.author != request.user and not request.user.is_staff):
            raise Http404

    step = get_object_or_404(TutorialStep, tutorial=tutorial, order=step_order)
    quiz = get_object_or_404(TutorialQuiz, step=step)

    answer = request.POST.get('answer', '').strip()
    correct = answer.lower() == quiz.correct_answer.lower()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'correct': correct, 'hint': quiz.hint if not correct else ''})

    if correct:
        messages.success(request, "Correct answer!")
    else:
        messages.error(request, "Incorrect answer. Try again!")
    return redirect('community:tutorial_step', slug=slug, step_order=step_order)


@login_required
@require_POST
def tutorial_complete(request, slug):
    tutorial = get_object_or_404(Tutorial, slug=slug)
    if not tutorial.is_published:
        # Unpublished tutorials only visible to the author or staff
        if not request.user.is_authenticated or (tutorial.author != request.user and not request.user.is_staff):
            raise Http404

    progress, _ = TutorialProgress.objects.get_or_create(user=request.user, tutorial=tutorial)
    if not progress.completed:
        progress.completed = True
        progress.completed_at = timezone.now()
        progress.save(update_fields=['completed', 'completed_at'])

        messages.success(request, f"Congratulations! You completed \"{tutorial.title}\".")
    else:
        messages.info(request, "You have already completed this tutorial.")
    return redirect('community:tutorial_detail', slug=slug)


@login_required
def tutorial_create(request):
    if not is_content_creator(request.user):
        messages.error(request, "You don't have permission to create tutorials.")
        return redirect('community:tutorial_list')

    step_formset = TutorialStepFormSet(
        request.POST or None,
        prefix='steps',
    )

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        difficulty = request.POST.get('difficulty', Tutorial.Difficulty.BEGINNER)
        estimated_minutes = request.POST.get('estimated_minutes', '15').strip()
        prerequisites = request.POST.get('prerequisites', '').strip()
        category = request.POST.get('category', '').strip()
        is_premium = request.POST.get('is_premium') == 'on'
        is_published = request.POST.get('is_published') == 'on'

        if not title or not description:
            messages.error(request, "Title and description are required.")
        elif not step_formset.is_valid():
            messages.error(request, "Please fix the errors in the tutorial steps.")
        else:
            # Validate difficulty
            if difficulty not in dict(Tutorial.Difficulty.choices):
                difficulty = Tutorial.Difficulty.BEGINNER

            # Generate unique slug
            slug = slugify(title)
            base_slug = slug
            counter = 1
            while Tutorial.objects.filter(slug=slug).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1

            try:
                mins = int(estimated_minutes)
                if mins < 1:
                    mins = 15
            except (ValueError, TypeError):
                mins = 15

            tutorial = Tutorial.objects.create(
                title=title,
                slug=slug,
                description=description,
                author=request.user,
                difficulty=difficulty,
                estimated_minutes=mins,
                prerequisites=prerequisites,
                category=category,
                is_premium=is_premium,
                is_published=is_published,
            )

            # Save tutorial steps
            step_formset.instance = tutorial
            step_formset.save()

            if tutorial.is_published:
                try:
                    create_feed_item(
                        user=request.user,
                        action_type=ActivityFeedItem.ActionType.TUTORIAL_PUBLISHED,
                        title=f'Published a tutorial: {tutorial.title}',
                        description=tutorial.description[:200] if tutorial.description else '',
                        icon='📚',
                        related_object_id=str(tutorial.id),
                    )
                except Exception:
                    pass
            messages.success(request, f'Tutorial "{tutorial.title}" created successfully.')
            return redirect('community:tutorial_detail', slug=tutorial.slug)

    return render(request, 'community/tutorials/create_edit.html', {
        'action': 'Create',
        'tutorial': None,
        'difficulties': Tutorial.Difficulty.choices,
        'step_formset': step_formset,
    })


@login_required
def tutorial_edit(request, slug):
    tutorial = get_object_or_404(Tutorial, slug=slug)

    # Allow staff/admin, or author who is a content creator
    if not (request.user.is_staff or (tutorial.author == request.user and is_content_creator(request.user))):
        messages.error(request, "You don't have permission to edit this tutorial.")
        return redirect('community:tutorial_detail', slug=tutorial.slug)

    step_formset = TutorialStepFormSet(
        request.POST or None,
        instance=tutorial,
        prefix='steps',
    )

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        difficulty = request.POST.get('difficulty', Tutorial.Difficulty.BEGINNER)
        estimated_minutes = request.POST.get('estimated_minutes', '15').strip()
        prerequisites = request.POST.get('prerequisites', '').strip()
        category = request.POST.get('category', '').strip()
        is_premium = request.POST.get('is_premium') == 'on'
        is_published = request.POST.get('is_published') == 'on'

        if not title or not description:
            messages.error(request, "Title and description are required.")
        elif not step_formset.is_valid():
            messages.error(request, "Please fix the errors in the tutorial steps.")
        else:
            # Validate difficulty
            if difficulty not in dict(Tutorial.Difficulty.choices):
                difficulty = Tutorial.Difficulty.BEGINNER

            # Regenerate slug only if title changed
            if title != tutorial.title:
                new_slug = slugify(title)
                base_slug = new_slug
                counter = 1
                while Tutorial.objects.filter(slug=new_slug).exclude(pk=tutorial.pk).exists():
                    new_slug = f'{base_slug}-{counter}'
                    counter += 1
                tutorial.slug = new_slug

            try:
                mins = int(estimated_minutes)
                if mins < 1:
                    mins = 15
            except (ValueError, TypeError):
                mins = 15

            tutorial.title = title
            tutorial.description = description
            tutorial.difficulty = difficulty
            tutorial.estimated_minutes = mins
            tutorial.prerequisites = prerequisites
            tutorial.category = category
            tutorial.is_premium = is_premium
            tutorial.is_published = is_published
            tutorial.save()

            # Save tutorial steps
            step_formset.save()

            messages.success(request, f'Tutorial "{tutorial.title}" updated successfully.')
            return redirect('community:tutorial_detail', slug=tutorial.slug)

    return render(request, 'community/tutorials/create_edit.html', {
        'action': 'Edit',
        'tutorial': tutorial,
        'difficulties': Tutorial.Difficulty.choices,
        'step_formset': step_formset,
    })


@login_required
@require_POST
def tutorial_delete(request, slug):
    tutorial = get_object_or_404(Tutorial, slug=slug)

    # Allow staff/admin, or author who is a content creator
    if not (request.user.is_staff or (tutorial.author == request.user and is_content_creator(request.user))):
        messages.error(request, "You don't have permission to delete this tutorial.")
        return redirect('community:tutorial_detail', slug=tutorial.slug)

    title = tutorial.title
    tutorial.delete()
    messages.success(request, f'Tutorial "{title}" has been deleted.')
    return redirect('community:tutorial_list')
