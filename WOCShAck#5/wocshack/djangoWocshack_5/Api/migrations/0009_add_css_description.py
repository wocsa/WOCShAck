from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Api', '0008_css_html_template'),
    ]

    operations = [
        migrations.AddField(
            model_name='css',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
    ]
