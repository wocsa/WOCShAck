from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Bank', '0002_bankcard_transaction'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='card',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='transactions',
                to='Bank.bankcard',
            ),
        ),
    ]
