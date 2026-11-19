"""Deterministic API fixtures, created inside each request's rollback boundary.

Two owners, cities and service graphs let response checks detect cross-record
leakage. Every primary key and business amount is explicit and independent of
the API response. There are no production credentials or live customer rows.
"""
from datetime import timedelta
from types import SimpleNamespace
from django.utils import timezone

def seed_fixtures(profile=None):
    """Arrange reference and contrast records before the HTTP operation executes."""
    from accounts.models import CustomUser
    from countries.models import Country
    from cities.models import City
    from hotels.models import Hotel, HotelImage, UserHotelInteraction
    from rooms.models import Room, RoomImage, RoomAmenity
    from bookings.models import Booking, GuestInfo, RefundPolicy
    from payments.models import Payment
    from cars.models import Car
    from airlines.models import Airline
    from airports.models import Airport
    from flights.models import Flight, FlightLeg, SeatClassPricing
    from activities.models import Activity, ActivityPackage, ActivityDate
    from promotions.models import Promotion, RoomPromotion, CarPromotion, FlightPromotion, ActivityPromotion

    now = timezone.now()
    state = SimpleNamespace(now=now)
    for index in (1, 2):
        owner = CustomUser.objects.create_user(id=index, username=f'api_owner_{index}',
            email=f'owner{index}@example.com', password='Api-test-123!', role='owner')
        country = Country.objects.create(id=index, name=['Vietnam', 'Japan'][index-1])
        city = City.objects.create(id=index, country=country, name=['Hanoi', 'Tokyo'][index-1])
        hotel = Hotel.objects.create(id=index, owner=owner, city=city,
            name=['Lotus Hotel', 'Harbor Hotel'][index-1], avg_star=[4, 2][index-1])
        room = Room.objects.create(id=index, hotel=hotel, room_type=['Deluxe', 'Family'][index-1],
            stay_type=['overnight', 'dayuse'][index-1], price_per_night=[100, 300][index-1],
            price_per_day=[60, 80][index-1], total_rooms=10, available_rooms=10,
            adults_capacity=index+1, children_capacity=index-1,
            start_date=now.date()-timedelta(days=5), end_date=now.date()+timedelta(days=365))
        HotelImage.objects.create(id=index, hotel=hotel, image=f'/media/api-fixture-{index}.png')
        RoomImage.objects.create(id=index, room=room, image=f'/media/api-room-{index}.png')
        RoomAmenity.objects.create(id=index, room=room, name=['WiFi', 'Parking'][index-1])
        UserHotelInteraction.objects.create(id=index, user=owner, hotel=hotel, click_count=index)
        booking = Booking.objects.create(id=index, user=owner, booking_code=f'AGDAPI{index}',
            service_type=index, total_price=100*index, final_price=100*index)
        GuestInfo.objects.create(id=index, booking=booking, full_name=f'Guest {index}',
            email=f'guest{index}@example.com', phone=f'090000000{index}')
        Payment.objects.create(id=index, booking=booking, amount=100*index, method=index,
            transaction_id=f'cs_fixture_{index}')
        RefundPolicy.objects.create(id=index, service_type=index, name=f'Policy {index}',
            is_active=(index==1), refund_percentage=50, hours_before_start=24)
        car = Car.objects.create(id=index, user=owner, name=f'Car {index}', capacity=4,
            luggage=2, price_per_km=10, avg_speed=50)
        airline = Airline.objects.create(id=index, name=f'Airline {index}', code=f'T{index}',
            flight_operations_staff=owner)
        flight = Flight.objects.create(id=index, airline=airline, base_price=100*index)
        airport = Airport.objects.create(id=index, city=city, name=f'Airport {index}', code=f'A{index}A')
        FlightLeg.objects.create(id=index, flight=flight, departure_airport=airport,
            arrival_airport=airport, departure_time=now+timedelta(days=3),
            arrival_time=now+timedelta(days=3,hours=2), flight_code=f'T{index}001',duration_minutes=120)
        SeatClassPricing.objects.create(id=index, flight=flight, seat_class='economy',capacity=20,available_seats=20)
        activity = Activity.objects.create(id=index, name=f'Museum {index}', city=city,
            total_time=2, event_organizer=owner)
        package = ActivityPackage.objects.create(id=index, activity=activity, name=f'Package {index}')
        activity_date = ActivityDate.objects.create(id=index, activity_package=package,
            date_launch=now+timedelta(days=3), price_adult=50,price_child=25,participants_available=20)
        promotion = Promotion.objects.create(id=index, title=['Summer', 'Winter'][index-1],
            discount_percent=10*index, start_date=now-timedelta(days=1),end_date=now+timedelta(days=10),
            is_active=(index==1),promotion_type=index)
        for model, field, related in [(RoomPromotion,'room',room),(CarPromotion,'car',car),
                (FlightPromotion,'flight',flight),(ActivityPromotion,'activity_date',activity_date)]:
            model.objects.create(id=index,promotion=promotion,**{field:related},discount_percent=5*index)
        if index == 1:
            state.__dict__.update(owner=owner,user=owner,country=country,city=city,hotel=hotel,room=room,
                booking=booking,promotion=promotion,car=car,flight=flight,activity_date=activity_date)
    # A third booking has no payment, so payment-create tests can exercise inserts.
    Booking.objects.create(id=3,user=state.owner,booking_code='AGDAPI3',service_type=1,total_price=150,final_price=150)
    if profile and profile.get('room_booking'):
        from rooms.models import RoomBookingDetail
        # Leave the PK unset so the model's real first-insert inventory hook
        # executes. The empty table deterministically assigns ID 1.
        detail = RoomBookingDetail.objects.create(booking=state.booking,room=state.room,
            check_in=now+timedelta(days=3),check_out=now+timedelta(days=4),num_guests=1,room_count=1)
        assert detail.pk==1
        state.booking.service_ref_ids = [detail.id]
        state.booking.save(update_fields=['service_ref_ids'])
    if profile:
        apply_profile(profile)
    return state

def apply_profile(profile):
    """Change explicitly selected fixture fields for boundary/state test cases."""
    from django.apps import apps
    for modification in profile.get('updates', []):
        model = apps.get_model(modification['model'])
        model.objects.filter(pk=modification.get('id',1)).update(**modification['values'])
    for removal in profile.get('deletes', []):
        apps.get_model(removal['model']).objects.filter(pk=removal.get('id',1)).delete()
