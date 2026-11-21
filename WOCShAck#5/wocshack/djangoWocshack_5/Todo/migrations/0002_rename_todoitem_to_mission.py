"""
Migration: Rename TodoItem to Mission and add new fields.
Migrates completed=True data to status='completed'.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def migrate_completed_to_status(apps, schema_editor):
    """Convert old `completed` boolean to new `status` field."""
    Mission = apps.get_model('Todo', 'Mission')
    Mission.objects.filter(status='').update(status='pending')


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Todo', '0001_initial'),
    ]

    operations = [
        # 1. Rename model
        migrations.RenameModel(
            old_name='TodoItem',
            new_name='Mission',
        ),
        # 2. Add new fields
        migrations.AddField(
            model_name='mission',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='mission',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('in_progress', 'In Progress'),
                    ('completed', 'Completed'),
                    ('cancelled', 'Cancelled'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='mission',
            name='priority',
            field=models.CharField(
                choices=[
                    ('low', 'Low'),
                    ('medium', 'Medium'),
                    ('high', 'High'),
                    ('critical', 'Critical'),
                ],
                default='medium',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='mission',
            name='category',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='mission',
            name='due_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mission',
            name='is_staff_shared',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='mission',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='mission',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='mission',
            name='user',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='missions',
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
        # 3. Enlarge title field
        migrations.AlterField(
            model_name='mission',
            name='title',
            field=models.CharField(max_length=200),
        ),
        # 4. Migrate completed → status
        migrations.RunPython(migrate_completed_to_status, migrations.RunPython.noop),
        # 5. Remove old completed field
        migrations.RemoveField(
            model_name='mission',
            name='completed',
        ),
        # 6. Set default ordering
        migrations.AlterModelOptions(
            name='mission',
            options={'ordering': ['-created_at']},
        ),
    ]
