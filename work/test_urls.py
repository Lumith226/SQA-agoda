"""Routes limited to the five requested feature modules."""
from django.urls import include, path
urlpatterns = [path(f'{app}/', include(f'{app}.urls')) for app in ['hotels', 'rooms', 'bookings', 'payments', 'promotions']]
