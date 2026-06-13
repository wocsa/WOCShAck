"""
Developer module views — CSS editor, projects, versions, and templates.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.utils.html import escape
from django.views.decorators.http import require_POST

from .views import developer_required
from .models import CssProject, CssVersion, CssTemplate
from .Utils.plan_limits import get_css_project_limit_error
from Api.models import Css as ApiCss
from Api.gif_utils import generate_gif_for_css


# =============================================================================
# EDITOR
# =============================================================================

@developer_required
def editor(request):
    """Full-page CSS editor with CodeMirror and live preview."""
    project_id = request.GET.get('project')
    css_id = request.GET.get('css')
    project = None
    version = None
    api_css = None
    edit_mode = None

    if project_id:
        project = get_object_or_404(CssProject, id=project_id, developer=request.user)
        version = project.current_version
        edit_mode = 'project'
    elif css_id:
        api_css = get_object_or_404(ApiCss, id=css_id, creator=request.user)
        edit_mode = 'api_css'

    projects = CssProject.objects.filter(developer=request.user).exclude(status=CssProject.Status.PUBLISHED)
    api_css_files = ApiCss.objects.filter(creator=request.user)

    context = {
        'project': project,
        'version': version,
        'projects': projects,
        'api_css_files': api_css_files,
        'api_css': api_css,
        'edit_mode': edit_mode,
    }
    return render(request, 'developer/editor.html', context)


@developer_required
@require_POST
def save_api_css(request, css_id):
    """Save CSS content for a published Api.Css item and regenerate its preview GIF (AJAX endpoint)."""
    css_obj = get_object_or_404(ApiCss, id=css_id, creator=request.user)

    css_content = request.POST.get('css_content', '')
    html_template = request.POST.get('html_template')
    
    css_obj.css_content = css_content
    if html_template is not None:
        css_obj.html_template = html_template
    css_obj.save()

    # Regenerate preview GIF in the same request (~3s)
    result = generate_gif_for_css(css_content, str(css_obj.id), body_html=css_obj.html_template)
    if result:
        content_file, filename = result
        css_obj.preview_gif.save(filename, content_file, save=True)

    return JsonResponse({'status': 'success', 'message': 'Saved.'})


# =============================================================================
# PROJECTS
# =============================================================================

@developer_required
def project_list(request):
    """List all projects for the developer."""
    projects = CssProject.objects.filter(developer=request.user).select_related('developer')
    context = {'projects': projects}
    return render(request, 'developer/projects.html', context)


@developer_required
def create_project(request):
    """Create a new CSS project."""
    templates = CssTemplate.objects.all()

    if request.method == 'POST':
        name = escape(request.POST.get('name', '')[:200])
        description = escape(request.POST.get('description', '')[:2000])
        template_id = request.POST.get('template_id', '')

        if not name:
            messages.error(request, 'Project name is required.')
            return render(request, 'developer/create_project.html', {'templates': templates})

        limit_error = get_css_project_limit_error(request.user)
        if limit_error:
            messages.error(request, limit_error)
            return render(request, 'developer/create_project.html', {'templates': templates})

        with transaction.atomic():
            project = CssProject.objects.create(
                developer=request.user,
                name=name,
                description=description,
            )

            # Initialize from template if selected
            css_content = ''
            html_template = '<div class="loader"></div>'
            if template_id:
                try:
                    tmpl = CssTemplate.objects.get(id=template_id)
                    css_content = tmpl.css_content
                    html_template = tmpl.html_template
                except CssTemplate.DoesNotExist:
                    pass

            CssVersion.objects.create(
                project=project,
                version_number='0.1.0',
                css_content=css_content,
                html_template=html_template,
                commit_message='Initial version',
                is_current=True,
            )

        messages.success(request, f'Project "{name}" created!')
        return redirect('developer_editor') if not template_id else redirect('developer_edit_project', project_id=project.id)

    context = {'templates': templates}
    return render(request, 'developer/create_project.html', context)


@developer_required
def edit_project(request, project_id):
    """Edit a CSS project (name, description)."""
    project = get_object_or_404(CssProject, id=project_id, developer=request.user)

    if request.method == 'POST':
        project.name = escape(request.POST.get('name', '')[:200])
        project.description = escape(request.POST.get('description', '')[:2000])
        project.save()
        messages.success(request, 'Project updated.')
        return redirect('developer_projects')

    versions = project.versions.all()[:20]
    context = {'project': project, 'versions': versions}
    return render(request, 'developer/edit_project.html', context)


@developer_required
@require_POST
def save_project(request, project_id):
    """Save CSS content for a project (AJAX endpoint)."""
    project = get_object_or_404(CssProject, id=project_id, developer=request.user)

    css_content = request.POST.get('css_content', '')
    html_template = request.POST.get('html_template', '')

    version = project.current_version
    if version:
        version.css_content = css_content
        version.html_template = html_template
        version.save()
        return JsonResponse({'status': 'success', 'message': 'Saved.'})

    return JsonResponse({'status': 'error', 'message': 'No current version found.'}, status=400)


@developer_required
@require_POST
def delete_project(request, project_id):
    """Delete a CSS project."""
    project = get_object_or_404(CssProject, id=project_id, developer=request.user)
    project_name = project.name
    project.delete()
    messages.success(request, f'Project "{project_name}" deleted.')
    return redirect('developer_projects')


# =============================================================================
# VERSIONS
# =============================================================================

@developer_required
def version_list(request, project_id):
    """List all versions for a project."""
    project = get_object_or_404(CssProject, id=project_id, developer=request.user)
    versions = project.versions.all()
    context = {'project': project, 'versions': versions}
    return render(request, 'developer/versions.html', context)


@developer_required
@require_POST
def create_version(request, project_id):
    """Create a new version of a CSS project."""
    project = get_object_or_404(CssProject, id=project_id, developer=request.user)

    version_number = escape(request.POST.get('version_number', '')[:20])
    commit_message = escape(request.POST.get('commit_message', '')[:500])
    css_content = request.POST.get('css_content', '')
    html_template = request.POST.get('html_template', '')

    if not version_number:
        messages.error(request, 'Version number is required.')
        return redirect('developer_versions', project_id=project.id)

    with transaction.atomic():
        # Unset current on all existing versions
        project.versions.filter(is_current=True).update(is_current=False)

        CssVersion.objects.create(
            project=project,
            version_number=version_number,
            css_content=css_content,
            html_template=html_template,
            commit_message=commit_message,
            is_current=True,
        )

    messages.success(request, f'Version {version_number} created.')
    return redirect('developer_versions', project_id=project.id)


# =============================================================================
# TEMPLATES
# =============================================================================

@developer_required
def template_list(request):
    """Browse starter templates."""
    templates = CssTemplate.objects.all()
    context = {'templates': templates}
    return render(request, 'developer/templates_list.html', context)
