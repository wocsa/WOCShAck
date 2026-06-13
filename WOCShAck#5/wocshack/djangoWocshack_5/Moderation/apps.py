from django.apps import AppConfig


class ModerationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Moderation'
    verbose_name = 'Moderation & Trust Safety'

    def ready(self):
        import Moderation.signals  # noqa: F401
