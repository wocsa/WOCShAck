from django.db import migrations, models


def reassign_removed_event_types(apps, schema_editor):
    """Migrate any existing ctf/hackathon events to meetup before choices are removed."""
    Event = apps.get_model('community_engagement', 'Event')
    Event.objects.filter(event_type__in=['ctf', 'hackathon']).update(event_type='meetup')


def reverse_reassign(apps, schema_editor):
    # Reversing the data migration is not meaningful; events stay as meetup.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('community_engagement', '0013_feedpreferences_show_achievements_and_more'),
    ]

    operations = [
        # Step 1: data migration — reassign removed types to 'meetup'
        migrations.RunPython(reassign_removed_event_types, reverse_reassign),

        # Step 2: remove CTF and HACKATHON from the choices list
        migrations.AlterField(
            model_name='event',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('workshop', 'Workshop'),
                    ('webinar', 'Webinar'),
                    ('meetup', 'Meetup'),
                ],
                default='workshop',
                max_length=10,
            ),
        ),
    ]
