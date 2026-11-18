"""Serializer validation, representation and real database create/update tests."""

from contract_support import checked_read
from datetime import timedelta
from types import SimpleNamespace
import pytest
from django.contrib.auth.models import AnonymousUser
from hotels.models import HotelImage
from hotels.serializers import (
    HotelSimpleSerializer,
    HotelSerializer,
    HotelCreateSerializer,
)
from rooms.models import Room, RoomAmenity, RoomBookingDetail
from rooms.serializers import (
    RoomCreateSerializer,
    RoomSerializer,
    RoomBookingDetailCreateSerializer,
)
from bookings.models import Booking, GuestInfo, RefundPolicy
from bookings.serializers import (
    BookingSerializer,
    GuestInfoSerializer,
    RefundPolicySerializer,
)
from payments.serializers import PaymentSerializer, PaymentCreateSerializer
from promotions.models import RoomPromotion
from promotions.serializers import (
    PromotionCreateSerializer,
    PromotionSerializer,
    RoomPromotionSerializer,
    CarPromotionSerializer,
    FlightPromotionSerializer,
    ActivityPromotionSerializer,
)
from conftest import case
from contract_support import database_snapshot


@pytest.mark.parametrize(
    "case_id",
    [
        case(
            f"H-S{case_index:02}",
            "Hotels",
            objective,
            input_description,
            expected_description,
            "hotels/serializers.py",
        )
        for case_index, objective, input_description, expected_description in [
            (1, "Return null thumbnail without images", "No images", "thumbnail=None"),
            (2, "Return first hotel image", "Image=first.png", "thumbnail=first.png"),
            (3, "Serialize hotel with no owner", "owner=None", "owner=None"),
            (
                4,
                "Serialize hotel owner",
                "Owner tester",
                "Nested owner username=tester",
            ),
            (
                5,
                "Create hotel using valid city",
                "Valid city and name",
                "Row created with correct city and name",
            ),
        ]
    ],
)
def test_hotel_serializers(case_id, sample_data):
    """Verify hotel serializers.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    if case_id == "H-S01":
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert (
            checked_read(lambda: HotelSimpleSerializer(sample_data.hotel).data)[
                "thumbnail"
            ]
            is None
        )
    elif case_id == "H-S02":
        HotelImage.objects.create(hotel=sample_data.hotel, image="first.png")
        assert (
            checked_read(lambda: HotelSimpleSerializer(sample_data.hotel).data)[
                "thumbnail"
            ]
            == "first.png"
        )
    elif case_id == "H-S03":
        sample_data.hotel.owner = None
        assert (
            checked_read(lambda: HotelSerializer(sample_data.hotel).data)["owner"]
            is None
        )
    elif case_id == "H-S04":
        assert (
            checked_read(lambda: HotelSerializer(sample_data.hotel).data)["owner"][
                "username"
            ]
            == "tester"
        )
    elif case_id == "H-S05":
        serializer = HotelCreateSerializer(
            data={"city": sample_data.city.pk, "name": "New Hotel"}
        )
        assert checked_read(lambda: serializer.is_valid()), serializer.errors
        resource = serializer.save()
        resource.refresh_from_db()
        assert resource.name == "New Hotel" and resource.city == sample_data.city


@pytest.mark.parametrize(
    "case_id",
    [
        case(
            f"R-S{case_index:02}",
            "Rooms",
            objective,
            input_description,
            expected_description,
            "rooms/serializers.py:RoomCreateSerializer",
        )
        for case_index, objective, input_description, expected_description in [
            (
                1,
                "Create room with default availability dates",
                "Dates omitted; amenities WiFi and Pool",
                "Today to today+365; both amenities persisted",
            ),
            (
                2,
                "Preserve explicit room dates",
                "Tomorrow to tomorrow+7",
                "Supplied dates persisted",
            ),
            (
                3,
                "Return no promotion fields",
                "Room without campaign",
                "promotion=None; has_promotion=False",
            ),
            (
                4,
                "Return active room promotion",
                "Linked 10% campaign",
                "promotion percent=10; has_promotion=True",
            ),
        ]
    ],
)
def test_room_creation_serializers(case_id, sample_data):
    """Verify room creation serializers.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    if case_id in ("R-S01", "R-S02"):
        payload = {
            "hotel": sample_data.hotel.pk,
            "room_type": "Twin",
            "amenities_data": [{"name": "WiFi"}, {"name": "Pool"}],
        }
        if case_id == "R-S02":
            payload.update(
                start_date=(sample_data.now + timedelta(days=1)).date().isoformat(),
                end_date=(sample_data.now + timedelta(days=8)).date().isoformat(),
            )
        serializer = RoomCreateSerializer(data=payload)
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert checked_read(lambda: serializer.is_valid()), serializer.errors
        room = serializer.save()
        room.refresh_from_db()
        offset = 0 if case_id == "R-S01" else 1
        assert room.start_date == (sample_data.now + timedelta(days=offset)).date()
        assert (
            room.end_date
            == (
                sample_data.now + timedelta(days=365 if case_id == "R-S01" else 8)
            ).date()
        )
        assert set(room.amenities.values_list("name", flat=True)) == {"WiFi", "Pool"}
        assert serializer.get_has_promotion(room) is False
        assert serializer.get_promotion(room) is None
    else:
        if case_id == "R-S04":
            RoomPromotion.objects.create(
                room=sample_data.room, promotion=sample_data.promotion
            )
        serialized_output = checked_read(lambda: RoomSerializer(sample_data.room).data)
        assert serialized_output["has_promotion"] == (case_id == "R-S04")
        if case_id == "R-S03":
            assert serialized_output["promotion"] is None
        else:
            assert serialized_output["promotion"]["discount_percent"] == 10


