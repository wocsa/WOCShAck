"""
Developer module views — documentation portal.
"""
from django.shortcuts import render

from .views import developer_required


@developer_required
def docs_home(request):
    """Developer documentation home — getting started guide."""
    return render(request, 'developer/docs/home.html')


@developer_required
def docs_api(request):
    """API endpoint reference documentation."""
    return render(request, 'developer/docs/api.html')


@developer_required
def docs_webhooks(request):
    """Webhook event types and signature verification docs."""
    return render(request, 'developer/docs/webhooks.html')


@developer_required
def docs_examples(request):
    """Code examples and integration guides."""
    return render(request, 'developer/docs/examples.html')
