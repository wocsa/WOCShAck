"""
Developer module views — CSS tool endpoints.
"""
import json

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .views import developer_required
from .Utils.css_tools import minify_css, beautify_css, validate_css, prefix_css


@developer_required
def tools_page(request):
    """Standalone CSS tools page."""
    return render(request, 'developer/tools.html')


@developer_required
@require_POST
def minify_css_view(request):
    """Minify CSS input."""
    css_input = request.POST.get('css', '')
    if not css_input:
        return JsonResponse({'error': 'No CSS provided.'}, status=400)
    result = minify_css(css_input)
    return JsonResponse({
        'result': result,
        'original_size': len(css_input),
        'minified_size': len(result),
        'savings': round((1 - len(result) / max(len(css_input), 1)) * 100, 1),
    })


@developer_required
@require_POST
def beautify_css_view(request):
    """Beautify CSS input."""
    css_input = request.POST.get('css', '')
    if not css_input:
        return JsonResponse({'error': 'No CSS provided.'}, status=400)
    result = beautify_css(css_input)
    return JsonResponse({'result': result})


@developer_required
@require_POST
def validate_css_view(request):
    """Validate CSS input."""
    css_input = request.POST.get('css', '')
    if not css_input:
        return JsonResponse({'error': 'No CSS provided.'}, status=400)
    result = validate_css(css_input)
    return JsonResponse(result)


@developer_required
@require_POST
def prefix_css_view(request):
    """Add vendor prefixes to CSS input."""
    css_input = request.POST.get('css', '')
    if not css_input:
        return JsonResponse({'error': 'No CSS provided.'}, status=400)
    result = prefix_css(css_input)
    return JsonResponse({'result': result})
