from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

CORS_ALLOW_ALL_ORIGINS = True

# Show browsable API in development
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = (
    'rest_framework.renderers.JSONRenderer',
    'rest_framework.renderers.BrowsableAPIRenderer',
)

# Print OTP to console instead of sending email
OTP_BACKEND = 'console'

# Surface the login OTP in the API response so the local demo is one-click.
DEMO_MODE = True
