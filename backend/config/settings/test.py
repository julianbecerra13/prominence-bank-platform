from .base import *  # noqa

# Fast, isolated tests: in-memory SQLite, no external services.
DEBUG = False
DEMO_MODE = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Speed up password hashing in tests.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

OTP_BACKEND = 'console'
