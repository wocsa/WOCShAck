# Merge migration to resolve conflicting 0019 migrations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('community_engagement', '0019_remove_css_battles'),
        ('community_engagement', '0019_showcaseitem_preview_gif'),
    ]

    operations = [
    ]
