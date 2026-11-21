from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from .views import api_success, api_error, api_auth_required, paginate_queryset
from Advertisement.models import Advertisement, AdImpression, AdClick

@require_http_methods(["GET"])
def serve_ad_view(request):
    """
    Serve a random active ad for a given zone.
    Query params: zone (str)
    """
    zone = request.GET.get('zone')
    if not zone:
        return api_error("Missing 'zone' query parameter.", status=400)
        
    ad = Advertisement.get_active_for_zone(zone)
    if not ad:
        return api_error("No active ads available for this zone.", status=404)
        
    # Return ad details (excluding sensitive info like budget)
    return api_success({
        "ad": {
            "id": str(ad.id),
            "title": ad.title,
            "body_html": ad.body_html,
            "image_url": ad.image_url,
            "target_url": ad.target_url,
            "placement_zone": ad.placement_zone,
        }
    })

@require_http_methods(["POST"])
def impression_view(request, ad_id):
    """
    Register an ad impression.
    """
    ad = get_object_or_404(Advertisement, id=ad_id)
    zone = request.GET.get('zone', 'unknown')
    
    AdImpression.objects.create(
        advertisement=ad,
        user=request.user if request.user.is_authenticated else None,
        ip_address=request.META.get('REMOTE_ADDR'),
        zone=zone
    )
    return api_success({"message": "Impression recorded"})

@require_http_methods(["POST"])
def click_view(request, ad_id):
    """
    Register an ad click.
    """
    ad = get_object_or_404(Advertisement, id=ad_id)
    
    AdClick.objects.create(
        advertisement=ad,
        user=request.user if request.user.is_authenticated else None,
        ip_address=request.META.get('REMOTE_ADDR')
    )
    return api_success({"message": "Click recorded", "target_url": ad.target_url})

@require_http_methods(["GET"])
@api_auth_required
def campaigns_view(request):
    """
    List active campaigns for the current advertiser.
    """
    ads = Advertisement.objects.filter(advertiser=request.user).order_by('-created_at')
    paginated = paginate_queryset(ads, request)
    
    data = []
    for ad in paginated['items']:
        data.append({
            "id": str(ad.id),
            "title": ad.title,
            "status": ad.status,
            "budget_neuros": float(ad.budget_neuros),
            "spent_neuros": float(ad.spent_neuros),
            "impressions_count": ad.impressions.count(),
            "clicks_count": ad.clicks.count(),
            "start_date": ad.start_date.isoformat(),
            "end_date": ad.end_date.isoformat() if ad.end_date else None,
        })
        
    return api_success({
        "campaigns": data,
        "pagination": paginated['pagination']
    })

import json
from django.db.models import Count, Sum
from django.utils import timezone

@require_http_methods(["GET", "POST"])
def ads_list_view(request):
    """
    GET /api/ads/ : List active advertisements (filterable by placement_zone)
    POST /api/ads/ : Create a new advertisement (authenticated advertisers)
    """
    if request.method == "GET":
        zone = request.GET.get('placement_zone')
        ads = Advertisement.objects.filter(status=Advertisement.Status.ACTIVE)
        if zone:
            ads = ads.filter(placement_zone=zone)
        ads = ads.order_by('-start_date')
        
        paginated = paginate_queryset(ads, request)
        data = []
        for ad in paginated['items']:
            data.append({
                "id": str(ad.id),
                "title": ad.title,
                "placement_zone": ad.placement_zone,
                "image_url": ad.image_url,
                "target_url": ad.target_url,
                "advertiser": ad.advertiser.username,
            })
        return api_success({"advertisements": data, "pagination": paginated['pagination']})

    elif request.method == "POST":
        if not request.user.is_authenticated:
            return api_error("Authentication required", status=401)
        try:
            payload = json.loads(request.body)
            title = payload.get("title")
            body = payload.get("body")
            target_url = payload.get("target_url")
            placement_zone = payload.get("placement_zone")
            budget_neuros = payload.get("budget_neuros", 0)
        except:
            return api_error("Invalid payload", status=400)
            
        if not all([title, body, target_url, placement_zone]):
            return api_error("Missing required fields", status=400)
            
        ad = Advertisement.objects.create(
            title=title,
            body=body,
            target_url=target_url,
            placement_zone=placement_zone,
            advertiser=request.user,
            budget_neuros=budget_neuros,
            status=Advertisement.Status.PENDING
        )
        return api_success({"message": "Advertisement created", "id": str(ad.id)}, status=201)

