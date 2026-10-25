from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Bank', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='BankCard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('card_type', models.CharField(choices=[('virtual', 'Virtual'), ('physical', 'Physical')], default='virtual', max_length=10)),
                ('status', models.CharField(choices=[('active', 'Active'), ('frozen', 'Frozen'), ('cancelled', 'Cancelled')], default='active', max_length=10)),
                ('payment_number', models.CharField(blank=True, max_length=16)),
                ('daily_limit', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bank_cards', to='auth.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(choices=[('transfer_out', 'Transfer Out'), ('transfer_in', 'Transfer In'), ('payment', 'Payment'), ('refund', 'Refund'), ('deposit', 'Deposit')], max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('counterpart_payment_number', models.CharField(blank=True, max_length=16)),
                ('counterpart_label', models.CharField(blank=True, max_length=255)),
                ('note', models.CharField(blank=True, max_length=500)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed')], default='completed', max_length=10)),
                ('balance_after', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bank_transactions', to='auth.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
