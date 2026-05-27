from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from .models import BankAccount, Transaction, LedgerEntry, Hold


class InsufficientFundsError(Exception):
    pass


class AccountNotActiveError(Exception):
    pass


class BankingService:
    """Double-entry posting engine. Every financial operation creates exactly 2 ledger entries.

    Money-moving operations are:
      - idempotent: an optional `idempotency_key` makes a retried/double-clicked request post once.
      - concurrency-safe: balances are read under a row-level lock (SELECT ... FOR UPDATE) inside
        the same atomic transaction, so two simultaneous requests can't both pass a balance check
        and overdraw an account (TOCTOU race).
    """

    # The bank's internal operating account for deposits/withdrawals
    OPERATING_ACCOUNT_NUMBER = 'PB-OPS-00000001'

    @classmethod
    def get_operating_account(cls):
        account, _ = BankAccount.objects.get_or_create(
            account_number=cls.OPERATING_ACCOUNT_NUMBER,
            defaults={
                'account_type': 'business_checking',
                'currency': 'USD',
                'status': 'active',
                'account_name': 'Prominence Bank Operating Account',
                'customer_id': 1,
            }
        )
        return account

    @classmethod
    def _validate_account(cls, account):
        if account.status != 'active':
            raise AccountNotActiveError(f"Account {account.account_number} is not active")

    @staticmethod
    def _existing_for_key(idempotency_key):
        """Return the transaction already posted for this key, if any (idempotency guard)."""
        if not idempotency_key:
            return None
        return Transaction.objects.filter(idempotency_key=idempotency_key).first()

    @staticmethod
    def _lock(account):
        """Re-fetch the account row with FOR UPDATE so balance checks are race-safe."""
        return BankAccount.objects.select_for_update().get(pk=account.pk)

    @classmethod
    def _create_ledger_entry(cls, transaction_obj, account, entry_type, amount, balance_type, posted_by):
        # Calculate running balance
        existing = account.ledger_entries.filter(balance_type=balance_type)
        credits_sum = existing.filter(entry_type='credit').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        debits_sum = existing.filter(entry_type='debit').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        current = credits_sum - debits_sum
        if entry_type == 'credit':
            running = current + amount
        else:
            running = current - amount

        return LedgerEntry.objects.create(
            transaction=transaction_obj,
            account=account,
            entry_type=entry_type,
            amount=amount,
            balance_type=balance_type,
            running_balance=running,
            posted_by=posted_by,
        )

    @classmethod
    @db_transaction.atomic
    def deposit(cls, account, amount, description, posted_by, idempotency_key=None):
        """Deposit funds into an account. Debits operating, credits customer."""
        existing = cls._existing_for_key(idempotency_key)
        if existing:
            return existing

        amount = Decimal(str(amount))
        account = cls._lock(account)
        cls._validate_account(account)

        operating = cls.get_operating_account()

        txn = Transaction.objects.create(
            transaction_type='deposit',
            description=description or f"Deposit to {account.account_number}",
            amount=amount,
            currency=account.currency,
            status='posted',
            debit_account=operating,
            credit_account=account,
            created_by=posted_by,
            posted_at=timezone.now(),
            idempotency_key=idempotency_key,
        )

        # Double entry: debit operating, credit customer
        cls._create_ledger_entry(txn, operating, 'debit', amount, 'available', posted_by)
        cls._create_ledger_entry(txn, account, 'credit', amount, 'available', posted_by)

        account.recalculate_balances()
        operating.recalculate_balances()

        return txn

    @classmethod
    @db_transaction.atomic
    def place_hold(cls, account, amount, reason, placed_by, expires_at=None, idempotency_key=None):
        """Place a hold: moves funds from available to held."""
        existing = cls._existing_for_key(idempotency_key)
        if existing:
            return existing, existing.holds.first() if hasattr(existing, 'holds') else None

        amount = Decimal(str(amount))
        account = cls._lock(account)
        cls._validate_account(account)

        if account.available_balance < amount:
            raise InsufficientFundsError(f"Available balance {account.available_balance} < hold amount {amount}")

        txn = Transaction.objects.create(
            transaction_type='hold_place',
            description=f"Hold placed: {reason}",
            amount=amount,
            currency=account.currency,
            status='posted',
            debit_account=account,
            credit_account=account,
            created_by=placed_by,
            posted_at=timezone.now(),
            idempotency_key=idempotency_key,
        )

        # Debit available, credit held
        cls._create_ledger_entry(txn, account, 'debit', amount, 'available', placed_by)
        cls._create_ledger_entry(txn, account, 'credit', amount, 'held', placed_by)

        hold = Hold.objects.create(
            account=account,
            transaction=txn,
            amount=amount,
            reason=reason,
            placed_by=placed_by,
            expires_at=expires_at,
        )

        account.recalculate_balances()
        return txn, hold

    @classmethod
    @db_transaction.atomic
    def release_hold(cls, hold, released_by):
        """Release a hold: moves funds from held back to available."""
        account = cls._lock(hold.account)
        amount = hold.amount

        txn = Transaction.objects.create(
            transaction_type='hold_release',
            description=f"Hold released: {hold.reason}",
            amount=amount,
            currency=account.currency,
            status='posted',
            debit_account=account,
            credit_account=account,
            created_by=released_by,
            posted_at=timezone.now(),
        )

        # Debit held, credit available
        cls._create_ledger_entry(txn, account, 'debit', amount, 'held', released_by)
        cls._create_ledger_entry(txn, account, 'credit', amount, 'available', released_by)

        hold.status = 'released'
        hold.released_by = released_by
        hold.released_at = timezone.now()
        hold.save()

        account.recalculate_balances()
        return txn

    @classmethod
    @db_transaction.atomic
    def internal_transfer(cls, from_account, to_account, amount, description, initiated_by, idempotency_key=None):
        """Transfer between two customer accounts."""
        existing = cls._existing_for_key(idempotency_key)
        if existing:
            return existing

        amount = Decimal(str(amount))

        # Lock both rows in a deterministic order (by pk) to avoid deadlocks.
        order = sorted([from_account.pk, to_account.pk])
        locked = {a.pk: a for a in BankAccount.objects.select_for_update().filter(pk__in=order)}
        from_account = locked[from_account.pk]
        to_account = locked[to_account.pk]

        cls._validate_account(from_account)
        cls._validate_account(to_account)

        if from_account.available_balance < amount:
            raise InsufficientFundsError(
                f"Available balance {from_account.available_balance} < transfer amount {amount}"
            )

        txn = Transaction.objects.create(
            transaction_type='transfer_internal',
            description=description or f"Transfer from {from_account.account_number} to {to_account.account_number}",
            amount=amount,
            currency=from_account.currency,
            status='posted',
            debit_account=from_account,
            credit_account=to_account,
            created_by=initiated_by,
            posted_at=timezone.now(),
            idempotency_key=idempotency_key,
        )

        cls._create_ledger_entry(txn, from_account, 'debit', amount, 'available', initiated_by)
        cls._create_ledger_entry(txn, to_account, 'credit', amount, 'available', initiated_by)

        from_account.recalculate_balances()
        to_account.recalculate_balances()

        return txn

    @classmethod
    @db_transaction.atomic
    def adjustment(cls, account, amount, description, posted_by, is_credit=True, idempotency_key=None):
        """Admin balance adjustment."""
        existing = cls._existing_for_key(idempotency_key)
        if existing:
            return existing

        amount = Decimal(str(amount))
        account = cls._lock(account)
        cls._validate_account(account)
        operating = cls.get_operating_account()

        txn = Transaction.objects.create(
            transaction_type='adjustment',
            description=description or f"Adjustment on {account.account_number}",
            amount=amount,
            currency=account.currency,
            status='posted',
            debit_account=operating if is_credit else account,
            credit_account=account if is_credit else operating,
            created_by=posted_by,
            posted_at=timezone.now(),
            idempotency_key=idempotency_key,
        )

        if is_credit:
            cls._create_ledger_entry(txn, operating, 'debit', amount, 'available', posted_by)
            cls._create_ledger_entry(txn, account, 'credit', amount, 'available', posted_by)
        else:
            cls._create_ledger_entry(txn, account, 'debit', amount, 'available', posted_by)
            cls._create_ledger_entry(txn, operating, 'credit', amount, 'available', posted_by)

        account.recalculate_balances()
        operating.recalculate_balances()

        return txn
