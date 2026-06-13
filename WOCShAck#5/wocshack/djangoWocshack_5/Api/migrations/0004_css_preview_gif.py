# Generated migration for adding preview_gif field to Css model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Api', '0003_preserve_logs_on_css_delete'),
    ]

    operations = [
        migrations.AddField(
            model_name='css',
            name='preview_gif',
            field=models.ImageField(
                blank=True,
                help_text='Animated GIF preview of the CSS loader, generated server-side to prevent source code scraping.',
                null=True,
                upload_to='css_previews/',
            ),
        ),
    ]
