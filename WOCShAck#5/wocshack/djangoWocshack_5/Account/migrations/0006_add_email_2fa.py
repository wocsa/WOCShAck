
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Account', '0005_add_login_history_backup_codes_sessions'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='email_2fa_enabled',
            field=models.BooleanField(default=False),
        ),
    ]
