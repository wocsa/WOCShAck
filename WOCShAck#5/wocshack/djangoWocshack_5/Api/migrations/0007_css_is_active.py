from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Api', '0006_alter_apikey_options_remove_apikey_key_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='css',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