ROOM_VALIDATION = [
    ("R-V01", "Valid future interval", 2, 4, 2, 1, True),
    ("R-V02", "Equal check-in and check-out", 2, 2, 2, 1, False),
    ("R-V03", "Reversed interval", 4, 2, 2, 1, False),
    ("R-V04", "Past check-in", -1, 2, 2, 1, False),
    ("R-V05", "Capacity exceeded", 2, 4, 4, 1, False),
    ("R-V06", "Inventory exceeded", 2, 4, 2, 11, False),
    ("R-V07", "Zero guests rejected", 2, 4, 0, 1, False),
    ("R-V08", "Negative guests rejected", 2, 4, -1, 1, False),
    ("R-V09", "Zero rooms rejected", 2, 4, 2, 0, False),
]


@pytest.mark.parametrize(
    "case_id,start,end,guests,count,valid",
    [
        pytest.param(
            case_id,
            start,
            end,
            guests,
            count,
            valid,
            id=case_id,
            marks=pytest.mark.case(
                module="Rooms",
                objective=resource,
                inputs=f"check-in=now+{start}d; check-out=now+{end}d; guests={guests}; rooms={count}",
                expected=f"Validation accepted={valid}; invalid input writes no rows",
                target="rooms/serializers.py:RoomBookingDetailCreateSerializer.validate",
                technique="Boundary values; negative inputs; database non-mutation",
            ),
        )
        for case_id, resource, start, end, guests, count, valid in ROOM_VALIDATION
    ],
)
def test_room_booking_validation(
    case_id, start, end, guests, count, valid, sample_data
):
    """Verify room booking validation.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    state_before_operation = database_snapshot()
    serializer = RoomBookingDetailCreateSerializer(
        data={
            "room": sample_data.room.pk,
            "check_in": sample_data.now + timedelta(days=start),
            "check_out": sample_data.now + timedelta(days=end),
            "num_guests": guests,
            "room_count": count,
        }
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert (
        checked_read(lambda: serializer.is_valid()) == valid
    ), f"Expected accepted={valid}; observed errors={serializer.errors}"
    assert database_snapshot() == state_before_operation
    if valid:
        assert serializer.validated_data["room"].pk == sample_data.room.pk
        assert serializer.validated_data["num_guests"] == guests
        assert serializer.validated_data["room_count"] == count
    else:
        expected_messages = {
            "R-V02": "Check-out must be after check-in",
            "R-V03": "Check-out must be after check-in",
            "R-V04": "Check-in cannot be in the past",
            "R-V05": "Number of guests (4) exceeds room capacity (3)",
            "R-V06": "Only 10 rooms available",
            "R-V07": "Guest count must be positive",
            "R-V08": "Guest count must be positive",
            "R-V09": "Room count must be positive",
        }
        assert expected_messages[case_id] in str(serializer.errors)


BOOKING_SERIALIZERS = [
    (
        "B-S01",
        "Create anonymous guest booking",
        "Anonymous user and guest",
        "User NULL; guest row linked",
    ),
    (
        "B-S02",
        "Assign authenticated request user",
        "Authenticated tester",
        "Booking user=tester",
    ),
    (
        "B-S03",
        "Create without request or guest",
        "Only service_type",
        "Booking persisted, no guest row",
    ),
    (
        "B-S04",
        "Update booking and existing guest",
        "Change total and guest name",
        "Same guest ID; new name and total",
    ),
    (
        "B-S05",
        "Create missing guest on update",
        "Booking without guest",
        "One guest created and linked",
    ),
    (
        "B-S06",
        "Update booking without guest data",
        "total_price=250",
        "Price persisted; no guest created",
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
            "bookings/serializers.py:BookingSerializer",
        )
        for case_index, objective, input_description, expected_description in BOOKING_SERIALIZERS
    ],
)
def test_booking_serializers(case_id, sample_data):
    """Verify booking serializers.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    guest = {"full_name": "Alice", "email": "alice@example.com", "phone": "123"}
    if case_id in ("B-S01", "B-S02", "B-S03"):
        context = (
            {}
            if case_id == "B-S03"
            else {
                "request": SimpleNamespace(
                    user=sample_data.user if case_id == "B-S02" else AnonymousUser()
                )
            }
        )
        payload = {"service_type": 1}
        if case_id == "B-S01":
            payload["guest_info"] = guest
        serializer = BookingSerializer(data=payload, context=context)
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert checked_read(lambda: serializer.is_valid()), serializer.errors
        booking = serializer.save()
        booking.refresh_from_db()
        assert booking.service_type == 1
        assert booking.user_id == (sample_data.user.pk if case_id == "B-S02" else None)
        assert GuestInfo.objects.filter(booking=booking).exists() == (
            case_id == "B-S01"
        )
        if case_id == "B-S01":
            persisted_guest = GuestInfo.objects.get(booking=booking)
            assert persisted_guest.full_name == "Alice"
            assert persisted_guest.email == "alice@example.com"
            assert persisted_guest.phone == "123"
    else:
        original_guest_id = None
        if case_id == "B-S04":
            original_guest_id = GuestInfo.objects.create(
                booking=sample_data.booking, **guest
            ).pk
        payload = {"total_price": 250}
        if case_id != "B-S06":
            payload["guest_info"] = {**guest, "full_name": "Updated Alice"}
        serializer = BookingSerializer(sample_data.booking, data=payload, partial=True)
        assert checked_read(lambda: serializer.is_valid()), serializer.errors
        serializer.save()
        sample_data.booking.refresh_from_db()
        assert sample_data.booking.total_price == 250
        if case_id != "B-S06":
            assert (
                GuestInfo.objects.get(booking=sample_data.booking).full_name
                == "Updated Alice"
            )
            persisted_guest = GuestInfo.objects.get(booking=sample_data.booking)
            assert (
                persisted_guest.email == "alice@example.com"
                and persisted_guest.phone == "123"
            )
            if original_guest_id is not None:
                assert persisted_guest.pk == original_guest_id
        else:
            assert not GuestInfo.objects.filter(booking=sample_data.booking).exists()


