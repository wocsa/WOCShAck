"""
Community moderation views — staff only.
All views require @login_required + is_staff check.
"""
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from Community.models.content import BlogPost, Tutorial, ShowcaseItem, Event
from Community.models.communication import MessageReport

ITEMS_PER_PAGE = 20


def _staff_required(request):
    """Return a redirect response if the user is not staff, else None."""
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect("index")
    return None


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def moderation_dashboard(request):
    guard = _staff_required(request)
    if guard:
        return guard

    context = {
        "total_blog_posts":      BlogPost.objects.count(),
        "open_reports":          MessageReport.objects.filter(status="pending").count(),
        "total_showcases":       ShowcaseItem.objects.count(),
        "pending_showcases":     ShowcaseItem.objects.filter(is_approved=False).count(),
        "unresolved_tutorials":  Tutorial.objects.filter(is_published=False).count(),
    }
    return render(request, "community/admin/dashboard.html", context)


# ── Blog ──────────────────────────────────────────────────────────────────────

@login_required
def blog_list(request):
    guard = _staff_required(request)
    if guard:
        return guard

    qs = BlogPost.objects.select_related("author", "category").order_by("-created_at")

    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(title__icontains=search) | Q(author__username__icontains=search)
        )

    published = request.GET.get("published", "all")
    if published == "yes":
        qs = qs.filter(status=BlogPost.Status.PUBLISHED)
    elif published == "no":
        qs = qs.exclude(status=BlogPost.Status.PUBLISHED)

    paginator = Paginator(qs, ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "community/admin/blog_list.html", {
        "page_obj":  page_obj,
        "search":    search,
        "published": published,
    })


@login_required
@require_POST
def blog_delete(request, slug):
    guard = _staff_required(request)
    if guard:
        return guard

    post = get_object_or_404(BlogPost, slug=slug)
    title = post.title
    post.delete()
    messages.success(request, f'Blog post "{title}" has been deleted.')
    return redirect("community:admin_blog_list")


# ── Tutorials ─────────────────────────────────────────────────────────────────

@login_required
def tutorial_list(request):
    guard = _staff_required(request)
    if guard:
        return guard

    qs = Tutorial.objects.select_related("author").order_by("-created_at")

    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(title__icontains=search) | Q(author__username__icontains=search)
        )

    published = request.GET.get("published", "all")
    if published == "yes":
        qs = qs.filter(is_published=True)
    elif published == "no":
        qs = qs.filter(is_published=False)

    paginator = Paginator(qs, ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "community/admin/tutorial_list.html", {
        "page_obj":  page_obj,
        "search":    search,
        "published": published,
    })


@login_required
@require_POST
def tutorial_delete(request, slug):
    guard = _staff_required(request)
    if guard:
        return guard

    tutorial = get_object_or_404(Tutorial, slug=slug)
    title = tutorial.title
    tutorial.delete()
    messages.success(request, f'Tutorial "{title}" has been deleted.')
    return redirect("community:admin_tutorial_list")


# ── Showcase ──────────────────────────────────────────────────────────────────

@login_required
def showcase_list(request):
    guard = _staff_required(request)
    if guard:
        return guard

    qs = ShowcaseItem.objects.select_related("author").order_by("-created_at")

    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(title__icontains=search) | Q(author__username__icontains=search)
        )

    paginator = Paginator(qs, ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "community/admin/showcase_list.html", {
        "page_obj": page_obj,
        "search":   search,
    })


@login_required
@require_POST
def showcase_action(request):
    guard = _staff_required(request)
    if guard:
        return guard

    action  = request.POST.get("action")
    item_id = request.POST.get("item_id")
    item = get_object_or_404(ShowcaseItem, id=item_id)

    if action == "feature":
        item.is_featured = True
        item.save(update_fields=["is_featured"])
        messages.success(request, f'"{item.title}" is now featured.')
    elif action == "unfeature":
        item.is_featured = False
        item.save(update_fields=["is_featured"])
        messages.success(request, f'"{item.title}" has been unfeatured.')
    elif action == "approve":
        item.is_approved = True
        item.save(update_fields=["is_approved"])
        messages.success(request, f'"{item.title}" has been approved.')
    elif action == "remove":
        title = item.title
        item.delete()
        messages.success(request, f'Showcase item "{title}" has been removed.')
    elif action == "generate_gif":
        try:
            from Api.gif_utils import generate_gif_for_css
            result = generate_gif_for_css(item.demo_css, str(item.id), body_html=item.demo_html or None)
            if result:
                gif_file, gif_name = result
                item.preview_gif.save(gif_name, gif_file, save=True)
                messages.success(request, f'GIF preview generated for "{item.title}".')
            else:
                messages.error(request, f'GIF generation failed for "{item.title}" (Selenium/Chrome may be unavailable).')
        except Exception as e:
            messages.error(request, f'GIF generation error for "{item.title}": {e}')
    else:
        messages.error(request, "Unknown action.")

    return redirect("community:admin_showcase_list")


# ── Message Reports ───────────────────────────────────────────────────────────

@login_required
def message_reports(request):
    guard = _staff_required(request)
    if guard:
        return guard

    qs = (
        MessageReport.objects
        .select_related("reporter", "message", "message__sender")
        .exclude(status="resolved")
        .order_by("-created_at")
    )

    paginator = Paginator(qs, ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "community/admin/message_reports.html", {
        "page_obj": page_obj,
    })


@login_required
@require_POST
def message_report_resolve(request, report_id):
    guard = _staff_required(request)
    if guard:
        return guard

    report = get_object_or_404(MessageReport, id=report_id)
    report.status = "resolved"
    report.save(update_fields=["status"])
    messages.success(request, "Report marked as resolved.")
    return redirect("community:admin_message_reports")


# ── Events ────────────────────────────────────────────────────────────────────

@login_required
def event_list(request):
    guard = _staff_required(request)
    if guard:
        return guard

    qs = Event.objects.select_related("organizer").order_by("-created_at")

    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(title__icontains=search) | Q(organizer__username__icontains=search)
        )

    paginator = Paginator(qs, ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "community/admin/event_list.html", {
        "page_obj": page_obj,
        "search":   search,
    })


@login_required
@require_POST
def event_cancel(request, event_id):
    guard = _staff_required(request)
    if guard:
        return guard

    event = get_object_or_404(Event, id=event_id)
    event.status = Event.Status.CANCELLED
    event.save(update_fields=["status"])
    messages.success(request, f'Event "{event.title}" has been cancelled.')
    return redirect("community:admin_event_list")

