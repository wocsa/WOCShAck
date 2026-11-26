from django.db import migrations


class Migration(migrations.Migration):
    """Merge migration resolving dual 0011 branches."""

    dependencies = [
        ('community_engagement', '0011_notificationpreference_moderation_and_more'),
        ('community_engagement', '0011_remove_userachievement_achievement_and_more'),
    ]

    operations = [
    ]
