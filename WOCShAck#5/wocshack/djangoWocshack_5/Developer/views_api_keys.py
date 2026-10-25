"""
Developer module views — API key management.
"""
import secrets
import hashlib

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST

from .views import developer_required
from .models import ApiKey, ApiKeyUsage


def _generate_api_key():
    """Generate a secure random API key."""
    return 'vrc_' + secrets.token_hex(32)


def _hash_key(key):
    """Hash an API key for secure storage."""
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


@developer_required
def api_key_list(request):
    """List all API keys."""
    keys = ApiKey.objects.filter(developer=request.user)
    # Pop the newly created key from session (shown once, then gone)
    new_api_key = request.session.pop('new_api_key', None)
    context = {'api_keys': keys, 'new_api_key': new_api_key}
    return render(request, 'developer/api_keys.html', context)


@developer_required
def create_api_key(request):
    """Create a new API key."""
    if request.method == 'POST':
        name = escape(request.POST.get('name', '')[:200])
        if not name:
            messages.error(request, 'Key name is required.')
            return redirect('developer_api_keys')

        scopes_raw = request.POST.get('scopes', 'read')
        scopes = [s.strip() for s in scopes_raw.split(',') if s.strip()]

        rate_per_min = request.POST.get('rate_limit_per_minute', '60')
        rate_per_day = request.POST.get('rate_limit_per_day', '5000')
        try:
            rate_per_min = int(rate_per_min)
            rate_per_day = int(rate_per_day)
        except ValueError:
            rate_per_min = 60
            rate_per_day = 5000

        expires_days = request.POST.get('expires_days', '')
        expires_at = None
        if expires_days:
            try:
                expires_at = timezone.now() + timezone.timedelta(days=int(expires_days))
            except ValueError:
                pass

        raw_key = _generate_api_key()
        key_hash = _hash_key(raw_key)
        key_prefix = raw_key[:8]

        ApiKey.objects.create(
            developer=request.user,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes,
            rate_limit_per_minute=rate_per_min,
            rate_limit_per_day=rate_per_day,
            expires_at=expires_at,
        )

        # Store key in session so it can be displayed once on the next page load
        request.session['new_api_key'] = raw_key
        messages.success(request, 'API key created. Copy it now — it will not be shown again.')
        return redirect('developer_api_keys')

    return render(request, 'developer/api_keys.html', {'api_keys': ApiKey.objects.filter(developer=request.user)})


@developer_required
@require_POST
def delete_api_key(request, key_id):
    """Delete an API key."""
    key = get_object_or_404(ApiKey, id=key_id, developer=request.user)
    key.delete()
    messages.success(request, 'API key deleted.')
    return redirect('developer_api_keys')


@developer_required
@require_POST
def regenerate_api_key(request, key_id):
    """Regenerate an API key (new key, same settings)."""
    key = get_object_or_404(ApiKey, id=key_id, developer=request.user)

    raw_key = _generate_api_key()
    key.key_hash = _hash_key(raw_key)
    key.key_prefix = raw_key[:8]
    key.save()

    request.session['new_api_key'] = raw_key
    messages.success(request, 'API key regenerated. Copy it now — it will not be shown again.')
    return redirect('developer_api_keys')


@developer_required
def api_key_usage(request, key_id):
    """View usage stats for an API key."""
    key = get_object_or_404(ApiKey, id=key_id, developer=request.user)
    usage = ApiKeyUsage.objects.filter(api_key=key)[:100]
    context = {'api_key': key, 'usage': usage}
    return render(request, 'developer/api_key_usage.html', context)
