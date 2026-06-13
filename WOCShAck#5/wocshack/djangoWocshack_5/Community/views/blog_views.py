from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.utils.text import slugify
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import F, Count

from Community.models.content import BlogCategory, BlogPost, BlogComment
from Community.functions import is_content_creator
from Community.views.moderation_views import _staff_required
from Community.services.feed_service import create_feed_item
from Community.models.feed import ActivityFeedItem


def blog_list(request):
    category_slug = request.GET.get('category')
    posts = BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED).select_related('author', 'category')
    if category_slug:
        posts = posts.filter(category__slug=category_slug)

    paginator = Paginator(posts, 9)
    page = paginator.get_page(request.GET.get('page'))
    categories = BlogCategory.objects.all()
    active_category = BlogCategory.objects.filter(slug=category_slug).first() if category_slug else None

    my_drafts = []
    if request.user.is_authenticated and is_content_creator(request.user):
        my_drafts = list(
            BlogPost.objects.filter(author=request.user, status=BlogPost.Status.DRAFT)
                            .order_by('-created_at')
        )

    return render(request, 'community/blog/list.html', {
        'page_obj': page,
        'categories': categories,
        'active_category': active_category,
        'my_drafts': my_drafts,
    })


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost, slug=slug)
    if post.status != BlogPost.Status.PUBLISHED:
        # Draft/archived posts only visible to the author or staff
        if not request.user.is_authenticated or (post.author != request.user and not request.user.is_staff):
            raise Http404
    BlogPost.objects.filter(pk=post.pk).update(view_count=F('view_count') + 1)
    post.refresh_from_db(fields=['view_count'])

    top_comments = post.comments.filter(
        parent=None, status=BlogComment.Status.APPROVED
    ).prefetch_related('replies')

    return render(request, 'community/blog/detail.html', {
        'post': post,
        'comments': top_comments,
    })


@login_required
@require_POST
def blog_comment_add(request, slug):
    post = get_object_or_404(BlogPost, slug=slug, status=BlogPost.Status.PUBLISHED)
    if not post.allow_comments:
        messages.error(request, "Comments are disabled for this post.")
        return redirect('community:blog_detail', slug=slug)

    content = request.POST.get('content', '').strip()
    if not content:
        messages.error(request, "Comment cannot be empty.")
        return redirect('community:blog_detail', slug=slug)

    parent_id = request.POST.get('parent_id')
    parent = None
    if parent_id:
        parent = BlogComment.objects.filter(id=parent_id, post=post).first()

    status = BlogComment.Status.APPROVED
    BlogComment.objects.create(post=post, author=request.user, content=content[:2000], parent=parent, status=status)

    messages.success(request, "Comment posted.")
    return redirect('community:blog_detail', slug=slug)


@login_required
def blog_create(request):
    if not is_content_creator(request.user):
        messages.error(request, "Access denied.")
        return redirect('community:blog_list')

    categories = BlogCategory.objects.all()
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        category_id = request.POST.get('category') or None
        tags = request.POST.get('tags', '').strip()
        status = request.POST.get('status', BlogPost.Status.DRAFT)
        allow_comments = request.POST.get('allow_comments') == 'on'
        featured_image = request.FILES.get('featured_image')

        # Non-staff content creators: allow draft/published/archived, no featured/pinned
        if request.user.is_staff:
            is_featured = request.POST.get('is_featured') == 'on'
            is_pinned = request.POST.get('is_pinned') == 'on'
        else:
            is_featured = False
            is_pinned = False

        if title and content:
            slug = slugify(title)
            base_slug = slug
            counter = 1
            while BlogPost.objects.filter(slug=slug).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1

            post = BlogPost.objects.create(
                title=title,
                slug=slug,
                content=content,
                author=request.user,
                category_id=category_id,
                tags=tags,
                featured_image=featured_image,
                status=status,
                is_featured=is_featured,
                is_pinned=is_pinned,
                allow_comments=allow_comments,
            )
            if status == BlogPost.Status.PUBLISHED:
                post.published_at = timezone.now()
                post.save(update_fields=['published_at'])
                try:
                    create_feed_item(
                        user=request.user,
                        action_type=ActivityFeedItem.ActionType.BLOG_POST_CREATED,
                        title=f'Published a new article: {post.title}',
                        description=post.content[:200] if post.content else '',
                        icon='📝',
                        related_object_id=str(post.id),
                    )
                except Exception:
                    pass
            messages.success(request, f"Blog post \"{post.title}\" created successfully.")
            return redirect('community:blog_detail', slug=post.slug)
        else:
            messages.error(request, "Title and content are required.")

    return render(request, 'community/blog/create_edit.html', {
        'categories': categories,
        'action': 'Create',
        'post': None,
    })


