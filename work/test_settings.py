"""Isolated test configuration. No production environment or live services are read."""
SECRET_KEY = 'isolated-unit-test-key'
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'rest_framework', 'rest_framework_simplejwt.token_blacklist', 'accounts', 'countries', 'cities', 'hotels', 'rooms', 'bookings', 'payments', 'promotions', 'airports', 'airlines', 'flights', 'cars', 'activities', 'reviews', 'notifications', 'chats', 'neighborhood', 'quick_info', 'faqs', 'travel_tips', 'accommodationtype', 'travelguide', 'handbooks']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
AUTH_USER_MODEL = 'accounts.CustomUser'
USE_TZ = True
TIME_ZONE = 'UTC'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
ROOT_URLCONF = 'test_urls'
MIDDLEWARE = []
ALLOWED_HOSTS = ['testserver', 'localhost']
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES': [], 'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny']}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DEFAULT_FROM_EMAIL = 'test@example.com'
MEDIA_ROOT = 'work/test_media'
MEDIA_URL = '/media/'
STRIPE_SECRET_KEY = 'sk_test_placeholder_no_network'
STRIPE_WEBHOOK_SECRET = 'test-placeholder'
FRONT_END_URL = 'http://localhost'
ADMIN_URL = 'http://localhost/admin'
# Build current model schema. Migration correctness and MySQL dialect are separate integration concerns.
MIGRATION_MODULES = {app: None for app in INSTALLED_APPS if not app.startswith(('django.', 'rest_framework'))}