@pytest.mark.parametrize(
    "case_id,service,field",
    [
        pytest.param(
            f"B-SR{case_index:02}",
            service,
            field,
            id=f"B-SR{case_index:02}",
            marks=pytest.mark.case(
                module="Bookings",
                objective="Select service detail fields and omit unrelated detail fields",
                inputs=f"service_type={service}; reference IDs empty",
                expected=f"Relevant detail field {field}; unrelated fields absent",
                target="bookings/serializers.py:BookingSerializer.to_representation",
                technique="Decision table",
            ),
        )
        for case_index, (service, field) in enumerate(
            [
                (1, "room_details"),
                (2, "car_detail"),
                (3, "flight_detail"),
                (4, "activity_date_detail"),
                (5, None),
            ],
            1,
        )
    ],
)
def test_booking_representation(case_id, service, field, sample_data):
    """Verify booking representation.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    booking = sample_data.booking
    booking.service_type = service
    serialized_output = checked_read(lambda: BookingSerializer(booking).data)
    assert serialized_output["id"] == booking.pk
    assert serialized_output["service_type"] == service
    all_fields = {"room_details", "car_detail", "flight_detail", "activity_date_detail"}
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert all_fields.intersection(serialized_output) == (
        {field} if field else all_fields
    )
    booking.service_ref_ids = [999999]
    serializer = BookingSerializer()
    method = {
        1: serializer.get_room_details,
        2: serializer.get_car_detail,
        3: serializer.get_flight_detail,
        4: serializer.get_activity_date_detail,
    }.get(service)
    if method:
        assert method(booking) == []


@pytest.mark.parametrize(
    "case_id",
    [
        case(
            "P-S01",
            "Payments",
            "Serialize booking and validate payment FK",
            "Existing booking; amount=150",
            "Nested booking ID correct; payment amount persisted",
            "payments/serializers.py",
        )
    ],
)
def test_payment_serializers(case_id, sample_data):
    """Verify payment serializers.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert (
        checked_read(lambda: PaymentSerializer(sample_data.payment).data)["booking"][
            "id"
        ]
        == sample_data.booking.pk
    )
    serializer = PaymentCreateSerializer(
        data={"booking": sample_data.booking.pk, "method": 1, "amount": 150}
    )
    assert checked_read(lambda: serializer.is_valid()), serializer.errors
    payment = serializer.save()
    payment.refresh_from_db()
    assert payment.amount == 150
    assert payment.booking_id == sample_data.booking.pk
    assert payment.method == 1


