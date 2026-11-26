from django.db import models
from django.contrib.auth.models import User


# PaymentSession: stores temporary payment session identifiers.
# No sensitive data (PINs, card numbers) stored in Django DB.
class PaymentSession(models.Model):
    sid = models.CharField(max_length=200, null=False, unique=True, blank=False)
    skey = models.CharField(max_length=200, null=False, blank=False)
    _from = models.CharField(max_length=16, null=False, blank=False)
    to = models.CharField(max_length=16, null=False, blank=False)
    amount = models.IntegerField(default=0, null=False, blank=False)


# BankCard: stores UI-level card metadata only.
# The actual financial data (balance, PIN) lives in the VRC Banking Backend.
# Card numbers are masked in templates - full number only shown on hover.
class BankCard(models.Model):
    CARD_TYPE_CHOICES = [
        ('virtual', 'Virtual'),
        ('physical', 'Physical'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('frozen', 'Frozen'),
        ('cancelled', 'Cancelled'),
        ('pending_replacement', 'Pending Replacement'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bank_cards')
    card_type = models.CharField(max_length=10, choices=CARD_TYPE_CHOICES, default='virtual')
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='active')
    # Payment number (16-digit) is stored here to allow card display;
    # it is also stored in the VRC banking backend as the account identifier.
    payment_number = models.CharField(max_length=16, blank=True, unique=True)
    # Replacement tracking
    replacement_reason = models.CharField(max_length=50, blank=True)
    replaced_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replaces_card'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.card_type} ({self.status})"

    def masked_number(self):
        """Return masked card number for display, e.g. **** **** **** 1234"""
        if len(self.payment_number) == 16:
            return f"**** **** **** {self.payment_number[-4:]}"
        return self.payment_number


# Transaction: local Django record for audit and display purposes.
# Financial truth lives in the VRC Banking Backend (history JSON field).
# This model acts as a local cache/audit log of transactions made through Django.
class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('transfer_out', 'Transfer Out'),
        ('transfer_in', 'Transfer In'),
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('deposit', 'Deposit'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bank_transactions')
    # Card used for this transaction (null for transfers that predate multi-card support)
    card = models.ForeignKey('BankCard', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Recipient payment number (for outgoing) or sender (for incoming)
    counterpart_payment_number = models.CharField(max_length=16, blank=True)
    counterpart_label = models.CharField(max_length=255, blank=True)
    note = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='completed')
    # Balance after transaction (fetched from backend at time of transaction)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} {self.amount} NE ({self.created_at})"


# Beneficiary: saved recipient accounts for quick transfers.
# Owned by user; account number validated on creation.
class Beneficiary(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='beneficiaries')
    label = models.CharField(max_length=100)
    account_number = models.CharField(max_length=16)
    # Optional cached name from backend (not authoritative)
    display_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['label']
        unique_together = ('user', 'account_number')

    def __str__(self):
        return f"{self.user.username} -> {self.label} ({self.account_number})"

    def masked_number(self):
        if len(self.account_number) == 16:
            return f"**** **** **** {self.account_number[-4:]}"
        return self.account_number
