"""
Migration: Rename app from V_R_C to Todo.
Renames the DB table and updates django_content_type entries.
"""
from django.db import migrations


def update_content_types(apps, schema_editor):
    """Update the app_label in django_content_type from V_R_C to Todo."""
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(app_label='V_R_C').update(app_label='Todo')


def revert_content_types(apps, schema_editor):
    """Revert the app_label in django_content_type from Todo to V_R_C."""
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(app_label='Todo').update(app_label='V_R_C')


class Migration(migrations.Migration):

    dependencies = [
        ('Todo', '0002_rename_todoitem_to_mission'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='mission',
            table='Todo_mission',
        ),
        migrations.RunPython(update_content_types, revert_content_types),
    ]
