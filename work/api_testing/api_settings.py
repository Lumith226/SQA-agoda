"""Local API integration configuration with real JWT and an isolated database.

Application model/view/serializer/URL files are imported without modification.
SQLite and external-service doubles are explicit test-environment choices.
"""
from test_settings import *

ROOT_URLCONF = 'api_urls'
SECRET_KEY = 'api-integration-isolated-local-test-signing-key-no-production-credentials'
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework_simplejwt.authentication.JWTAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
}
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
]
DEBUG = False
MEDIA_ROOT = 'work/api_testing/test_media'
SIMPLE_JWT = {'SIGNING_KEY': SECRET_KEY}
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}

