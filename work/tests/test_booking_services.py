"""Booking orchestration over the service graphs used by the selected modules."""

from datetime import timedelta
import pytest
from bookings.models import Booking, GuestInfo
from bookings.views import BookingViewSet
from bookings.constants.booking_status import BookingStatus
from payments.constants.payment_status import PaymentStatus
from test_views import request_view
from test_lifecycle import mark, attach_detail


@pytest.mark.parametrize(
    "case_id,kind,many",
    [
        pytest.param(
            f"B-N{case_index:02}",
            kind,
            many,
            id=f"B-N{case_index:02}",
            marks=mark(
                f"B-N{case_index:02}",
                "Bookings",
                "Create booking with service detail and synchronized references",
                f"service={kind}; list payload={many}",
                "201; exactly one booking and linked detail; service_ref_ids matches actual detail",
                "bookings/views.py:BookingViewSet.create",
            ),
        )
        for case_index, (kind, many) in enumerate(
            [
                (field_name, model_class)
                for field_name in [1, 2, 3, 4]
                for model_class in [False, True]
            ],
            1,
        )
    ],
)
def test_create_service_booking(
    case_id, kind, many, sample_data, related_services, request_factory
):
    """Verify create service booking.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    details = {
        1: (
            "room_details",
            {
                "room": sample_data.room.pk,
                "check_in": (sample_data.now + timedelta(days=3)).isoformat(),
                "check_out": (sample_data.now + timedelta(days=4)).isoformat(),
                "num_guests": 2,
                "room_count": 1,
            },
        ),
        2: (
            "car_detail",
            {
                "car": related_services.car.pk,
                "pickup_datetime": (sample_data.now + timedelta(days=3)).isoformat(),
                "distance_km": 10,
                "passenger_quantity_booking": 1,
            },
        ),
        3: (
            "flight_detail",
            {
                "flight": related_services.flight.pk,
                "seat_class": "economy",
                "num_passengers": 1,
            },
        ),
        4: (
            "activity_date_detail",
            {
                "activity_date": related_services.activity_date.pk,
                "date_launch": related_services.activity_date.date_launch.isoformat(),
                "adult_quantity_booking": 1,
                "child_quantity_booking": 1,
                "price_adult": 50,
                "price_child": 25,
            },
        ),
    }
    key, value = details[kind]
    state_before_operation = Booking.objects.count()
    response = request_view(
        request_factory,
        BookingViewSet,
        "post",
        {"service_type": kind, key: [value] if many else value},
        sample_data.user,
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 201, response.data
    assert Booking.objects.count() == state_before_operation + 1
    booking = Booking.objects.latest("pk")
    assert booking.user == sample_data.user
    assert len(booking.service_ref_ids) == 1
    related = {
        1: lambda: booking.hotel_detail,
        2: lambda: booking.car_detail,
        3: lambda: booking.flight_details.get(),
        4: lambda: booking.activity_date_detail,
    }[kind]()
    assert related.pk == booking.service_ref_ids[0]
    # CheckDB: link IDs and submitted values must agree with a fresh DB read.
    related.refresh_from_db()
    if kind == 1:
        assert related.room_id == sample_data.room.pk
        assert related.num_guests == 2 and related.room_count == 1
        assert related.total_price == related.final_price == 100
    elif kind == 2:
        assert related.car_id == related_services.car.pk
        assert related.distance_km == 10 and related.passenger_quantity_booking == 1
    elif kind == 3:
        assert related.flight_id == related_services.flight.pk
        assert related.seat_class == "economy" and related.num_passengers == 1
    else:
        assert related.activity_date_id == related_services.activity_date.pk
        assert related.adult_quantity_booking == related.child_quantity_booking == 1
        assert related.price_adult == 50 and related.price_child == 25
    assert response.data["booking_id"] == booking.pk
    assert response.data["booking_code"] == booking.booking_code


@pytest.mark.parametrize(
    "case_id,kind,scenario",
    [
        pytest.param(
            f"B-X{case_index:02}",
            kind,
            scenario,
            id=f"B-X{case_index:02}",
            marks=mark(
                f"B-X{case_index:02}",
                "Bookings",
                "Reject invalid service without inserting orphan booking",
                f"service={kind}; {scenario}",
                "HTTP 400; booking count unchanged",
                "bookings/views.py:BookingViewSet.create",
            ),
        )
        for case_index, (kind, scenario) in enumerate(
            [
                (2, "missing_id"),
                (2, "unknown_id"),
                (2, "missing_driver"),
                (2, "busy_driver"),
                (4, "missing_id"),
                (4, "unknown_id"),
                (4, "no_capacity"),
            ],
            1,
        )
    ],
)
def test_invalid_service_booking_atomicity(
    case_id, kind, scenario, sample_data, related_services, request_factory
):
    """Verify invalid service booking atomicity.

    Arrange: Prepare an unavailable or invalid service and record all pre-request database rows.
    Act: Attempt to create the booking through the real HTTP view.
    Assert and CheckDB: Require a validation error and verify that no orphan booking or unrelated data change remains.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    key = "car_detail" if kind == 2 else "activity_date_detail"
    value = (
        {
            "car": related_services.car.pk,
            "pickup_datetime": (sample_data.now + timedelta(days=3)).isoformat(),
        }
        if kind == 2
        else {
            "activity_date": related_services.activity_date.pk,
            "adult_quantity_booking": 1,
            "child_quantity_booking": 1,
        }
    )
    if scenario == "missing_id":
        value.pop("car" if kind == 2 else "activity_date")
    if scenario == "unknown_id":
        value["car" if kind == 2 else "activity_date"] = 999999
    if scenario == "missing_driver":
        related_services.car.user = None
        related_services.car.save()
    if scenario == "busy_driver":
        sample_data.user.driver_status = "busy"
        sample_data.user.save()
    if scenario == "no_capacity":
        related_services.activity_date.participants_available = 0
        related_services.activity_date.save()
    state_before_operation = Booking.objects.count()
    response = request_view(
        request_factory, BookingViewSet, "post", {"service_type": kind, key: value}
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 400, response.data
    assert (
        Booking.objects.count() == state_before_operation
    ), "Rejected service request left an orphan booking"


@pytest.mark.parametrize(
    "case_id,kind",
    [
        pytest.param(
            f"B-RE{case_index:02}",
            kind,
            id=f"B-RE{case_index:02}",
            marks=mark(
                f"B-RE{case_index:02}",
                "Bookings",
                "Rebook cancelled booking and clone service and guest data",
                f"service={kind}; old booking=CANCELLED",
                "New booking and detail created; old booking/payment marked REBOOKED",
                "bookings/views.py:rebook_booking",
            ),
        )
        for case_index, kind in enumerate([1, 2, 3, 4], 1)
    ],
)
def test_rebook_service(case_id, kind, sample_data, related_services, request_factory):
    """Verify rebook service.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    attach_detail(sample_data, related_services, kind)
    original_booking = sample_data.booking
    original_booking.status = BookingStatus.CANCELLED
    original_booking.save()
    if kind == 2:
        sample_data.user.driver_status = "idle"
        sample_data.user.save()
    response = request_view(
        request_factory,
        BookingViewSet,
        "post",
        action="rebook_booking",
        pk=original_booking.pk,
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 201, response.data
    new = Booking.objects.get(pk=response.data["new_booking_id"])
    original_booking.refresh_from_db()
    sample_data.payment.refresh_from_db()
    assert (
        new.pk != original_booking.pk
        and new.service_type == kind
        and (new.status == BookingStatus.PENDING)
    )
    assert new.guest_info.full_name == "Alice"
    assert (
        original_booking.status == BookingStatus.REBOOKED
        and int(sample_data.payment.status) == PaymentStatus.REBOOKED
    )


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(
            "B-RE05",
            id="B-RE05",
            marks=mark(
                "B-RE05",
                "Bookings",
                "Reject rebooking a pending booking",
                "status=PENDING",
                "400; no new booking",
                "bookings/views.py:rebook_booking",
            ),
        )
    ],
)
def test_rebook_pending_rejected(case_id, sample_data, request_factory):
    """Verify rebook pending rejected.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    count = Booking.objects.count()
    response = request_view(
        request_factory,
        BookingViewSet,
        "post",
        action="rebook_booking",
        pk=sample_data.booking.pk,
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 400
    assert Booking.objects.count() == count


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_create_service_booking
# Test Case ID: B-N01
# Test Case ID: B-N02
# Test Case ID: B-N03
# Test Case ID: B-N04
# Test Case ID: B-N05
# Test Case ID: B-N06
# Test Case ID: B-N07
# Test Case ID: B-N08
# Function: test_invalid_service_booking_atomicity
# Test Case ID: B-X01
# Test Case ID: B-X02
# Test Case ID: B-X03
# Test Case ID: B-X04
# Test Case ID: B-X05
# Test Case ID: B-X06
# Test Case ID: B-X07
# Function: test_rebook_service
# Test Case ID: B-RE01
# Test Case ID: B-RE02
# Test Case ID: B-RE03
# Test Case ID: B-RE04
# Function: test_rebook_pending_rejected
# Test Case ID: B-RE05
