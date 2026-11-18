"""Independent HTTP/data oracles and report metadata shared by the test suite.

The oracles read prepared database rows directly and apply the declared API
filter contract in Python. They never call the view's get_queryset() or derive
an expected value from the response under test.
"""

from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
import json
import math

CURRENT_CASE = ContextVar("current_pytest_case", default=None)


def database_snapshot():
    """Capture every registered table, including automatically created M2M tables.

    Values are sorted by primary key, so comparison detects changed fields,
    inserted/deleted rows and relation-table changes rather than count alone.
    """
    from django.apps import apps

    return {
        model._meta.label: list(model.objects.order_by("pk").values_list())
        for model in apps.get_models(include_auto_created=True)
        if model._meta.managed and not model._meta.proxy
    }


def checked_read(operation):
    """Execute a model/serializer read and assert immediate DB non-mutation.

    This verifies the read before test cleanup. Rollback alone would conceal an
    unintended write and therefore cannot substitute for this CheckDB assertion.
    """
    state_before = database_snapshot()
    result = operation()
    assert (
        database_snapshot() == state_before
    ), "A read or validation operation changed persisted database values."
    return result


def publish_contract(expected, *, inputs=None, response_fields=None):
    """Declare expected values before invoking the real operation under test."""
    case_item = CURRENT_CASE.get()
    if case_item is None:
        return
    marker = case_item.get_closest_marker("case")
    marker.kwargs["expected"] = expected
    if inputs is not None:
        marker.kwargs["inputs"] = json.dumps(inputs, default=str, ensure_ascii=True)
    if response_fields is not None:
        marker.kwargs["expected_response_fields"] = response_fields


def values_at(record, dotted_path):
    """Read related values, expanding reverse relationships without view logic."""
    values = [record]
    for part in dotted_path.split("."):
        expanded = []
        for value in values:
            try:
                related = getattr(value, part)
            except (AttributeError, LookupError):
                continue
            if hasattr(related, "all"):
                expanded.extend(related.all())
            elif related is not None:
                expanded.append(related)
        values = expanded
    return values


def compare_value(actual, expected):
    """Normalize JSON numeric/date representations while preserving their value."""
    if isinstance(expected, (int, float, Decimal)) and not isinstance(expected, bool):
        return actual is not None and float(actual) == float(expected)
    if isinstance(expected, str) and expected.isdigit() and isinstance(actual, int):
        return str(actual) == expected
    if isinstance(expected, (date, datetime)):
        parsed = datetime.fromisoformat(str(actual).replace("Z", "+00:00"))
        return (
            parsed == expected
            if isinstance(expected, datetime)
            else parsed.date() == expected
        )
    return actual == expected


