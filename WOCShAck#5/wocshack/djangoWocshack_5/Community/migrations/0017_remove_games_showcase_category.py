"""
Data + schema migration: remove the 'games' category from ShowcaseItem.

Step 1 (data) — reassign any existing ShowcaseItem rows with category='games'
to 'other' so they remain valid after the choices are narrowed.

Step 2 (schema) — alter the field choices to drop 'games'.
"""
from django.db import migrations, models


def migrate_games_to_other(apps, schema_editor):
    ShowcaseItem = apps.get_model('community_engagement', 'ShowcaseItem')
    updated = ShowcaseItem.objects.filter(category='games').update(category='other')
    if updated:
        print(f'  Reassigned {updated} ShowcaseItem(s) from "games" to "other".')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('community_engagement', '0016_delete_stale_gamification_feed_items'),
    ]

    operations = [
        migrations.RunPython(migrate_games_to_other, reverse_code=noop),
        migrations.AlterField(
            model_name='showcaseitem',
            name='category',
            field=models.CharField(
                choices=[
                    ('loaders',    'Loaders & Spinners'),
                    ('buttons',    'Buttons & Interactions'),
                    ('cards',      'Cards & Layouts'),
                    ('art',        'Pure CSS Art'),
                    ('animations', 'Animations'),
                    ('typography', 'Typography'),
                    ('dark_mode',  'Dark Mode Designs'),
                    ('other',      'Other'),
                ],
                default='other',
                max_length=20,
            ),
        ),
    ]
