"""Tests del motor de doble partida (BankingService).

El invariante central de cualquier sistema contable: en cada transaccion, la suma
de los debitos debe ser exactamente igual a la suma de los creditos. Si esto se
cumple siempre, los libros nunca se descuadran.
"""
from decimal import Decimal

import pytest
from django.db.models import Sum

from apps.banking.services import BankingService, InsufficientFundsError

pytestmark = pytest.mark.django_db


def assert_double_entry_balanced(txn):
    """Invariante: por transaccion, sum(debitos) == sum(creditos)."""
    debits = txn.ledger_entries.filter(entry_type='debit').aggregate(t=Sum('amount'))['t'] or Decimal('0')
    credits = txn.ledger_entries.filter(entry_type='credit').aggregate(t=Sum('amount'))['t'] or Decimal('0')
    assert debits == credits, f"Libros descuadrados: debitos={debits} != creditos={credits}"


def test_deposit_crea_doble_partida_balanceada(client_account, staff_user):
    txn = BankingService.deposit(client_account, Decimal('100.00'), 'Deposito de prueba', staff_user)

    # Exactamente 2 asientos (uno por cuenta)
    assert txn.ledger_entries.count() == 2
    assert_double_entry_balanced(txn)

    client_account.refresh_from_db()
    assert client_account.available_balance == Decimal('100.0000')


def test_hold_mueve_de_disponible_a_retenido(client_account, staff_user):
    BankingService.deposit(client_account, Decimal('100.00'), 'fondeo', staff_user)
    txn, _hold = BankingService.place_hold(client_account, Decimal('30.00'), 'verificacion', staff_user)

    client_account.refresh_from_db()
    assert client_account.available_balance == Decimal('70.0000')
    assert client_account.held_balance == Decimal('30.0000')
    # El dinero no se crea ni se destruye: el saldo total (ledger) no cambia
    assert client_account.ledger_balance == Decimal('100.0000')
    assert_double_entry_balanced(txn)


def test_release_hold_regresa_al_estado_original(client_account, staff_user):
    BankingService.deposit(client_account, Decimal('100.00'), 'fondeo', staff_user)
    _txn, hold = BankingService.place_hold(client_account, Decimal('40.00'), 'verificacion', staff_user)

    BankingService.release_hold(hold, staff_user)

    client_account.refresh_from_db()
    assert client_account.available_balance == Decimal('100.0000')
    assert client_account.held_balance == Decimal('0.0000')


def test_transferencia_interna_conserva_el_total(client_account, second_account, staff_user):
    BankingService.deposit(client_account, Decimal('100.00'), 'fondeo', staff_user)

    txn = BankingService.internal_transfer(client_account, second_account, Decimal('25.00'), 'movimiento', staff_user)

    client_account.refresh_from_db()
    second_account.refresh_from_db()
    assert client_account.available_balance == Decimal('75.0000')
    assert second_account.available_balance == Decimal('25.0000')
    # El dinero se conserva entre las dos cuentas de cliente
    assert client_account.available_balance + second_account.available_balance == Decimal('100.0000')
    assert_double_entry_balanced(txn)


def test_transferencia_sin_fondos_suficientes_falla(client_account, second_account, staff_user):
    BankingService.deposit(client_account, Decimal('10.00'), 'fondeo', staff_user)

    with pytest.raises(InsufficientFundsError):
        BankingService.internal_transfer(client_account, second_account, Decimal('50.00'), 'demasiado', staff_user)


def test_los_asientos_del_ledger_son_inmutables(client_account, staff_user):
    txn = BankingService.deposit(client_account, Decimal('10.00'), 'fondeo', staff_user)
    entry = txn.ledger_entries.first()

    with pytest.raises(ValueError):
        entry.amount = Decimal('999.0000')
        entry.save()

    with pytest.raises(ValueError):
        entry.delete()