MODEL_NAMES = {
    "HotelListView": ("hotels", "Hotel"),
    "HotelByCityView": ("hotels", "Hotel"),
    "HotelSearchView": ("hotels", "Hotel"),
    "HotelDetailView": ("hotels", "Hotel"),
    "RoomListView": ("rooms", "Room"),
    "RoomAdminListView": ("rooms", "Room"),
    "RoomSearchView": ("rooms", "Room"),
    "RoomDetailView": ("rooms", "Room"),
    "RoomAmenityListView": ("rooms", "RoomAmenity"),
    "RoomAmenityDetailView": ("rooms", "RoomAmenity"),
    "RoomBookingDetailView": ("rooms", "RoomBookingDetail"),
    "BookingViewSet": ("bookings", "Booking"),
    "RefundPolicyViewSet": ("bookings", "RefundPolicy"),
    "PaymentViewSet": ("payments", "Payment"),
    "PaymentListView": ("payments", "Payment"),
    "PaymentDetailView": ("payments", "Payment"),
    "PaymentListOverviewView": ("payments", "Payment"),
    "PromotionListCreateView": ("promotions", "Promotion"),
    "PromotionListAdminView": ("promotions", "Promotion"),
    "PromotionDetailView": ("promotions", "Promotion"),
    "RoomPromotionListAdminView": ("promotions", "RoomPromotion"),
    "RoomPromotionAdminDetailView": ("promotions", "RoomPromotion"),
    "CarPromotionListAdminView": ("promotions", "CarPromotion"),
    "CarPromotionAdminDetailView": ("promotions", "CarPromotion"),
    "FlightPromotionListAdminView": ("promotions", "FlightPromotion"),
    "FlightPromotionAdminDetailView": ("promotions", "FlightPromotion"),
    "ActivityPromotionListAdminView": ("promotions", "ActivityPromotion"),
    "ActivityPromotionAdminDetailView": ("promotions", "ActivityPromotion"),
}
RESPONSE_FIELDS = {
    "Hotel": ["id", "name", "avg_star", "min_price"],
    "Room": [
        "id",
        "room_type",
        "price_per_night",
        "price_per_day",
        "adults_capacity",
        "children_capacity",
        "available_rooms",
        "available",
        "stay_type",
    ],
    "RoomAmenity": ["id", "name"],
    "RoomBookingDetail": [
        "id",
        "room_type",
        "room_count",
        "num_guests",
        "total_price",
        "discount_amount",
        "final_price",
    ],
    "Booking": [
        "id",
        "booking_code",
        "service_type",
        "status",
        "payment_status",
        "total_price",
        "discount_amount",
        "final_price",
    ],
    "RefundPolicy": [
        "id",
        "name",
        "service_type",
        "policy_type",
        "is_active",
        "refund_percentage",
        "refund_amount",
    ],
    "Payment": ["id", "amount", "method", "status"],
    "Promotion": [
        "id",
        "title",
        "promotion_type",
        "is_active",
        "discount_percent",
        "discount_amount",
    ],
    "RoomPromotion": ["id", "discount_percent", "discount_amount"],
    "CarPromotion": ["id", "discount_percent", "discount_amount"],
    "FlightPromotion": ["id", "discount_percent", "discount_amount"],
    "ActivityPromotion": ["id", "discount_percent", "discount_amount"],
}


def model_projection(record):
    """Expected API field values from the independent persisted record."""
    return {
        field: getattr(record, field)
        for field in RESPONSE_FIELDS[record.__class__.__name__]
    }


def _filter_path(model_name, key):
    """Map public query names to the documented domain relationship."""
    if model_name == "Hotel":
        return {"cityId": "city_id", "city_id": "city_id", "ownerId": "owner_id"}.get(
            key
        )
    if model_name == "Room":
        return {
            "hotel_id": "hotel_id",
            "owner_id": "hotel.owner_id",
            "hotel_name": "hotel.name",
            "adults": "adults_capacity",
            "children": "children_capacity",
        }.get(key)
    if model_name == "RoomAmenity":
        return {
            "room_id": "room_id",
            "hotel_id": "room.hotel_id",
            "owner_id": "room.hotel.owner_id",
        }.get(key)
    if model_name == "Payment":
        return {
            "owner_hotel_id": "booking.hotel_detail.owner_hotel_id",
            "hotel_id": "booking.hotel_detail.room.hotel_id",
            "room_id": "booking.hotel_detail.room_id",
            "event_organizer_activity_id": "booking.activity_date_detail.event_organizer_activity_id",
            "activity_id": "booking.activity_date_detail.activity_date.activity_package.activity_id",
            "activity_package_id": "booking.activity_date_detail.activity_date.activity_package_id",
            "activity_date_id": "booking.activity_date_detail.activity_date_id",
            "driver_id": "booking.car_detail.driver_id",
            "car_id": "booking.car_detail.car_id",
            "car_booking_status": "booking.car_detail.status",
            "airline_id": "booking.flight_details.flight.airline_id",
            "aircraft_id": "booking.flight_details.flight.aircraft_id",
            "flight_id": "booking.flight_details.flight_id",
            "flight_operations_staff_id": "booking.flight_details.flight.airline.flight_operations_staff_id",
            "booking__service_ref_id": "booking.service_ref_ids",
            "date_launch_activity": "booking.activity_date_detail.date_launch",
            "time_checkin_room": "booking.hotel_detail.check_in",
            "time_checkout_room": "booking.hotel_detail.check_out",
            "pickup_datetime_car": "booking.car_detail.pickup_datetime",
            "dropoff_datetime_car": "booking.car_detail.dropoff_datetime",
            "date_launch_activity": "booking.activity_date_detail.date_launch",
            "flight_leg_departure": "booking.flight_details.flight.legs.departure_time",
            "flight_leg_arrival": "booking.flight_details.flight.legs.arrival_time",
            "total_price": "booking.total_price",
            "discount_amount": "booking.discount_amount",
            "final_price": "booking.final_price",
            "refund_amount": "booking.refund_amount",
        }.get(key)
    if model_name.endswith("Promotion"):
        return {
            "owner_id": "room.hotel.owner_id",
            "driver_id": "car.user_id",
            "flight_operations_staff_id": "flight.airline.flight_operations_staff_id",
            "event_organizer_id": "activity_date.activity_package.activity.event_organizer_id",
        }.get(key)
    return None


