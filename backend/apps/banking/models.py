import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from apps.core.models import TimestampedModel


class BankAccount(TimestampedModel):
    ACCOUNT_TYPE_CHOICES = [
        ('personal_checking', 'Personal Checking'),
        ('business_checking', 'Business Checking'),
        ('savings', 'Savings'),
        ('crypto', 'Cryptocurrency'),
        ('custody', 'Custody / Safekeeping'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('frozen', 'Frozen'),
        ('closed', 'Closed'),
        ('pending', 'Pending Approval'),
    ]

    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
        ('CHF', 'Swiss Franc'),
        ('BTC', 'Bitcoin'),
        ('ETH', 'Ethereum'),
        ('USDT', 'Tether'),
    ]

    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, related_name='accounts')
    account_number = models.CharField(max_length=20, unique=True)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    currency = models.CharField(max_length=5, choices=CURRENCY_CHOICES, default='USD')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    account_name = models.CharField(max_length=255, blank=True)

    # Cached balances (source of truth = sum of LedgerEntry)
    available_balance = models.DecimalField(max_digits=19, decimal_places=4, default=Decimal('0.0000'))
    ledger_balance = models.DecimalField(max_digits=19, decimal_places=4, default=Decimal('0.0000'))
    held_balance = models.DecimalField(max_digits=19, decimal_places=4, default=Decimal('0.0000'))
    in_transit_balance = models.DecimalField(max_digits=19, decimal_places=4, default=Decimal('0.0000'))

    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='opened_accounts'
    )

    class Meta:
        db_table = 'bank_accounts'

    def __str__(self):
        return f"{self.account_number} ({self.get_account_type_display()}) - {self.customer}"

    @staticmethod
    def generate_account_number(account_type):
        import random
        prefix_map = {
            'personal_checking': 'CHK',
            'business_checking': 'BIZ',
            'savings': 'SAV',
            'crypto': 'CRY',
            'custody': 'CUS',
        }
        prefix = prefix_map.get(account_type, 'GEN')
        return f"PB-{prefix}-{random.randint(10000000, 99999999)}"

    def recalculate_balances(self):
        from django.db.models import Sum, Q
        entries = self.ledger_entries.all()

        credits = entries.filter(entry_type='credit')
        debits = entries.filter(entry_type='debit')

        def sum_by_balance_type(qs, balance_type):
            return qs.filter(balance_type=balance_type).aggregate(
                total=Sum('amount'))['total'] or Decimal('0.0000')

        available_credits = sum_by_balance_type(credits, 'available')
        available_debits = sum_by_balance_type(debits, 'available')
        self.available_balance = available_credits - available_debits

        held_credits = sum_by_balance_type(credits, 'held')
        held_debits = sum_by_balance_type(debits, 'held')
        self.held_balance = held_credits - held_debits

        transit_credits = sum_by_balance_type(credits, 'in_transit')
        transit_debits = sum_by_balance_type(debits, 'in_transit')
        self.in_transit_balance = transit_credits - transit_debits

        self.ledger_balance = self.available_balance + self.held_balance + self.in_transit_balance
        self.save(update_fields=[
            'available_balance', 'ledger_balance', 'held_balance', 'in_transit_balance', 'updated_at'
        ])


class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('transfer_internal', 'Internal Transfer'),
        ('transfer_external', 'External Wire'),
        ('hold_place', 'Hold Placed'),
        ('hold_release', 'Hold Released'),
        ('adjustment', 'Adjustment'),
        ('fee', 'Fee'),
        ('interest', 'Interest'),
        ('reversal', 'Reversal'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('posted', 'Posted'),
        ('reversed', 'Reversed'),
        ('failed', 'Failed'),
    ]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Client-supplied key so a retried/double-clicked money operation posts only once.
    idempotency_key = models.CharField(max_length=255, null=True, blank=True, unique=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=5, default='USD')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    debit_account = models.ForeignKey(
        BankAccount, null=True, blank=True,
        on_delete=models.PROTECT, related_name='debit_transactions'
    )
    credit_account = models.ForeignKey(
        BankAccount, null=True, blank=True,
        on_delete=models.PROTECT, related_name='credit_transactions'
    )

    requires_approval = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_transactions'
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} - {self.get_transaction_type_display()} - {self.amount}"


class LedgerEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ('debit', 'Debit'),
        ('credit', 'Credit'),
    ]

    BALANCE_TYPE_CHOICES = [
        ('available', 'Available'),
        ('held', 'Held'),
        ('in_transit', 'In Transit'),
    ]

    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name='ledger_entries')
    account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='ledger_entries')
    entry_type = models.CharField(max_length=6, choices=ENTRY_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    balance_type = models.CharField(max_length=10, choices=BALANCE_TYPE_CHOICES, default='available')
    running_balance = models.DecimalField(max_digits=19, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL
    )

    class Meta:
        db_table = 'ledger_entries'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Ledger entries are immutable and cannot be updated")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Ledger entries are immutable and cannot be deleted")

    def __str__(self):
        return f"{self.entry_type} {self.amount} on {self.account.account_number}"


class Hold(TimestampedModel):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('released', 'Released'),
        ('expired', 'Expired'),
    ]

    account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='holds')
    transaction = models.ForeignKey(Transaction, null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    placed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='placed_holds'
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='released_holds'
    )
    released_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'holds'

    def __str__(self):
        return f"Hold {self.amount} on {self.account.account_number} - {self.status}"


class FundingInstruction(TimestampedModel):
    account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='funding_instructions')
    bank_name = models.CharField(max_length=255, default='Prominence Bank')
    routing_number = models.CharField(max_length=50, blank=True)
    swift_code = models.CharField(max_length=20, blank=True)
    account_holder = models.CharField(max_length=255)
    instructions_html = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'funding_instructions'
