"""
Developer module views — payouts and payment methods.
"""
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST

from .views import developer_required
from .models import DeveloperBalance, Payout


@developer_required
def payout_dashboard(request):
    """Payout overview with balance and recent payouts."""
    balance, _ = DeveloperBalance.objects.get_or_create(developer=request.user)
    recent_payouts = Payout.objects.filter(developer=request.user)[:10]

    context = {
        'balance': balance,
        'recent_payouts': recent_payouts,
    }
    return render(request, 'developer/payouts.html', context)


@developer_required
def request_payout(request):
    """Request a payout of available balance."""
    if request.method == 'POST':
        balance, _ = DeveloperBalance.objects.get_or_create(developer=request.user)

        amount_str = request.POST.get('amount', '0')
        try:
            amount = Decimal(amount_str)
        except (ValueError, ArithmeticError):
            messages.error(request, 'Invalid amount.')
            return redirect('developer_payouts')

        if amount <= 0:
            messages.error(request, 'Amount must be positive.')
            return redirect('developer_payouts')

        if amount > balance.available:
            messages.error(request, 'Insufficient available balance.')
            return redirect('developer_payouts')

        Payout.objects.create(
            developer=request.user,
            amount=amount,
            fee=Decimal('0.00'),
            net_amount=amount,
            method=None,
            status=Payout.Status.PENDING,
        )

        # Deduct from available, add to pending (will be resolved by admin)
        balance.available -= amount
        balance.pending += amount
        balance.save()

        messages.success(request, f'Payout of {amount} NS requested.')
        return redirect('developer_payout_history')

    return redirect('developer_payouts')


@developer_required
def payout_history(request):
    """View payout history."""
    payouts = Payout.objects.filter(developer=request.user)
    context = {'payouts': payouts}
    return render(request, 'developer/payout_history.html', context)


@developer_required
def payout_methods(request):
    """View and manage payout methods."""
    methods = PayoutMethod.objects.filter(developer=request.user)
    context = {'methods': methods}
    return render(request, 'developer/payout_methods.html', context)


@developer_required
def add_payout_method(request):
    """Add a new payout method."""
    if request.method == 'POST':
        method_type = request.POST.get('method_type', '')
        details = escape(request.POST.get('details', '')[:500])

        if method_type not in dict(PayoutMethod.MethodType.choices):
            messages.error(request, 'Invalid payout method type.')
            return redirect('developer_payout_methods')

        # Set as primary if it's the first method
        is_first = not PayoutMethod.objects.filter(developer=request.user).exists()

        PayoutMethod.objects.create(
            developer=request.user,
            method_type=method_type,
            details_text=details,
            is_primary=is_first,
        )

        messages.success(request, 'Payout method added.')
        return redirect('developer_payout_methods')

    context = {'method_types': PayoutMethod.MethodType.choices}
    return render(request, 'developer/add_payout_method.html', context)


@developer_required
@require_POST
def delete_payout_method(request, method_id):
    """Delete a payout method."""
    method = get_object_or_404(PayoutMethod, id=method_id, developer=request.user)
    was_primary = method.is_primary
    method.delete()

    # If deleted method was primary, promote another
    if was_primary:
        next_method = PayoutMethod.objects.filter(developer=request.user).first()
        if next_method:
            next_method.is_primary = True
            next_method.save()

    messages.success(request, 'Payout method removed.')
    return redirect('developer_payout_methods')
