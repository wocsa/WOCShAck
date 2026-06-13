# Generated migration for issue #107

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('community_engagement', '0018_alter_showcaseitem_is_approved_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='showcaseitem',
            name='preview_gif',
            field=models.ImageField(blank=True, help_text='Animated GIF preview of the CSS creation', null=True, upload_to='showcase/previews/'),
        ),
    ]
