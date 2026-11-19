"""Preserve original /api/<module>/ prefixes and original module URL patterns."""
from django.urls import include, path

urlpatterns = [
    path(f'api/{module}/', include(f'{module}.urls'))
    for module in ['hotels', 'rooms', 'bookings', 'payments', 'promotions']
]

