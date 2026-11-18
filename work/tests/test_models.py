"""Business model tests. Test Case IDs are declared beside every parameter set.

Write paths use real model saves, refresh_from_db, and the shared rollback audit.
Floating-point comparisons use independently calculated monetary expectations.
"""

from contract_support import checked_read
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch, PropertyMock
import math
import pytest
from django.utils import timezone
from django.db import IntegrityError, transaction
from hotels.models import Hotel, HotelImage, UserHotelInteraction
from rooms.models import Room, RoomImage, RoomAmenity, RoomBookingDetail
from bookings.models import Booking, GuestInfo, RefundPolicy
from payments.models import Payment
from promotions.models import (
    Promotion,
    RoomPromotion,
    CarPromotion,
    FlightPromotion,
    ActivityPromotion,
)
from conftest import case

HOTEL_CASES = [
    (
        "H-M01",
        "Persist hotel name and readable label",
        "Hotel name = Lotus Hotel",
        "Saved name and string equal Lotus Hotel",
    ),
    (
        "H-M02",
        "Compute neutral sentiment without division by zero",
        "No interactions",
        "Sentiment = 0",
    ),
    (
        "H-M03",
        "Compute positive and negative sentiment",
        "Positive=5; negative=2; neutral=2",
        "Sentiment = 0.3",
    ),
    ("H-M04", "Compute logarithmic click score", "Clicks = 9", "Score = ln(10)"),
    (
        "H-M05",
        "Persist weighted recommendation score",
        "Stars=4; clicks=9; positive=5; negative=2; neutral=2",
        "Score = 0.6*4 + 0.3*ln(10) + 0.1*0.3",
    ),
    (
        "H-M06",
        "Persist explicit weighted score refresh",
        "Stars changed to 3",
        "Stored score equals independent weighted formula",
    ),
    (
        "H-M07",
        "Return zero price for no available rooms",
        "All rooms unavailable",
        "Stored min_price = 0",
    ),
    (
        "H-M08",
        "Exclude unavailable rooms from price aggregation",
        "Available price=100; unavailable price=500",
        "Stored price = 100",
    ),
    (
        "H-M09",
        "Expose the lowest available nightly price",
        "Available room prices = 100 and 300",
        "min_price = 100",
    ),
    (
        "H-M10",
        "Render hotel image label",
        "Hotel image with parent hotel",
        "Image for Lotus Hotel",
    ),
    (
        "H-M11",
        "Persist individual interaction score",
        "Clicks=4; positive=3; negative=1; neutral=0",
        "0.7*(2/5) + 0.3*ln(5), persisted",
    ),
    (
        "H-M12",
        "Render interaction user and hotel label",
        "User tester; hotel Lotus Hotel",
        "Both names appear",
    ),
    (
        "H-M13",
        "Fallback when recommendation calculation raises",
        "Property raises ValueError",
        "Stored weighted score = 0",
    ),
    (
        "H-M14",
        "Enforce one interaction per user and hotel",
        "Insert duplicate user/hotel pair",
        "IntegrityError and original row preserved",
    ),
]


