from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Bank', '0003_transaction_card'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # Add new fields to BankCard
        migrations.AddField(
            model_name='bankcard',
            name='weekly_limit',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='bankcard',
            name='monthly_limit',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='bankcard',
            name='transaction_alerts_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='bankcard',
            name='replacement_reason',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='bankcard',
            name='replaced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='bankcard',
            name='replaced_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='replaces_card',
                to='Bank.bankcard',
            ),
        ),
        # Expand status field to accommodate 'pending_replacement'
        migrations.AlterField(
            model_name='bankcard',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', 'Active'),
                    ('frozen', 'Frozen'),
                    ('cancelled', 'Cancelled'),
                    ('pending_replacement', 'Pending Replacement'),
                ],
                default='active',
                max_length=25,
            ),
        ),
        # Create Beneficiary model
        migrations.CreateModel(
            name='Beneficiary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=100)),
                ('account_number', models.CharField(max_length=16)),
                ('display_name', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='beneficiaries',
                    to='auth.user',
                )),
            ],
            options={
                'ordering': ['label'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='beneficiary',
            unique_together={('user', 'account_number')},
        ),
    ]
