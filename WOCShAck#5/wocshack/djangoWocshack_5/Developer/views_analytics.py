"""
Developer module views — analytics dashboards.
"""
import csv
import json
from decimal import Decimal

from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Sum, Count, Avg, F
from django.utils import timezone

from .views import developer_required
from .models import SaleAnalytics, CustomerAnalytics, CssListing


def _parse_days(request, default=30):
    """Safely parse the 'days' query parameter."""
    try:
        days = int(request.GET.get('days', default))
        return max(1, min(days, 365))
    except (ValueError, TypeError):
        return default


@developer_required
def analytics_dashboard(request):
    """Main analytics dashboard with charts and summary."""
    user = request.user
    days = _parse_days(request)
    start_date = timezone.now().date() - timezone.timedelta(days=days)

    analytics = SaleAnalytics.objects.filter(
        developer=user,
        date__gte=start_date,
    ).order_by('date')

    # Summary stats
    totals = analytics.aggregate(
        total_revenue=Sum('revenue'),
        total_sales=Sum('sales_count'),
        total_customers=Sum('unique_customers'),
        total_views=Sum('page_views'),
        avg_conversion=Avg('conversion_rate'),
        avg_order_value=Avg('avg_order_value'),
    )

    # Chart data
    chart_labels = [a.date.isoformat() for a in analytics]
    chart_revenue = [float(a.revenue) for a in analytics]
    chart_sales = [a.sales_count for a in analytics]
    chart_views = [a.page_views for a in analytics]

    context = {
        'analytics': analytics,
        'totals': totals,
        'days': days,
        'chart_labels': json.dumps(chart_labels),
        'chart_revenue': json.dumps(chart_revenue),
        'chart_sales': json.dumps(chart_sales),
        'chart_views': json.dumps(chart_views),
    }
    return render(request, 'developer/analytics.html', context)


@developer_required
def revenue_analytics(request):
    """Detailed revenue analytics."""
    user = request.user
    days = _parse_days(request)
    start_date = timezone.now().date() - timezone.timedelta(days=days)

    analytics = SaleAnalytics.objects.filter(
        developer=user,
        date__gte=start_date,
    ).order_by('-date')

    totals = analytics.aggregate(
        total_revenue=Sum('revenue'),
        total_sales=Sum('sales_count'),
        avg_order_value=Avg('avg_order_value'),
    )

    context = {
        'analytics': analytics,
        'totals': totals,
        'days': days,
    }
    return render(request, 'developer/analytics.html', context)


@developer_required
def product_analytics(request):
    """Product performance analytics."""
    user = request.user
    listings = CssListing.objects.filter(
        developer=user,
        status='published',
    ).annotate(
        tier_count=Count('pricing_tiers'),
    )

    context = {'listings': listings}
    return render(request, 'developer/analytics.html', context)


@developer_required
def customer_analytics(request):
    """Customer analytics breakdown."""
    user = request.user
    customers = CustomerAnalytics.objects.filter(
        developer=user,
    ).select_related('customer').order_by('-lifetime_value')[:50]

    totals = CustomerAnalytics.objects.filter(developer=user).aggregate(
        total_customers=Count('id'),
        avg_ltv=Avg('lifetime_value'),
        total_purchases=Sum('purchase_count'),
    )

    context = {
        'customers': customers,
        'totals': totals,
    }
    return render(request, 'developer/analytics.html', context)


@developer_required
def export_analytics(request):
    """Export analytics data as CSV."""
    user = request.user
    days = _parse_days(request, default=90)
    start_date = timezone.now().date() - timezone.timedelta(days=days)

    analytics = SaleAnalytics.objects.filter(
        developer=user,
        date__gte=start_date,
    ).order_by('date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="analytics_{user.username}_{days}d.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Date', 'Revenue', 'Sales Count', 'Unique Customers',
        'Page Views', 'Cart Additions', 'Conversion Rate', 'Avg Order Value'
    ])
    for a in analytics:
        writer.writerow([
            a.date, a.revenue, a.sales_count, a.unique_customers,
            a.page_views, a.cart_additions, a.conversion_rate, a.avg_order_value
        ])

    return response
