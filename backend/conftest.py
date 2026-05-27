import pytest

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.banking.models import BankAccount


@pytest.fixture
def staff_user(db):
    """An admin user used as created_by / posted_by in transactions."""
    return User.objects.create_user(
        email='ops@prominence.test', password='Strong-Pw-2026',
        first_name='Ops', last_name='Admin', role='superadmin',
    )


@pytest.fixture
def operating_customer(db, staff_user):
    """The posting engine expects the bank's operating account to belong to customer id=1."""
    return Customer.objects.create(
        id=1, user=staff_user, customer_number='PB-C-OPERATING', customer_type='business',
    )


def _make_account(email, customer_number, account_number, name):
    user = User.objects.create_user(
        email=email, password='Strong-Pw-2026',
        first_name=name, last_name='Test', role='client',
    )
    customer = Customer.objects.create(
        user=user, customer_number=customer_number, customer_type='personal',
    )
    return BankAccount.objects.create(
        customer=customer, account_number=account_number,
        account_type='personal_checking', currency='USD', status='active',
        account_name=f'{name} Checking',
    )


@pytest.fixture
def client_account(db, operating_customer):
    return _make_account('john@prominence.test', 'PB-C-10000001', 'PB-CHK-10000001', 'John')


@pytest.fixture
def second_account(db, operating_customer):
    return _make_account('jane@prominence.test', 'PB-C-10000002', 'PB-CHK-10000002', 'Jane')