def _matches(record, key, raw_value, view_name):
    """Evaluate one expected filter in Python over stored fixture values."""
    model_name = record.__class__.__name__
    if key in {
        "current",
        "statistic_by",
        "page",
        "pageSize",
        "sort",
        "recommended",
        "startDate",
        "endDate",
        "start_date",
        "end_date",
    }:
        return True
    if key == "email" and model_name == "Booking":
        return raw_value in values_at(record, "user.email") + values_at(
            record, "guest_info.email"
        )
    if key in {"adult", "child", "room", "stay_type"} and model_name == "Hotel":
        room_values = values_at(record, "rooms")
        if key == "stay_type":
            return any(room.stay_type == raw_value for room in room_values)
        try:
            quantity = int(raw_value)
        except ValueError:
            return True
        if key == "room":
            return sum(room.available_rooms for room in room_values) >= quantity
        return any(
            getattr(room, "adults_capacity" if key == "adult" else "children_capacity")
            >= quantity
            for room in room_values
        )
    if key == "min_date" and model_name == "Promotion":
        return record.end_date.date() >= date.fromisoformat(raw_value)
    if key in {"min_date", "max_date"} and model_name == "Payment":
        compare_date = record.created_at.date()
        return (
            compare_date >= date.fromisoformat(raw_value)
            if key == "min_date"
            else compare_date <= date.fromisoformat(raw_value)
        )
    # Room price ranges are specific to their stay type.
    if (
        model_name == "Room"
        and key.endswith("price_per_night")
        and record.stay_type != "overnight"
    ):
        return False
    if (
        model_name == "Room"
        and key.endswith("price_per_day")
        and record.stay_type != "dayuse"
    ):
        return False
    lower = key.startswith("min_")
    upper = key.startswith("max_")
    bare_key = key[4:] if lower or upper else key
    bare_key = (
        {"avg_price": "min_price"}.get(bare_key, bare_key)
        if model_name == "Hotel"
        else bare_key
    )
    path = _filter_path(model_name, bare_key) or bare_key.replace("__", ".")
    candidate_values = values_at(record, path)
    if not candidate_values:
        # Unsupported scalar search on an existing field with NULL has no match.
        return False
    for candidate in candidate_values:
        if isinstance(candidate, list):
            if str(raw_value) in [str(value) for value in candidate]:
                return True
            continue
        if isinstance(candidate, (datetime, date)):
            try:
                target = date.fromisoformat(str(raw_value)[:10])
            except ValueError:
                return True
            candidate_date = (
                candidate.date() if isinstance(candidate, datetime) else candidate
            )
            if (
                candidate_date >= target
                if lower
                else candidate_date <= target if upper else candidate_date == target
            ):
                return True
        elif isinstance(candidate, bool):
            if candidate == (str(raw_value).lower() in ("true", "1")):
                return True
        elif isinstance(candidate, (int, float, Decimal)):
            try:
                target = float(raw_value)
            except (TypeError, ValueError):
                if key in ("cityId", "ownerId") or (
                    model_name == "Room" and key in ("hotel_id", "owner_id")
                ):
                    return False
                return True
            if bare_key == "avg_star" and not lower and not upper:
                if int(target) <= float(candidate) < int(target) + 1:
                    return True
            elif lower and float(candidate) >= target:
                return True
            elif upper and float(candidate) <= target:
                return True
            elif key in ("adults", "children") and float(candidate) >= target:
                return True
            elif not lower and not upper and float(candidate) == target:
                return True
        elif str(raw_value).lower() in str(candidate).lower():
            return True
    return False