@pytest.mark.parametrize(
    "case_id",
    [
        case(
            case_index,
            "Hotels",
            objective,
            input_description,
            expected_description,
            "hotels/models.py",
        )
        for case_index, objective, input_description, expected_description in HOTEL_CASES
    ],
)
def test_hotel_persistence_and_recommendation_rules(case_id, sample_data):
    """Verify hotel persistence and recommendation rules.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    hotel = sample_data.hotel
    if case_id == "H-M01":
        hotel.refresh_from_db()
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert hotel.name == str(hotel) == "Lotus Hotel"
    elif case_id == "H-M02":
        assert hotel.sentiment_score == 0
    elif case_id == "H-M03":
        hotel.total_positive, hotel.total_negative, hotel.total_neutral = (5, 2, 2)
        assert hotel.sentiment_score == pytest.approx(0.3)
    elif case_id == "H-M04":
        hotel.total_click = 9
        assert hotel.click_score == pytest.approx(math.log(10))
    elif case_id in ("H-M05", "H-M06"):
        hotel.avg_star = 4 if case_id == "H-M05" else 3
        hotel.total_click = 9
        hotel.total_positive, hotel.total_negative, hotel.total_neutral = (5, 2, 2)
        expected = 0.6 * hotel.avg_star + 0.3 * math.log(10) + 0.1 * 0.3
        hotel.save() if case_id == "H-M05" else hotel.update_total_weighted_score()
        hotel.refresh_from_db()
        assert hotel.total_weighted_score == pytest.approx(expected)
    elif case_id == "H-M07":
        sample_data.room.available_rooms = 0
        sample_data.room.save()
        hotel.refresh_from_db()
        assert hotel.min_price == 0
    elif case_id == "H-M08":
        Room.objects.create(
            hotel=hotel, room_type="Closed", price_per_night=500, available_rooms=0
        )
        hotel.refresh_from_db()
        assert hotel.min_price == 100
    elif case_id == "H-M09":
        Room.objects.create(hotel=hotel, room_type="Suite", price_per_night=300)
        hotel.refresh_from_db()
        assert (
            hotel.min_price == 100
        ), f"Expected lowest price 100, observed {hotel.min_price}"
    elif case_id == "H-M10":
        assert (
            str(HotelImage.objects.create(hotel=hotel, image="hotel.png"))
            == "Image for Lotus Hotel"
        )
    elif case_id == "H-M11":
        resource = UserHotelInteraction.objects.create(
            user=sample_data.user,
            hotel=hotel,
            click_count=4,
            positive_count=3,
            negative_count=1,
        )
        resource.update_weighted_score()
        resource.refresh_from_db()
        assert resource.weighted_score == pytest.approx(0.7 * 2 / 5 + 0.3 * math.log(5))
    elif case_id == "H-M12":
        assert all(
            (
                name_fragment
                in str(UserHotelInteraction(user=sample_data.user, hotel=hotel))
                for name_fragment in ("tester", "Lotus Hotel")
            )
        )
    elif case_id == "H-M13":
        with patch.object(
            Hotel,
            "calc_total_weighted_score",
            new_callable=PropertyMock,
            side_effect=ValueError("invalid score"),
        ):
            hotel.save()
        hotel.refresh_from_db()
        assert hotel.total_weighted_score == 0
    elif case_id == "H-M14":
        UserHotelInteraction.objects.create(user=sample_data.user, hotel=hotel)
        with pytest.raises(IntegrityError), transaction.atomic():
            UserHotelInteraction.objects.create(user=sample_data.user, hotel=hotel)
        assert (
            UserHotelInteraction.objects.filter(
                user=sample_data.user, hotel=hotel
            ).count()
            == 1
        )


ROOM_CASES = [
    ("R-M01", "Sum adult and child capacity", "Adults=2; children=1", "Capacity=3"),
    (
        "R-M02",
        "Disable room when inventory is zero",
        "Available rooms=0",
        "available=False persisted",
    ),
    (
        "R-M03",
        "Disable expired room",
        "End date=yesterday",
        "available=False persisted",
    ),
    (
        "R-M04",
        "Keep room available on end date",
        "End date=today; inventory=10",
        "available=True persisted",
    ),
    (
        "R-M05",
        "Decrease inventory without negative balance",
        "Inventory=10; decrease=20",
        "Inventory=0 persisted",
    ),
    (
        "R-M06",
        "Decrease inventory by default quantity",
        "Inventory=10; no argument",
        "Inventory=9 persisted",
    ),
    (
        "R-M07",
        "Refresh hotel price after deleting last room",
        "Delete sole room",
        "No room remains; hotel price=0",
    ),
    (
        "R-M08",
        "Persist standalone room without hotel",
        "hotel=None",
        "Room saved and deleted successfully",
    ),
    (
        "R-M09",
        "Render room and amenity labels",
        "Deluxe room in Lotus Hotel",
        "Labels contain parent names",
    ),
    ("R-M10", "Return no promotion when none is linked", "No room promotions", "None"),
    ("R-M11", "Ignore inactive promotion", "is_active=False", "None"),
    ("R-M12", "Ignore future promotion", "Start date=tomorrow", "None"),
    ("R-M13", "Ignore expired promotion", "End date=yesterday", "None"),
    (
        "R-M14",
        "Use campaign discount when room override is zero",
        "Campaign 10%; room override 0",
        "Effective 10%",
    ),
    (
        "R-M15",
        "Use room-specific discount",
        "Campaign 10%; room override 20",
        "Effective 20%",
    ),
    (
        "R-M16",
        "Choose greatest effective percent discount",
        "Campaign 40% with room 0; campaign 10% with room 20",
        "Effective best discount=40%",
    ),
]


@pytest.mark.parametrize(
    "case_id",
    [
        case(
            case_index,
            "Rooms",
            objective,
            input_description,
            expected_description,
            "rooms/models.py:Room",
        )
        for case_index, objective, input_description, expected_description in ROOM_CASES
    ],
)
def test_room_inventory_availability_and_promotions(case_id, sample_data):
    """Verify room inventory availability and promotions.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    room = sample_data.room
    if case_id == "R-M01":
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert room.capacity == 3
    elif case_id in ("R-M02", "R-M03", "R-M04"):
        if case_id == "R-M02":
            room.available_rooms = 0
        else:
            room.end_date = (
                sample_data.now + timedelta(days=-1 if case_id == "R-M03" else 0)
            ).date()
        room.save()
        room.refresh_from_db()
        assert room.available == (case_id == "R-M04")
    elif case_id in ("R-M05", "R-M06"):
        (
            room.decrease_available_rooms(20)
            if case_id == "R-M05"
            else room.decrease_available_rooms()
        )
        room.refresh_from_db()
        assert room.available_rooms == (0 if case_id == "R-M05" else 9)
    elif case_id == "R-M07":
        record_id = room.pk
        room.delete()
        sample_data.hotel.refresh_from_db()
        assert not Room.objects.filter(pk=record_id).exists()
        assert sample_data.hotel.min_price == 0
    elif case_id == "R-M08":
        resource = Room.objects.create(room_type="Standalone", hotel=None)
        record_id = resource.pk
        resource.delete()
        assert not Room.objects.filter(pk=record_id).exists()
    elif case_id == "R-M09":
        assert str(room) == "Lotus Hotel - Deluxe"
        assert str(RoomImage(room=room)) == "Image for Deluxe in Lotus Hotel"
        assert str(RoomAmenity(room=room, name="WiFi")) == "WiFi (Deluxe)"
    elif case_id == "R-M10":
        assert checked_read(lambda: room.get_active_promotion()) is None
    else:
        promotion = sample_data.promotion
        if case_id == "R-M11":
            promotion.is_active = False
        if case_id == "R-M12":
            promotion.start_date = sample_data.now + timedelta(days=1)
        if case_id == "R-M13":
            promotion.start_date = sample_data.now - timedelta(days=2)
            promotion.end_date = sample_data.now - timedelta(days=1)
        promotion.save()
        RoomPromotion.objects.create(
            room=room,
            promotion=promotion,
            discount_percent=20 if case_id == "R-M15" else 0,
        )
        if case_id == "R-M16":
            promotion.discount_percent = 40
            promotion.save()
            competing_promotion = Promotion.objects.create(
                title="Second",
                discount_percent=10,
                start_date=promotion.start_date,
                end_date=promotion.end_date,
            )
            RoomPromotion.objects.create(
                room=room, promotion=competing_promotion, discount_percent=20
            )
        actual = checked_read(lambda: room.get_active_promotion())
        if case_id in ("R-M11", "R-M12", "R-M13"):
            assert actual is None
        else:
            expected = {"R-M14": 10, "R-M15": 20, "R-M16": 40}[case_id]
            assert (
                actual["discount_percent"] == expected
            ), f"Expected effective discount {expected}, observed {actual}"
            assert set(actual) == {
                "id",
                "title",
                "discount_percent",
                "discount_amount",
                "start_date",
                "end_date",
            }
            assert actual["id"] == promotion.pk and actual["title"] == promotion.title
            assert actual["discount_amount"] == promotion.discount_amount
            assert (
                actual["start_date"] == promotion.start_date
                and actual["end_date"] == promotion.end_date
            )


