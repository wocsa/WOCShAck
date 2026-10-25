import os
import threading
import time

from django.apps import AppConfig


def _subscription_scheduler():
    """Background thread: process due subscriptions every hour."""
    from django.core.management import call_command
    while True:
        time.sleep(3600)
        try:
            call_command('process_subscriptions', verbosity=0)
        except Exception:
            pass


class DeveloperConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Developer'
    verbose_name = 'Developer Portal'

    def ready(self):
        # RUN_MAIN is set by the runserver reloader in the child (real server) process.
        # This guard prevents the scheduler from starting twice under the reloader,
        # and avoids running it in management-command subprocesses.
        if os.environ.get('RUN_MAIN') != 'true':
            return
        t = threading.Thread(target=_subscription_scheduler, daemon=True, name='subscription-scheduler')
        t.start()