@login_required
def blog_edit(request, slug):
    post = get_object_or_404(BlogPost, slug=slug)

    # Allow edit if staff/admin, or author who is a content creator
    if not request.user.is_staff and not (post.author == request.user and is_content_creator(request.user)):
        messages.error(request, "Access denied.")
        return redirect('community:blog_list')

    categories = BlogCategory.objects.all()
    if request.method == 'POST':
        post.title = request.POST.get('title', post.title).strip()
        post.content = request.POST.get('content', post.content).strip()
        post.category_id = request.POST.get('category') or None
        post.tags = request.POST.get('tags', '').strip()
        new_status = request.POST.get('status', post.status)
        featured_image = request.FILES.get('featured_image')

        # Non-staff content creators: allow status changes, no featured/pinned
        if new_status == BlogPost.Status.PUBLISHED and post.status != BlogPost.Status.PUBLISHED:
            post.published_at = timezone.now()
            try:
                create_feed_item(
                    user=post.author,
                    action_type=ActivityFeedItem.ActionType.BLOG_POST_CREATED,
                    title=f'Published a new article: {post.title}',
                    description=post.content[:200] if post.content else '',
                    icon='📝',
                    related_object_id=str(post.id),
                )
            except Exception:
                pass
        post.status = new_status
        if request.user.is_staff:
            post.is_featured = request.POST.get('is_featured') == 'on'
            post.is_pinned = request.POST.get('is_pinned') == 'on'

        post.allow_comments = request.POST.get('allow_comments') == 'on'
        if featured_image:
            post.featured_image = featured_image
        post.save()
        messages.success(request, f"Blog post \"{post.title}\" updated successfully.")
        return redirect('community:blog_detail', slug=post.slug)

    return render(request, 'community/blog/create_edit.html', {
        'categories': categories,
        'action': 'Edit',
        'post': post,
    })


@login_required
@require_POST
def blog_delete(request, slug):
    post = get_object_or_404(BlogPost, slug=slug)

    # Allow delete if staff/admin, or author who is a content creator
    if not request.user.is_staff and not (post.author == request.user and is_content_creator(request.user)):
        messages.error(request, "Access denied.")
        return redirect('community:blog_list')

    title = post.title
    post.delete()
    messages.success(request, f"Blog post \"{title}\" deleted.")
    return redirect('community:blog_list')


# ── Blog Category Admin Views (Staff Only) ────────────────────────────────────

@login_required
def category_list(request):
    guard = _staff_required(request)
    if guard:
        return guard
    categories = BlogCategory.objects.annotate(post_count=Count('posts')).order_by('name')
    return render(request, 'community/admin/category_list.html', {'categories': categories})


@login_required
def category_create(request):
    guard = _staff_required(request)
    if guard:
        return guard
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip() or slugify(name)
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, "Name is required.")
        elif BlogCategory.objects.filter(name=name).exists():
            messages.error(request, "A category with that name already exists.")
        elif BlogCategory.objects.filter(slug=slug).exists():
            messages.error(request, "A category with that slug already exists.")
        else:
            BlogCategory.objects.create(name=name, slug=slug, description=description)
            messages.success(request, "Category created.")
            return redirect('community:category_list')
    return render(request, 'community/admin/category_create_edit.html', {'action': 'Create'})


@login_required
def category_edit(request, slug):
    guard = _staff_required(request)
    if guard:
        return guard
    category = get_object_or_404(BlogCategory, slug=slug)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        new_slug = request.POST.get('slug', '').strip() or slugify(name)
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, "Name is required.")
        elif BlogCategory.objects.filter(name=name).exclude(pk=category.pk).exists():
            messages.error(request, "A category with that name already exists.")
        elif BlogCategory.objects.filter(slug=new_slug).exclude(pk=category.pk).exists():
            messages.error(request, "A category with that slug already exists.")
        else:
            category.name = name
            category.slug = new_slug
            category.description = description
            category.save()
            messages.success(request, "Category updated.")
            return redirect('community:category_list')
    return render(request, 'community/admin/category_create_edit.html', {'category': category, 'action': 'Edit'})


@login_required
def category_delete(request, slug):
    guard = _staff_required(request)
    if guard:
        return guard
    category = get_object_or_404(BlogCategory, slug=slug)
    if request.method == 'POST':
        category.delete()
        messages.success(request, "Category deleted. Posts have been unlinked.")
        return redirect('community:category_list')
    return render(request, 'community/admin/category_delete.html', {'category': category})