@require_http_methods(["GET", "PATCH"])
def ad_detail_view(request, ad_id):
    ad = get_object_or_404(Advertisement, id=ad_id)
    
    if request.method == "GET":
        return api_success({
            "id": str(ad.id),
            "title": ad.title,
            "body": ad.body,
            "body_html": ad.body_html,
            "placement_zone": ad.placement_zone,
            "image_url": ad.image_url,
            "target_url": ad.target_url,
            "advertiser": ad.advertiser.username,
            "status": ad.status
        })
        
    elif request.method == "PATCH":
        if not request.user.is_authenticated or request.user != ad.advertiser:
            return api_error("Not authorized", status=403)
        if ad.status not in [Advertisement.Status.PENDING, Advertisement.Status.REJECTED]:
            return api_error("Cannot edit advertisement unless pending or rejected", status=400)
            
        try:
            payload = json.loads(request.body)
            if "title" in payload:
                ad.title = payload["title"]
            if "body" in payload:
                ad.body = payload["body"]
            if "target_url" in payload:
                ad.target_url = payload["target_url"]
            ad.status = Advertisement.Status.PENDING # Re-submit
            ad.save()
            return api_success({"message": "Advertisement updated"})
        except:
            return api_error("Invalid payload", status=400)

@require_http_methods(["POST"])
@api_auth_required
def activate_ad_view(request, ad_id):
    ad = get_object_or_404(Advertisement, id=ad_id, advertiser=request.user)
    if ad.status != Advertisement.Status.APPROVED:
        return api_error("Advertisement must be approved before activation", status=400)
    
    # Deduct Neuros here (mocked for API)
    ad.status = Advertisement.Status.ACTIVE
    ad.start_date = timezone.now()
    ad.save()
    return api_success({"message": "Advertisement activated"})

@require_http_methods(["GET"])
@api_auth_required
def dashboard_view(request):
    ads = Advertisement.objects.filter(advertiser=request.user)
    total_impressions = sum(ad.impressions.count() for ad in ads)
    total_clicks = sum(ad.clicks.count() for ad in ads)
    spent = sum(ad.spent_neuros for ad in ads)
    return api_success({
        "total_campaigns": ads.count(),
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "total_spent_neuros": float(spent),
        "ctr": (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    })

@require_http_methods(["GET"])
@api_auth_required
def ad_stats_view(request, ad_id):
    ad = get_object_or_404(Advertisement, id=ad_id, advertiser=request.user)
    imp = ad.impressions.count()
    clk = ad.clicks.count()
    return api_success({
        "id": str(ad.id),
        "impressions": imp,
        "clicks": clk,
        "ctr": (clk / imp * 100) if imp > 0 else 0
    })

@require_http_methods(["GET"])
@api_auth_required
def admin_pending_view(request):
    if not request.user.is_staff:
        return api_error("Admin only", status=403)
    ads = Advertisement.objects.filter(status=Advertisement.Status.PENDING).order_by('-created_at')
    paginated = paginate_queryset(ads, request)
    data = [{"id": str(a.id), "title": a.title, "advertiser": a.advertiser.username} for a in paginated['items']]
    return api_success({"pending_ads": data, "pagination": paginated['pagination']})

@require_http_methods(["POST"])
@api_auth_required
def admin_approve_view(request, ad_id):
    if not request.user.is_staff:
        return api_error("Admin only", status=403)
    ad = get_object_or_404(Advertisement, id=ad_id)
    ad.status = Advertisement.Status.APPROVED
    ad.reviewed_by = request.user
    ad.reviewed_at = timezone.now()
    ad.save()
    return api_success({"message": "Advertisement approved"})

@require_http_methods(["POST"])
@api_auth_required
def admin_reject_view(request, ad_id):
    if not request.user.is_staff:
        return api_error("Admin only", status=403)
    try:
        payload = json.loads(request.body)
        reason = payload.get("reason", "")
    except:
        reason = ""
    ad = get_object_or_404(Advertisement, id=ad_id)
    ad.status = Advertisement.Status.REJECTED
    ad.rejection_reason = reason
    ad.reviewed_by = request.user
    ad.reviewed_at = timezone.now()
    ad.save()
    return api_success({"message": "Advertisement rejected"})
