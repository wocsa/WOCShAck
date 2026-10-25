import os
import traceback

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponseForbidden, HttpResponseServerError, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from .models import BankCard, Transaction
from .Utils.external_calls import (
    backend_connection,
    check_backend_connectivity,
    create_backend_session,
    make_connection_with_sid,
    build_query,
)


# ---------------------------------------------------------------------------
# Internal HTTP client (debugging/admin tool)
# ---------------------------------------------------------------------------

def http_client(request, cmd, sid, secret):
    if secret != "Q5HxkocADCyPG39FBrqLvN6rtu3nSBxP":
        return HttpResponseForbidden("Unauthorized query")
    try:
        if sid == "none":
            new_sid = create_backend_session()
            return JsonResponse({'sid': new_sid})
        else:
            cli, rsp = make_connection_with_sid(sid)
            if cli is None:
                return HttpResponseServerError("An error occurred: Server down")
            elif rsp is False:
                return JsonResponse({'error': 'bad sid'})
            else:
                rsp, rst = build_query(cmd, sid)
                if rsp:
                    result = cli._send_with_retry(rst)
                    if result is None:
                        return JsonResponse({'error': 'No response from server'}, safe=False)
                    return JsonResponse(result, safe=False)
                else:
                    return JsonResponse({
                        'error': "badly formed query",
                        'debug_cmd': cmd,
                        'debug_cmd_split': cmd.split("+")
                    })
    except Exception as e:
        return HttpResponseServerError(f"An error occurred: {str(e)}\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Banking admin page (staff only)
# ---------------------------------------------------------------------------

@login_required
def banking_admin(request):
    """
    Banking system admin page - staff only.
    Shows system status and banking backend connectivity.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    # Check banking backend connectivity
    is_connected = check_backend_connectivity()
    backend_status = "Connected" if is_connected else "Connection Failed"
    client_status = "Connected" if is_connected else "Disconnected"

    # Count Django bank-related data
    total_users = User.objects.count()
    total_cards = BankCard.objects.count()
    total_transactions = Transaction.objects.count()
    active_cards = BankCard.objects.filter(status='active').count()

    context = {
        'backend_status': backend_status,
        'client_status': client_status,
        'total_users': total_users,
        'total_cards': total_cards,
        'active_cards': active_cards,
        'total_transactions': total_transactions,
    }

    return render(request, 'account/admin.html', context)


# ---------------------------------------------------------------------------
# Admin: Accounts list
# ---------------------------------------------------------------------------

@login_required
@require_GET
def admin_accounts(request):
    """
    List all bank accounts.
    Shows Django users cross-referenced with backend account data.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    users = User.objects.prefetch_related('bank_cards').order_by('username')

    # Try to fetch backend account data
    backend_accounts = {}
    backend_error = None
    try:
        with backend_connection() as (cli, sid):
            if cli is not None:
                response = cli.get_users(sid)
                if isinstance(response, dict) and response.get('success'):
                    users_data = response.get('users', {})
                    if isinstance(users_data, dict):
                        for uid, acc in users_data.items():
                            if isinstance(acc, dict):
                                backend_accounts[str(uid)] = acc
                    elif isinstance(users_data, list):
                        for acc in users_data:
                            if isinstance(acc, dict):
                                uid = str(acc.get('id', acc.get('user_id', '')))
                                backend_accounts[uid] = acc
            else:
                backend_error = "Banking backend is unreachable."
    except Exception:
        backend_error = "Failed to query the banking backend."

    # Build combined account list: a banking account exists if either the
    # Django user has a BankCard, OR the backend has a record for that user.
    account_list = []
    seen_uids = set()
    for u in users:
        cards = u.bank_cards.all()
        backend_data = backend_accounts.get(str(u.id), {})
        if not cards.exists() and not backend_data:
            continue
        seen_uids.add(str(u.id))
        account_list.append({
            'user': u,
            'card_count': cards.count(),
            'active_cards': cards.filter(status='active').count(),
            'balance': backend_data.get('balance'),
            'account_number': backend_data.get('account_number', backend_data.get('payment_number', '')),
        })

    # Include backend accounts whose Django user couldn't be matched above
    # (e.g. accounts created on the backend without a corresponding Django user
    # or where the Django user has no cards yet).
    for uid, backend_data in backend_accounts.items():
        if uid in seen_uids:
            continue
        try:
            u = User.objects.get(pk=int(uid))
        except (User.DoesNotExist, ValueError, TypeError):
            u = None
        account_list.append({
            'user': u,
            'backend_user_id': uid,
            'card_count': u.bank_cards.count() if u else 0,
            'active_cards': u.bank_cards.filter(status='active').count() if u else 0,
            'balance': backend_data.get('balance'),
            'account_number': backend_data.get('account_number', backend_data.get('payment_number', '')),
        })

    paginator = Paginator(account_list, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'account/admin_accounts.html', {
        'page_obj': page_obj,
        'total_accounts': len(account_list),
        'backend_error': backend_error,
    })


# ---------------------------------------------------------------------------
# Admin: Transactions list
# ---------------------------------------------------------------------------

@login_required
@require_GET
def admin_transactions(request):
    """
    List all transactions (audit log) with filters.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    qs = Transaction.objects.select_related('user', 'card').order_by('-created_at')

    # Filters
    type_filter = request.GET.get('type', '').strip()
    status_filter = request.GET.get('status', '').strip()
    search_q = request.GET.get('q', '').strip()

    if type_filter in ('transfer_out', 'transfer_in', 'payment', 'refund', 'deposit'):
        qs = qs.filter(transaction_type=type_filter)
    if status_filter in ('pending', 'completed', 'failed'):
        qs = qs.filter(status=status_filter)
    if search_q:
        from django.db.models import Q
        qs = qs.filter(
            Q(user__username__icontains=search_q) |
            Q(counterpart_payment_number__icontains=search_q) |
            Q(counterpart_label__icontains=search_q) |
            Q(note__icontains=search_q)
        )

    paginator = Paginator(qs, 30)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'account/admin_transactions.html', {
        'page_obj': page_obj,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'search_q': search_q,
        'total_transactions': qs.count(),
    })


# ---------------------------------------------------------------------------
# Admin: Banking Client Apps List
# ---------------------------------------------------------------------------

@login_required
@require_GET
def admin_client_list(request):
    """
    List all available banking client apps in the static folder.
    Staff-only access.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    apps_dir = os.path.join(settings.BASE_DIR, 'Bank', 'static', 'apps')
    apps = []
    if os.path.exists(apps_dir):
        # List all files in the apps directory
        apps = [f for f in os.listdir(apps_dir) if os.path.isfile(os.path.join(apps_dir, f))]
        # Sort apps alphabetically
        apps.sort()

    return render(request, 'account/admin_client_list.html', {
        'apps': apps,
    })


# ---------------------------------------------------------------------------
# Download Banking Client App (staff only)
# ---------------------------------------------------------------------------

@login_required
@require_GET
def download_banking_client(request, app_name=None):
    """
    Serve the VRC Internal Banking Client app for download.
    Staff-only access to the Qt/C++ banking client application.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('index')

    # If app_name is provided, serve from the static apps folder
    if app_name:
        app_path = os.path.join(settings.BASE_DIR, 'Bank', 'static', 'apps', app_name)
        if not os.path.exists(app_path):
            raise Http404("Banking client application not found.")
        
        try:
            return FileResponse(
                open(app_path, 'rb'),
                as_attachment=True,
                filename=app_name
            )
        except Exception as e:
            messages.error(request, f"Failed to serve the application: {str(e)}")
            return redirect('banking_admin_apps')

    # Fallback to the original logic if no app_name (legacy support)
    # Path to the banking client app in VRC_INTERNAL_BANKING_CLIENT/build
    # Use the project root to find the banking client
    project_root = settings.BASE_DIR.parent.parent
    app_path = os.path.join(project_root, 'VRC_INTERNAL_BANKING_CLIENT', 'build', 'appVRC_BANK_CLIENT.app')

    # Verify the app exists
    if not os.path.exists(app_path):
        messages.error(request, "Banking client application not found. Please ensure the VRC client is built.")
        return redirect('banking_admin')

    # For macOS .app bundles, create a tar.gz archive on-the-fly
    import tarfile
    import tempfile

    # Create a temporary tar.gz archive of the .app bundle
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz')
    try:
        with tarfile.open(temp_file.name, 'w:gz') as tar:
            tar.add(app_path, arcname='VRC_Banking_Client.app')
        
        # Open and return the archive
        temp_file.seek(0)
        response = FileResponse(
            open(temp_file.name, 'rb'),
            as_attachment=True,
            filename='VRC_Banking_Client.tar.gz'
        )
        response['Content-Type'] = 'application/gzip'
        
        # Note: The temp file will be cleaned up by the OS eventually
        # For production, consider using a background task to clean up
        return response
    except Exception as e:
        messages.error(request, f"Failed to create download archive: {str(e)}")
        return redirect('banking_admin')