@pytest.mark.parametrize(
    "case_id,kind,key,present",
    [
        pytest.param(
            f"PR-S{case_index:02}",
            kind,
            key,
            present,
            id=f"PR-S{case_index:02}",
            marks=pytest.mark.case(
                module="Promotions",
                objective=f"Validate required {key} collection for {kind} campaign",
                inputs=f"type={kind}; {key} present={present}",
                expected=f"Accepted={present}",
                target="promotions/serializers.py:PromotionCreateSerializer.validate",
                technique="Decision table; required fields",
            ),
        )
        for case_index, (kind, key, present) in enumerate(
            [
                (field_name, key, parameter_value)
                for field_name, key in [
                    ("hotel", "rooms"),
                    ("flight", "flights"),
                    ("activity", "actDates"),
                    ("car", "cars"),
                ]
                for parameter_value in [False, True]
            ],
            1,
        )
    ],
)
def test_promotion_create_validation(case_id, kind, key, present, sample_data):
    """Verify promotion create validation.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    payload = {
        "type": kind,
        "title": "Sale",
        "start_date": sample_data.now,
        "end_date": sample_data.now + timedelta(days=2),
    }
    if present:
        payload[key] = [{"id": 1}]
    serializer = PromotionCreateSerializer(data=payload)
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert checked_read(lambda: serializer.is_valid()) == present, serializer.errors
    if present:
        assert serializer.validated_data["type"] == kind
        assert serializer.validated_data[key] == [{"id": 1}]
    else:
        assert f"{key} is required for {kind} promotion" in str(serializer.errors)


@pytest.mark.parametrize(
    "case_id,kind,field",
    [
        pytest.param(
            f"PR-SR{case_index:02}",
            kind,
            field,
            id=f"PR-SR{case_index:02}",
            marks=pytest.mark.case(
                module="Promotions",
                objective="Retain only campaign links matching service type",
                inputs=f"promotion_type={kind}",
                expected=(
                    f"Only {field} links retained"
                    if field
                    else "All link fields retained for unknown type"
                ),
                target="promotions/serializers.py:PromotionSerializer.to_representation",
                technique="Decision table",
            ),
        )
        for case_index, (kind, field) in enumerate(
            [
                (1, "room_promotions"),
                (2, "flight_promotions"),
                (3, "activity_promotions"),
                (4, "car_promotions"),
                (99, None),
            ],
            1,
        )
    ],
)
def test_promotion_representation(case_id, kind, field, sample_data):
    """Verify promotion representation.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    promotion = sample_data.promotion
    promotion.promotion_type = kind
    serialized_output = checked_read(lambda: PromotionSerializer(promotion).data)
    fields = {
        "room_promotions",
        "flight_promotions",
        "activity_promotions",
        "car_promotions",
    }
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert fields.intersection(serialized_output) == ({field} if field else fields)


