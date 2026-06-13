"""
Data migration: delete ActivityFeedItem rows with stale gamification action_types
(level_up, achievement_unlocked, streak_milestone, daily_reward) that were
removed from the ActionType enum in migration 0015.

CharField choices are DB-advisory only, so existing rows with stale values
remain valid at the DB level after 0015. This migration cleans them up.
"""
from django.db import migrations

STALE_TYPES = ('level_up', 'achievement_unlocked', 'streak_milestone', 'daily_reward')


def delete_stale_feed_items(apps, schema_editor):
    ActivityFeedItem = apps.get_model('community_engagement', 'ActivityFeedItem')
    deleted, _ = ActivityFeedItem.objects.filter(action_type__in=STALE_TYPES).delete()
    if deleted:
        print(f'  Deleted {deleted} stale gamification feed item(s).')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('community_engagement', '0015_remove_gamification_add_content_feed_fields'),
    ]

    operations = [
        migrations.RunPython(delete_stale_feed_items, reverse_code=noop),
    ]
