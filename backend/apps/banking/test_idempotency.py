"""Tests de idempotencia: una operacion de dinero reintentada (doble clic, retry de red)
debe aplicarse UNA sola vez si se envia con la misma clave de idempotencia.
"""
from decimal import Decimal

import pytest

from apps.banking.services import BankingService

pytestmark = pytest.mark.django_db


def test_idempotency_evita_doble_deposito(client_account, staff_user):
    key = 'dep-abc-123'
    t1 = BankingService.deposit(client_account, Decimal('100.00'), 'dep', staff_user, idempotency_key=key)
    t2 = BankingService.deposit(client_account, Decimal('100.00'), 'dep', staff_user, idempotency_key=key)

    # Misma transaccion devuelta, no se creo una segunda
    assert t1.pk == t2.pk
    client_account.refresh_from_db()
    # El saldo solo refleja UN deposito
    assert client_account.available_balance == Decimal('100.0000')


def test_idempotency_claves_distintas_si_aplican(client_account, staff_user):
    BankingService.deposit(client_account, Decimal('50.00'), 'a', staff_user, idempotency_key='k1')
    BankingService.deposit(client_account, Decimal('50.00'), 'b', staff_user, idempotency_key='k2')

    client_account.refresh_from_db()
    assert client_account.available_balance == Decimal('100.0000')


def test_idempotency_evita_doble_transferencia(client_account, second_account, staff_user):
    BankingService.deposit(client_account, Decimal('100.00'), 'fondeo', staff_user)
    key = 'tr-xyz-789'

    t1 = BankingService.internal_transfer(client_account, second_account, Decimal('30.00'), 'mv', staff_user, idempotency_key=key)
    t2 = BankingService.internal_transfer(client_account, second_account, Decimal('30.00'), 'mv', staff_user, idempotency_key=key)

    assert t1.pk == t2.pk
    client_account.refresh_from_db()
    second_account.refresh_from_db()
    # Solo se movio 30 una vez
    assert client_account.available_balance == Decimal('70.0000')
    assert second_account.available_balance == Decimal('30.0000')
