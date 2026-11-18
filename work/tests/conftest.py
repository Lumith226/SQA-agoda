"""Shared fixtures, audited database rollback, and machine-readable test evidence."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from django.db import transaction
from django.apps import apps
from django.utils import timezone
from datetime import timedelta

RESULTS = {}
pytestmark = pytest.mark.django_db

def pytest_configure(config):
    config.addinivalue_line('markers', 'case(module, objective, inputs, expected, target, technique): report metadata')

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    marker = item.get_closest_marker('case')
    if marker is None:
        return
    entry = RESULTS.setdefault(item.nodeid, dict(marker.kwargs, nodeid=item.nodeid, id=item.callspec.id if hasattr(item, 'callspec') else item.name, status='NOT RUN', reason='Test execution did not reach the call phase.'))
    if report.when == 'call':
        entry['status'] = {'passed':'PASS', 'failed':'FAIL', 'skipped':'NOT RUN'}[report.outcome]
        entry['reason'] = '' if report.passed else str(report.longrepr)
        entry['duration'] = report.duration
    elif report.failed:
        entry['status'] = 'ERROR'
        entry['reason'] = f'{report.when}: {report.longrepr}'
    if report.when == 'teardown':
        entry['rollback_verified'] = report.passed

def pytest_sessionfinish(session, exitstatus):
    folder = Path('work/evidence')
    folder.mkdir(parents=True, exist_ok=True)
    source_root=Path(__file__).resolve().parents[2]/'UnitTest/SQA-main/SQA-main/agoda-be'
    if not source_root.exists():source_root=Path('backend').resolve()
    source_files=sorted({str(Path(m.__file__).resolve().relative_to(source_root)).replace('\\','/') for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(source_root)})
    (folder/'results.json').write_text(json.dumps({'exitcode':int(exitstatus), 'tests':list(RESULTS.values()),'source_files':source_files}, indent=2, default=str), encoding='utf-8')

@pytest.fixture(autouse=True)
def isolate_and_verify_rollback(db, monkeypatch):
    """CheckDB: compare persisted rows before and after a real savepoint rollback.

    All fixtures and the test body run inside this savepoint. Assertions still run
    on real SQLite rows. pytest-django additionally rolls back its outer test
    transaction. No production DB configuration is imported.
    """
    # HotelPagination stores filters on its class. Reset between independent
    # cases; a dedicated sequential-request regression tests the leak itself.
    from hotels.views import HotelPagination
    monkeypatch.setattr(HotelPagination, 'filters', {})
    relevant = list(apps.get_models())
    def snapshot():
        return {m._meta.label: list(m.objects.order_by('pk').values_list()) for m in relevant}
    before = snapshot()
    with transaction.atomic():
        yield
        transaction.set_rollback(True)
    assert snapshot() == before, 'Database rows did not return to the pre-test state after rollback'

@pytest.fixture
def data():
    from accounts.models import CustomUser
    from countries.models import Country
    from cities.models import City
    from hotels.models import Hotel
    from rooms.models import Room
    from bookings.models import Booking
    from payments.models import Payment
    from promotions.models import Promotion, RoomPromotion
    user = CustomUser.objects.create_user(username='tester', email='guest@example.com', password='Test-strong-123', role='owner')
    country = Country.objects.create(name='Vietnam')
    city = City.objects.create(name='Hanoi', country=country)
    hotel = Hotel.objects.create(name='Lotus Hotel', city=city, owner=user, avg_star=4)
    room = Room.objects.create(hotel=hotel, room_type='Deluxe', price_per_night=100, price_per_day=60, total_rooms=10, available_rooms=10, adults_capacity=2, children_capacity=1, start_date=timezone.now().date()-timedelta(days=1), end_date=timezone.now().date()+timedelta(days=365))
    booking = Booking.objects.create(user=user, service_type=1, total_price=100, final_price=100)
    payment = Payment.objects.create(booking=booking, amount=100, method=1)
    now = timezone.now()
    promotion = Promotion.objects.create(title='Summer', discount_percent=10, start_date=now-timedelta(days=1), end_date=now+timedelta(days=10))
    return SimpleNamespace(user=user, country=country, city=city, hotel=hotel, room=room, booking=booking, payment=payment, promotion=promotion, now=now)

@pytest.fixture
def factory():
    from rest_framework.test import APIRequestFactory
    return APIRequestFactory()

@pytest.fixture
def services(data):
    """Real related service records used only to test the selected five modules."""
    from cars.models import Car
    from airlines.models import Airline, Aircraft
    from airports.models import Airport
    from flights.models import Flight, FlightLeg, SeatClassPricing
    from activities.models import Activity, ActivityPackage, ActivityDate
    car=Car.objects.create(user=data.user,name='Sedan',capacity=4,luggage=2,price_per_km=10,avg_speed=50)
    airline=Airline.objects.create(name='Test Airline',code='TA',flight_operations_staff=data.user)
    flight=Flight.objects.create(airline=airline,base_price=100)
    a1=Airport.objects.create(name='Origin',code='AAA',city=data.city)
    a2=Airport.objects.create(name='Destination',code='BBB',city=data.city)
    leg=FlightLeg.objects.create(flight=flight,departure_airport=a1,arrival_airport=a2,departure_time=data.now+timedelta(days=3),arrival_time=data.now+timedelta(days=3,hours=2),flight_code='TA001',duration_minutes=120)
    SeatClassPricing.objects.create(flight=flight,seat_class='economy',capacity=20,available_seats=20)
    activity=Activity.objects.create(name='Museum',city=data.city,total_time=2,event_organizer=data.user)
    package=ActivityPackage.objects.create(activity=activity,name='Standard')
    ad=ActivityDate.objects.create(activity_package=package,date_launch=data.now+timedelta(days=3),price_adult=50,price_child=25,participants_available=20)
    return SimpleNamespace(car=car,airline=airline,flight=flight,leg=leg,a1=a1,a2=a2,activity=activity,package=package,ad=ad)

def case(case_id, module, objective, inputs, expected, target, technique='Equivalence partitioning; real database assertions'):
    """Each parameter ID is the corresponding Test Case ID required by the prompt."""
    return pytest.param(case_id, id=case_id, marks=pytest.mark.case(module=module, objective=objective, inputs=inputs, expected=expected, target=target, technique=technique))