@pytest.mark.parametrize(
    "case_id",
    [
        case(
            "PR-D01",
            "Promotions",
            "Apply child override and campaign fallback across all services",
            "Override 0 then 25; campaign percent=10, amount=30",
            "Fallback=10/30 then override=25/25",
            "promotions/serializers.py:effective discount methods",
        )
    ],
)
def test_effective_discounts(case_id, sample_data):
    """Verify effective discounts.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    sample_data.promotion.discount_amount = 30
    for serializer_class in [
        RoomPromotionSerializer,
        CarPromotionSerializer,
        FlightPromotionSerializer,
        ActivityPromotionSerializer,
    ]:
        serializer = serializer_class()
        resource = SimpleNamespace(
            promotion=sample_data.promotion, discount_percent=0, discount_amount=0
        )
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert (
            checked_read(lambda: serializer.get_effective_discount_percent(resource))
            == 10
        )
        assert (
            checked_read(lambda: serializer.get_effective_discount_amount(resource))
            == 30
        )
        resource.discount_percent = 25
        resource.discount_amount = 25
        assert (
            checked_read(lambda: serializer.get_effective_discount_percent(resource))
            == 25
        )
        assert (
            checked_read(lambda: serializer.get_effective_discount_amount(resource))
            == 25
        )


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_hotel_serializers
# Test Case ID: H-S01
# Test Case ID: H-S02
# Test Case ID: H-S03
# Test Case ID: H-S04
# Test Case ID: H-S05
# Function: test_room_creation_serializers
# Test Case ID: R-S01
# Test Case ID: R-S02
# Test Case ID: R-S03
# Test Case ID: R-S04
# Function: test_room_booking_validation
# Test Case ID: R-V01
# Test Case ID: R-V02
# Test Case ID: R-V03
# Test Case ID: R-V04
# Test Case ID: R-V05
# Test Case ID: R-V06
# Test Case ID: R-V07
# Test Case ID: R-V08
# Test Case ID: R-V09
# Function: test_booking_serializers
# Test Case ID: B-S01
# Test Case ID: B-S02
# Test Case ID: B-S03
# Test Case ID: B-S04
# Test Case ID: B-S05
# Test Case ID: B-S06
# Function: test_booking_representation
# Test Case ID: B-SR01
# Test Case ID: B-SR02
# Test Case ID: B-SR03
# Test Case ID: B-SR04
# Test Case ID: B-SR05
# Function: test_payment_serializers
# Test Case ID: P-S01
# Function: test_promotion_create_validation
# Test Case ID: PR-S01
# Test Case ID: PR-S02
# Test Case ID: PR-S03
# Test Case ID: PR-S04
# Test Case ID: PR-S05
# Test Case ID: PR-S06
# Test Case ID: PR-S07
# Test Case ID: PR-S08
# Function: test_promotion_representation
# Test Case ID: PR-SR01
# Test Case ID: PR-SR02
# Test Case ID: PR-SR03
# Test Case ID: PR-SR04
# Test Case ID: PR-SR05
# Function: test_effective_discounts
# Test Case ID: PR-D01