def expected_read_contract(view_class, payload, route_kwargs, user, action):
    """Compute output records before calling the view; expose exact expected IDs."""
    from django.apps import apps
    from django.utils import timezone

    view_name = view_class.__name__
    if view_name not in MODEL_NAMES:
        return None
    application_name, model_name = MODEL_NAMES[view_name]
    model = apps.get_model(application_name, model_name)
    records = list(model.objects.order_by("pk"))
    requested_id = route_kwargs.get("pk")
    is_detail = requested_id is not None and (
        action == "retrieve" or "DetailView" in view_name
    )
    if is_detail:
        records = [record for record in records if record.pk == requested_id]
    if view_name == "HotelByCityView":
        try:
            city_id = int(route_kwargs.get("city_id", 0))
        except (TypeError, ValueError):
            city_id = 0
        records = [record for record in records if record.city_id == city_id]
    if view_name == "RoomListView":
        today = timezone.now().date()
        records = [
            record
            for record in records
            if record.available_rooms > 0
            and record.start_date
            and record.end_date
            and record.start_date <= today <= record.end_date
        ]
    if view_name == "RoomSearchView":
        from hotels.models import Hotel

        hotel = (
            Hotel.objects.filter(name__icontains=payload.get("hotel_name", ""))
            .order_by("pk")
            .first()
        )
        records = [
            record
            for record in records
            if hotel and record.hotel_id == hotel.pk and record.available_rooms > 0
        ]
    for key, raw_value in payload.items():
        if not is_detail and raw_value not in ("", None):
            records = [
                record
                for record in records
                if _matches(record, key, str(raw_value), view_name)
            ]
    if model_name == "Hotel" and payload.get("startDate") and payload.get("endDate"):
        try:
            start = date.fromisoformat(payload["startDate"])
            end = date.fromisoformat(payload["endDate"])
            if start <= end:
                records = [
                    record
                    for record in records
                    if any(
                        room.start_date
                        and room.end_date
                        and room.start_date <= start
                        and room.end_date >= end
                        for room in record.rooms.all()
                    )
                ]
        except ValueError:
            pass
    sort_expression = payload.get("sort", "")
    for expression in reversed(str(sort_expression).split(",")):
        if "-" in expression:
            field, direction = expression.rsplit("-", 1)
            if field in {field.name for field in model._meta.fields}:
                records.sort(
                    key=lambda record: getattr(record, field),
                    reverse=direction == "desc",
                )
    if (
        view_name in ("BookingViewSet", "RefundPolicyViewSet", "PaymentListView")
        and not sort_expression
    ):
        records.reverse()
    if model_name == "Hotel" and payload.get("recommended"):
        records.sort(key=lambda hotel: hotel.total_weighted_score, reverse=True)
    total = len(records)
    if (
        not is_detail
        and view_name
        not in ("RoomSearchView", "HotelByCityView", "PaymentListOverviewView")
        and getattr(view_class, "pagination_class", None)
    ):
        try:
            page_size = int(payload.get("pageSize", 10))
            page_size = max(1, page_size)
        except (ValueError, TypeError):
            page_size = 10
        try:
            page_number = max(1, int(payload.get("current", 1)))
        except (ValueError, TypeError):
            page_number = 1
        records = records[(page_number - 1) * page_size : page_number * page_size]
    return {
        "view_name": view_name,
        "model_name": model_name,
        "records": records,
        "total": total,
        "is_detail": is_detail,
        "not_found": is_detail and not records,
    }


def describe_read_contract(contract, payload):
    """English output description names exact fields and expected record IDs."""
    records = contract["records"]
    if contract["not_found"]:
        return "HTTP 404 with a not-found error object. No resource data is returned; every existing database row and field remains unchanged."
    if contract["view_name"] == "PaymentListOverviewView":
        total = sum(float(record.amount) for record in records)
        return f"HTTP 200. data.total_revenue={total:g}; the period revenue series sums to {total:g} across {len(records)} matching payment rows. Labels, revenues, customer counts and order counts have equal lengths; all DB rows remain unchanged."
    projection = []
    for record in records:
        fields = model_projection(record)
        projection.append(dict(list(fields.items())[:4]))
    label = "data.rooms" if contract["view_name"] == "RoomSearchView" else "data"
    return f"HTTP 200. {label} IDs={[record.pk for record in records]} in this order; expected record fields={json.dumps(projection,default=str,ensure_ascii=True)}. Only records matching {json.dumps(payload,default=str)} are returned. All database rows and fields remain unchanged."