PRICE_CASES = [
    ("R-P01", "overnight", 2, 2, 0, 0, 400, 0),
    ("R-P02", "dayuse", 0, 2, 0, 0, 120, 0),
    ("R-P03", "overnight", 0, 1, 0, 0, 100, 0),
    ("R-P04", "overnight", 2, 1, 10, 0, 200, 20),
    ("R-P05", "overnight", 2, 1, 10, 15, 200, 15),
    ("R-P06", "overnight", 2, 1, 0, 300, 200, 200),
    ("R-P07", "overnight", 2, 1, 0, 20, 200, 20),
    ("R-P08", "overnight", 2, 1, 0, 0, 200, 0),
    ("R-P09", "overnight", 2, 1, 150, 0, 200, 200),
]


@pytest.mark.parametrize(
    "case_id,stay,nights,count,percent,amount,total,discount",
    [
        pytest.param(
            *case_values,
            id=case_values[0],
            marks=pytest.mark.case(
                module="Rooms",
                objective="Calculate room total, discount, final price, parent booking and stock",
                inputs=f"stay={case_values[1]}, nights={case_values[2]}, rooms={case_values[3]}, percent={case_values[4]}, cap={case_values[5]}",
                expected=f"total={case_values[6]}, discount={case_values[7]}, final={case_values[6] - case_values[7]}; stock decremented once",
                target="rooms/models.py:RoomBookingDetail.save",
                technique="Boundary values; decision table; real DB side effects",
            ),
        )
        for case_values in PRICE_CASES
    ],
)
def test_room_price_and_booking_sync(
    case_id, stay, nights, count, percent, amount, total, discount, sample_data
):
    """Verify room price and booking sync.

    Arrange: Prepare stay length, room count, nightly/day-use price and campaign discount.
    Act: Save the real RoomBookingDetail, then save it again to test repeat updates.
    Assert and CheckDB: Reload room, detail and booking; check totals, discount, final price, owner and inventory decremented exactly once.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    room = sample_data.room
    room.stay_type = stay
    room.save()
    if percent or amount or case_id == "R-P08":
        promotion = sample_data.promotion
        promotion.discount_percent = percent
        promotion.discount_amount = amount
        promotion.save()
        RoomPromotion.objects.create(
            room=room,
            promotion=promotion,
            discount_percent=percent,
            discount_amount=amount,
        )
    detail = RoomBookingDetail.objects.create(
        booking=sample_data.booking,
        room=room,
        check_in=sample_data.now + timedelta(days=2),
        check_out=sample_data.now + timedelta(days=2 + nights),
        num_guests=2,
        room_count=count,
    )
    detail.refresh_from_db()
    sample_data.booking.refresh_from_db()
    room.refresh_from_db()
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert detail.total_price == total
    assert (
        detail.discount_amount == discount
    ), f"Expected capped discount {discount}, observed {detail.discount_amount}"
    assert detail.final_price == total - discount
    assert (
        sample_data.booking.final_price == total - discount
        and sample_data.booking.total_price == total
    )
    assert detail.owner_hotel == sample_data.user and detail.room_type == "Deluxe"
    assert room.available_rooms == 10 - count
    detail.save()
    room.refresh_from_db()
    assert room.available_rooms == 10 - count
    assert sample_data.booking.booking_code in str(detail)


BOOKING_CASES = [
    (
        "B-M01",
        "Generate booking code",
        "Blank booking code",
        "AGD followed by 6 uppercase hexadecimal digits",
    ),
    (
        "B-M02",
        "Preserve explicit booking code",
        "booking_code=CUSTOM",
        "Code remains CUSTOM after two saves",
    ),
    (
        "B-M03",
        "Render booking and guest labels",
        "Booking with guest",
        "Booking code and guest name appear",
    ),
    (
        "B-M04",
        "Cascade delete guest and payments",
        "Booking with guest and payment",
        "Related guest and payment rows deleted",
    ),
    (
        "B-M05",
        "Keep booking after user deletion",
        "Booking references user",
        "Booking user becomes NULL",
    ),
    (
        "B-M06",
        "Render refund policy type",
        "Hotel policy",
        "Policy name and Hotel appear",
    ),
    (
        "B-M07",
        "Enforce unique booking code",
        "Two identical codes",
        "Duplicate rejected; existing row retained",
    ),
]


@pytest.mark.parametrize(
    "case_id",
    [
        case(
            case_index,
            "Bookings",
            objective,
            input_description,
            expected_description,
            "bookings/models.py",
        )
        for case_index, objective, input_description, expected_description in BOOKING_CASES
    ],
)
def test_booking_identifiers_and_referential_integrity(case_id, sample_data):
    """Verify booking identifiers and referential integrity.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    import re

    booking = sample_data.booking
    if case_id == "B-M01":
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert re.fullmatch("AGD[0-9A-F]{6}", booking.booking_code)
    elif case_id == "B-M02":
        booking.booking_code = "CUSTOM"
        booking.save()
        booking.save()
        booking.refresh_from_db()
        assert booking.booking_code == "CUSTOM"
    elif case_id == "B-M03":
        guest_info = GuestInfo.objects.create(
            booking=booking, full_name="Alice", email="alice@example.com", phone="123"
        )
        assert str(guest_info) == "Alice"
        assert booking.booking_code in str(booking)
    elif case_id == "B-M04":
        GuestInfo.objects.create(
            booking=booking, full_name="Alice", email="alice@example.com", phone="123"
        )
        record_id = booking.pk
        booking.delete()
        assert not GuestInfo.objects.filter(booking_id=record_id).exists()
        assert not Payment.objects.filter(booking_id=record_id).exists()
    elif case_id == "B-M05":
        sample_data.user.delete()
        booking.refresh_from_db()
        assert booking.user_id is None
    elif case_id == "B-M06":
        assert str(RefundPolicy(name="Standard", service_type=1)) == "Standard - Hotel"
    elif case_id == "B-M07":
        with pytest.raises(IntegrityError), transaction.atomic():
            Booking.objects.create(service_type=1, booking_code=booking.booking_code)
        assert Booking.objects.filter(booking_code=booking.booking_code).count() == 1


