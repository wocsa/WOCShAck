from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Developer', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='payoutmethod',
            old_name='details_encrypted',
            new_name='details_text',
        ),
        migrations.AlterField(
            model_name='payoutmethod',
            name='details_text',
            field=models.TextField(blank=True, help_text='Payout method details (e.g. email, account number).'),
        ),
    ]
