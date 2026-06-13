from .models import Advertisement, AdImpression


def ads(request):
    """
    Inject all active advertisements into every template context and log
    one impression per ad per page view.
    """
    active_ads = Advertisement.get_all_active()

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

    for ad in active_ads:
        AdImpression.objects.create(
            advertisement=ad,
            user=request.user if request.user.is_authenticated else None,
            ip_address=ip,
            zone=ad.placement_zone,
        )

    return {'ads': active_ads}