@pytest.mark.parametrize(
    "case_id",
    [
        case(
            "P-M01",
            "Payments",
            "Persist payment amount and booking foreign key",
            "Amount=125.5; method=1",
            "Reloaded amount 125.5 and matching booking",
            "payments/models.py:Payment",
        )
    ],
)
def test_payment_amount_and_booking_persistence(case_id, sample_data):
    """Verify payment amount and booking persistence.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    payment = sample_data.payment
    payment.amount = 125.5
    payment.save()
    payment.refresh_from_db()
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert payment.amount == 125.5
    assert payment.booking_id == sample_data.booking.pk


@pytest.mark.parametrize(
    "case_id",
    [
        case(
            "PR-M01",
            "Promotions",
            "Render all promotion model labels",
            "Hotel, flight, activity, room and car links",
            "Correct parent title and service labels",
            "promotions/models.py",
        )
    ],
)
def test_promotion_model_labels(case_id, sample_data):
    """Verify promotion model labels.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    promotion = sample_data.promotion
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert str(promotion).startswith("Summer (")
    assert (
        str(RoomPromotion(promotion=promotion, room=sample_data.room))
        == "Summer -> Room: Deluxe"
    )
    assert (
        str(FlightPromotion(promotion=promotion, flight=None))
        == "Summer -> Flight: N/A"
    )
    assert str(CarPromotion(promotion=promotion, car=None)) == "Summer -> Car: N/A"
    from cars.models import Car
    from flights.models import Flight

    car = Car(id=7, name="Sedan")
    flight = Flight(id=8)
    assert str(CarPromotion(promotion=promotion, car=car)) == "Summer -> Car: Sedan"
    assert (
        str(FlightPromotion(promotion=promotion, flight=flight))
        == "Summer -> Flight: 8"
    )
    from activities.models import ActivityDate

    assert (
        str(ActivityPromotion(promotion=promotion, activity_date=ActivityDate(id=9)))
        == "Summer -> ActivityDate: 9"
    )


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_hotel_persistence_and_recommendation_rules
# Test Case ID: H-M01
# Test Case ID: H-M02
# Test Case ID: H-M03
# Test Case ID: H-M04
# Test Case ID: H-M05
# Test Case ID: H-M06
# Test Case ID: H-M07
# Test Case ID: H-M08
# Test Case ID: H-M09
# Test Case ID: H-M10
# Test Case ID: H-M11
# Test Case ID: H-M12
# Test Case ID: H-M13
# Test Case ID: H-M14
# Function: test_room_inventory_availability_and_promotions
# Test Case ID: R-M01
# Test Case ID: R-M02
# Test Case ID: R-M03
# Test Case ID: R-M04
# Test Case ID: R-M05
# Test Case ID: R-M06
# Test Case ID: R-M07
# Test Case ID: R-M08
# Test Case ID: R-M09
# Test Case ID: R-M10
# Test Case ID: R-M11
# Test Case ID: R-M12
# Test Case ID: R-M13
# Test Case ID: R-M14
# Test Case ID: R-M15
# Test Case ID: R-M16
# Function: test_room_price_and_booking_sync
# Test Case ID: R-P01
# Test Case ID: R-P02
# Test Case ID: R-P03
# Test Case ID: R-P04
# Test Case ID: R-P05
# Test Case ID: R-P06
# Test Case ID: R-P07
# Test Case ID: R-P08
# Test Case ID: R-P09
# Function: test_booking_identifiers_and_referential_integrity
# Test Case ID: B-M01
# Test Case ID: B-M02
# Test Case ID: B-M03
# Test Case ID: B-M04
# Test Case ID: B-M05
# Test Case ID: B-M06
# Test Case ID: B-M07
# Function: test_payment_amount_and_booking_persistence
# Test Case ID: P-M01
# Function: test_promotion_model_labels
# Test Case ID: PR-M01
