from django.apps import AppConfig


class CommunityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "Community"
    label = "community_engagement"  # Preserve existing DB table names

    def ready(self):
        import Community.signals