def assert_read_response(contract, response):
    """Check IDs and values against the precomputed DB projection, not status alone."""
    if contract is None:
        return
    if contract["not_found"]:
        assert (
            response.status_code == 404
        ), f"Expected HTTP 404; observed HTTP {response.status_code}: {response.data}"
        return
    assert (
        response.status_code == 200
    ), f"Expected HTTP 200; observed HTTP {response.status_code}: {response.data}"
    if contract["view_name"] == "PaymentListOverviewView":
        expected_total = sum(float(record.amount) for record in contract["records"])
        output = response.data["data"]
        assert (
            output["total_revenue"] == expected_total
        ), f'Expected total_revenue={expected_total}; observed {output["total_revenue"]}'
        assert sum(output["revenues"]) == expected_total
        assert (
            len(output["labels"])
            == len(output["revenues"])
            == len(output["customers"])
            == len(output["orders"])
        )
        return
    body = response.data
    rows = (
        body.get("data", body.get("results", body)) if isinstance(body, dict) else body
    )
    if contract["view_name"] == "RoomSearchView":
        rows = rows["rooms"]
    if contract["is_detail"]:
        rows = [rows]
    assert isinstance(rows, list), f"Expected a resource list; observed {rows!r}"
    expected_ids = [record.pk for record in contract["records"]]
    actual_ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
    assert (
        actual_ids == expected_ids
    ), f"Expected IDs {expected_ids}; observed IDs {actual_ids}"
    for output_row, record in zip(rows, contract["records"]):
        for field, expected_value in model_projection(record).items():
            # RoomSearch uses its documented compact names instead of RoomSerializer.
            output_field = (
                {"room_type": "name", "price_per_night": "price"}.get(field, field)
                if contract["view_name"] == "RoomSearchView"
                else field
            )
            if contract["view_name"] == "RoomSearchView" and output_field not in (
                "id",
                "name",
                "price",
                "available_rooms",
                "adults_capacity",
                "children_capacity",
            ):
                continue
            assert (
                output_field in output_row
            ), f"Missing expected field {output_field}: {output_row}"
            assert compare_value(
                output_row[output_field], expected_value
            ), f"Expected {output_field}={expected_value!r}; observed {output_row[output_field]!r}"


def seed_contrast_records(sample_data):
    """Create a second independent hotel/room/booking/payment/campaign graph.

    Distinct owner, city, price, stay type and service type prevent a filter that
    always returns every row from passing the read-contract checks.
    """
    from accounts.models import CustomUser
    from countries.models import Country
    from cities.models import City
    from hotels.models import Hotel
    from rooms.models import Room, RoomAmenity
    from bookings.models import Booking, RefundPolicy
    from payments.models import Payment
    from promotions.models import Promotion, RoomPromotion
    from django.utils import timezone
    from datetime import timedelta

    owner = CustomUser.objects.create_user(
        username="comparison_owner", email="other@example.com", role="owner"
    )
    country = Country.objects.create(name="Comparison country")
    city = City.objects.create(name="Comparison city", country=country)
    hotel = Hotel.objects.create(
        name="Harbor Hotel", city=city, owner=owner, avg_star=2
    )
    room = Room.objects.create(
        hotel=hotel,
        room_type="Family",
        stay_type="dayuse",
        price_per_night=300,
        price_per_day=80,
        adults_capacity=4,
        children_capacity=0,
        total_rooms=2,
        available_rooms=2,
        start_date=timezone.now().date() - timedelta(days=1),
        end_date=timezone.now().date() + timedelta(days=365),
    )
    RoomAmenity.objects.create(room=room, name="Parking")
    booking = Booking.objects.create(
        user=owner, service_type=2, total_price=200, final_price=200
    )
    Payment.objects.create(booking=booking, amount=200, method=2)
    RefundPolicy.objects.create(
        name="Comparison policy", service_type=2, is_active=False
    )
    promotion = Promotion.objects.create(
        title="Comparison Sale",
        promotion_type=4,
        is_active=False,
        discount_percent=20,
        discount_amount=40,
        start_date=timezone.now() - timedelta(days=10),
        end_date=timezone.now() - timedelta(days=1),
    )
    RoomPromotion.objects.create(
        room=room, promotion=promotion, discount_percent=20, discount_amount=40
    )
