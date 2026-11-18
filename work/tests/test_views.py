"""HTTP view tests with request factory, real database checks and mocked gateways.

Case ID prefixes: H-V Hotels, R-VW Rooms, B-V Bookings, P-V Payments,
PR-V Promotions. Each generated pytest parameter includes its full case ID.
"""

from contract_support import checked_read
from datetime import timedelta
import importlib
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from rest_framework.test import force_authenticate
from rest_framework.request import Request
from hotels import views as hotel_views
from rooms import views as room_views
from bookings import views as booking_views
from payments import views as payment_views
from promotions import views as promotion_views
from hotels.models import Hotel, HotelImage, UserHotelInteraction
from rooms.models import Room, RoomAmenity, RoomImage, RoomBookingDetail
from bookings.models import Booking, GuestInfo, RefundPolicy
from payments.models import Payment
from payments.constants.payment_status import PaymentStatus
from payments.constants.payment_method import PaymentMethod
from bookings.constants.booking_status import BookingStatus
from promotions.models import (
    Promotion,
    RoomPromotion,
    CarPromotion,
    FlightPromotion,
    ActivityPromotion,
)
from contract_support import (
    database_snapshot,
    publish_contract,
    expected_read_contract,
    describe_read_contract,
    assert_read_response,
    model_projection,
    compare_value,
)

MODULES = {
    "hotels": hotel_views,
    "rooms": room_views,
    "bookings": booking_views,
    "payments": payment_views,
    "promotions": promotion_views,
}
TITLES = {
    "hotels": "Hotels",
    "rooms": "Rooms",
    "bookings": "Bookings",
    "payments": "Payments",
    "promotions": "Promotions",
}


def request_view(
    request_factory,
    view_class,
    method="get",
    payload=None,
    user=None,
    action=None,
    **kwargs,
):
    """Invoke a real HTTP view; independently verify GET data and DB non-mutation."""
    request = getattr(request_factory, method)("/", data=payload or {}, format="json")
    if user is not None:
        force_authenticate(request, user=user)
    view = (
        view_class.as_view(
            {
                method: action
                or {
                    "get": "list",
                    "post": "create",
                    "patch": "partial_update",
                    "delete": "destroy",
                }[method]
            }
        )
        if hasattr(view_class, "get_extra_actions")
        else view_class.as_view()
    )
    if method == "get":
        contract = expected_read_contract(
            view_class, payload or {}, kwargs, user, action
        )
        if contract is not None:
            publish_contract(
                describe_read_contract(contract, payload or {}),
                inputs={"query": payload or {}, "route": kwargs},
            )
        before_read = database_snapshot()
        try:
            response = view(request, **kwargs)
            assert_read_response(contract, response)
            return response
        finally:
            assert (
                database_snapshot() == before_read
            ), "GET changed persisted database rows or fields."
    before_write = database_snapshot()
    response = view(request, **kwargs)
    # Validation failures must not leave partial writes. A capture failure has
    # its own explicit FAILED-payment transition, checked by lifecycle tests.
    if response.status_code >= 400 and action != "capture":
        assert (
            database_snapshot() == before_write
        ), "Rejected request changed persisted rows or fields instead of preserving the pre-request state."
    return response


CRUD = [
    (
        "hotels",
        "Hotel",
        "HotelListView",
        "HotelDetailView",
        "HotelCreateView",
        "HotelUpdateViewNotImage",
        "HotelDeleteView",
        "hotel",
    ),
    (
        "rooms",
        "Room",
        "RoomListView",
        "RoomDetailView",
        "RoomCreateView",
        "RoomUpdateView",
        "RoomDeleteView",
        "room",
    ),
    (
        "rooms",
        "RoomAmenity",
        "RoomAmenityListView",
        "RoomAmenityDetailView",
        "RoomAmenityCreateView",
        "RoomAmenityUpdateView",
        "RoomAmenityDeleteView",
        "amenity",
    ),
    (
        "payments",
        "Payment",
        "PaymentListView",
        "PaymentDetailView",
        "PaymentCreateView",
        "PaymentUpdateView",
        "PaymentDeleteView",
        "payment",
    ),
    (
        "promotions",
        "Promotion",
        "PromotionListAdminView",
        "PromotionDetailView",
        None,
        "PromotionUpdateView",
        "PromotionDeleteView",
        "promotion",
    ),
    (
        "promotions",
        "RoomPromotion",
        "RoomPromotionListAdminView",
        "RoomPromotionAdminDetailView",
        "RoomPromotionAdminCreateView",
        "RoomPromotionAdminUpdateView",
        "RoomPromotionAdminDeleteView",
        "rp",
    ),
    (
        "promotions",
        "CarPromotion",
        "CarPromotionListAdminView",
        "CarPromotionAdminDetailView",
        "CarPromotionAdminCreateView",
        "CarPromotionAdminUpdateView",
        "CarPromotionAdminDeleteView",
        "cp",
    ),
    (
        "promotions",
        "FlightPromotion",
        "FlightPromotionListAdminView",
        "FlightPromotionAdminDetailView",
        "FlightPromotionAdminCreateView",
        "FlightPromotionAdminUpdateView",
        "FlightPromotionAdminDeleteView",
        "fp",
    ),
    (
        "promotions",
        "ActivityPromotion",
        "ActivityPromotionListAdminView",
        "ActivityPromotionAdminDetailView",
        "ActivityPromotionAdminCreateView",
        "ActivityPromotionAdminUpdateView",
        "ActivityPromotionAdminDeleteView",
        "ap",
    ),
    (
        "bookings",
        "RefundPolicy",
        "RefundPolicyViewSet",
        "RefundPolicyViewSet",
        "RefundPolicyViewSet",
        "RefundPolicyViewSet",
        "RefundPolicyViewSet",
        "policy",
    ),
    (
        "bookings",
        "Booking",
        "BookingViewSet",
        "BookingViewSet",
        "BookingViewSet",
        "BookingViewSet",
        "BookingViewSet",
        "booking",
    ),
]
OPERATIONS = [
    "list",
    "retrieve",
    "create",
    "invalid_create",
    "update",
    "invalid_update",
    "delete",
    "missing",
]
PARAMS = []
for configuration_index, crud_configuration in enumerate(CRUD, 1):
    application_name, model, *_ = crud_configuration
    for operation in OPERATIONS:
        if crud_configuration[4] is None and "create" in operation:
            continue
        case_id = (
            f"{application_name[:2].upper()}-CRUD{configuration_index:02}-{operation}"
        )
        PARAMS.append(
            pytest.param(
                crud_configuration,
                operation,
                id=case_id,
                marks=pytest.mark.case(
                    module=TITLES[application_name],
                    objective=f"{operation.replace('_', ' ').title()} {model} through its HTTP view",
                    inputs=f"{model} fixture; operation={operation}; authenticated owner",
                    expected=(
                        "HTTP 400 and no DB mutation"
                        if operation.startswith("invalid")
                        else (
                            "HTTP 404"
                            if operation == "missing"
                            else f"Success response and persisted {operation} result"
                        )
                    ),
                    target=f"{application_name}/views.py:{crud_configuration[2 if operation == 'list' else 3 if operation in ('retrieve', 'missing') else 4 if 'create' in operation else 5 if 'update' in operation else 6]}",
                    technique="API unit test; positive/negative partition; CheckDB; rollback",
                ),
            )
        )


@pytest.mark.parametrize("crud_configuration,operation", PARAMS)
def test_resource_create_read_update_delete_contracts(
    crud_configuration, operation, sample_data, related_services, request_factory
):
    """Verify resource create read update delete contracts.

    Arrange: Persist the resource and related foreign keys; keep a full database snapshot before the request.
    Act: Dispatch the requested list, retrieve, create, update or delete HTTP action.
    Assert and CheckDB: Compare response fields and exact affected database rows; reject invalid writes without changing any field.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    (
        application_name,
        model,
        list_view_name,
        detail_view_name,
        create_view_name,
        update_view_name,
        delete_view_name,
        key,
    ) = crud_configuration
    amenity = RoomAmenity.objects.create(room=sample_data.room, name="WiFi")
    room_promotion = RoomPromotion.objects.create(
        room=sample_data.room, promotion=sample_data.promotion
    )
    car_promotion = CarPromotion.objects.create(
        car=related_services.car, promotion=sample_data.promotion
    )
    flight_promotion = FlightPromotion.objects.create(
        flight=related_services.flight, promotion=sample_data.promotion
    )
    activity_promotion = ActivityPromotion.objects.create(
        activity_date=related_services.activity_date, promotion=sample_data.promotion
    )
    policy = RefundPolicy.objects.create(name="Standard", service_type=1)
    objects = {
        **vars(sample_data),
        "amenity": amenity,
        "rp": room_promotion,
        "cp": car_promotion,
        "fp": flight_promotion,
        "ap": activity_promotion,
        "policy": policy,
    }
    resource = objects[key]
    manager = resource.__class__.objects
    state_before_operation = manager.count()
    before_request = database_snapshot()
    payloads = {
        "hotel": {"city": sample_data.city.pk, "name": "New Hotel"},
        "room": {
            "hotel": sample_data.hotel.pk,
            "room_type": "Twin",
            "price_per_night": 150,
        },
        "amenity": {"room": sample_data.room.pk, "name": "Pool"},
        "payment": {"booking": sample_data.booking.pk, "method": 1, "amount": 150},
        "promotion": {
            "title": "New Sale",
            "start_date": sample_data.now.isoformat(),
            "end_date": (sample_data.now + timedelta(days=2)).isoformat(),
        },
        "rp": {
            "room": sample_data.room.pk,
            "promotion": sample_data.promotion.pk,
            "discount_percent": 15,
        },
        "cp": {
            "car": related_services.car.pk,
            "promotion": sample_data.promotion.pk,
            "discount_percent": 15,
        },
        "fp": {
            "flight": related_services.flight.pk,
            "promotion": sample_data.promotion.pk,
            "discount_percent": 15,
        },
        "ap": {
            "activity_date": related_services.activity_date.pk,
            "promotion": sample_data.promotion.pk,
            "discount_percent": 15,
        },
        "policy": {"name": "New Policy", "service_type": 1},
        "booking": {"service_type": 1, "total_price": 150},
    }
    if operation == "list":
        response = request_view(
            request_factory,
            getattr(MODULES[application_name], list_view_name),
            user=sample_data.user,
        )
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert response.status_code == 200, response.data
        body = response.data
        rows = body.get("data", body.get("results")) if isinstance(body, dict) else body
        assert isinstance(rows, list), body
        assert any(
            (row and row.get("id") == resource.pk for row in rows)
        ), f"Fixture {resource.pk} absent from response {body}"
    elif operation in ("retrieve", "missing"):
        response = request_view(
            request_factory,
            getattr(MODULES[application_name], detail_view_name),
            user=sample_data.user,
            action="retrieve",
            pk=999999 if operation == "missing" else resource.pk,
        )
        assert response.status_code == (
            404 if operation == "missing" else 200
        ), response.data
        if operation == "retrieve":
            row = response.data.get("data", response.data)
            assert row["id"] == resource.pk
    elif "create" in operation:
        payload = {} if operation == "invalid_create" else payloads[key]
        expected_status = (
            400
            if operation == "invalid_create"
            else 201 if key in ("booking", "policy") else 200
        )
        publish_contract(
            f"HTTP {expected_status}. "
            + (
                "Return field validation errors. All database rows and fields remain equal to the pre-request snapshot."
                if operation == "invalid_create"
                else f"Create exactly one {model} row. Persisted fields equal {payload}; foreign keys reference the submitted IDs. Return the newly persisted resource fields in data."
            ),
            inputs=payload,
        )
        response = request_view(
            request_factory,
            getattr(MODULES[application_name], create_view_name),
            "post",
            payload,
            sample_data.user,
        )
        if operation == "invalid_create":
            assert response.status_code == 400, response.data
            assert manager.count() == state_before_operation
            assert (
                database_snapshot() == before_request
            ), "Rejected creation changed an existing row or left related rows."
        else:
            assert response.status_code == expected_status, response.data
            assert manager.count() == state_before_operation + 1
            created_record = manager.latest("pk")
            for field, value in payload.items():
                actual = (
                    getattr(created_record, field + "_id")
                    if field
                    in (
                        "room",
                        "hotel",
                        "city",
                        "booking",
                        "promotion",
                        "car",
                        "flight",
                        "activity_date",
                    )
                    else getattr(created_record, field)
                )
                assert actual == value
            if key != "booking":
                output_row = response.data.get("data", response.data)
                for output_field, expected_value in model_projection(
                    created_record
                ).items():
                    if key == "hotel" and output_field == "id":
                        continue  # HotelCreateSerializer intentionally omits the ID field.
                    assert output_field in output_row
                    assert compare_value(output_row[output_field], expected_value)
    elif "update" in operation:
        field = (
            "name"
            if key in ("hotel", "amenity", "policy")
            else (
                "room_type"
                if key == "room"
                else (
                    "amount"
                    if key == "payment"
                    else (
                        "title"
                        if key == "promotion"
                        else "total_price" if key == "booking" else "discount_percent"
                    )
                )
            )
        )
        value = "Updated" if field in ("name", "room_type", "title") else 27
        payload = {field: value if operation == "update" else None}
        if operation == "invalid_update" and key == "amenity":
            payload = {"room": None}
        publish_contract(
            (
                "HTTP 400 with field validation errors; every persisted row and field, including the original resource and related rows, remains unchanged."
                if operation == "invalid_update"
                else f"HTTP 200. data.id={resource.pk}; data.{field}={value!r}. Reloaded {model}.{field} equals {value!r}; resource count remains {state_before_operation}; unrelated resource fields remain unchanged."
            ),
            inputs=payload,
        )
        original_values = manager.filter(pk=resource.pk).values().get()
        response = request_view(
            request_factory,
            getattr(MODULES[application_name], update_view_name),
            "patch",
            payload,
            sample_data.user,
            pk=resource.pk,
        )
        if operation == "invalid_update":
            assert response.status_code == 400, response.data
            assert (
                database_snapshot() == before_request
            ), "Rejected update changed persisted fields."
        else:
            assert response.status_code == 200, response.data
            resource.refresh_from_db()
            assert getattr(resource, field) == value
            updated_values = manager.filter(pk=resource.pk).values().get()
            for original_field, original_value in original_values.items():
                if original_field not in (field, "updated_at"):
                    assert (
                        updated_values[original_field] == original_value
                    ), f"Unexpected write to {original_field}"
        assert manager.count() == state_before_operation
    else:
        record_id = resource.pk
        publish_contract(
            f'HTTP {200 if key in ("amenity","payment","promotion","rp","cp","fp","ap","policy","booking") else 204}. Delete {model} id={record_id}; a fresh DB query finds no row with that ID. Unrelated parent records remain unchanged.'
        )
        response = request_view(
            request_factory,
            getattr(MODULES[application_name], delete_view_name),
            "delete",
            user=sample_data.user,
            pk=record_id,
        )
        assert response.status_code in (200, 204), response.data
        assert not manager.filter(pk=record_id).exists()
        # CheckDB: deleting a resource must preserve unrelated identity tables.
        after_delete = database_snapshot()
        for identity_table in (
            "accounts.CustomUser",
            "countries.Country",
            "cities.City",
        ):
            assert after_delete[identity_table] == before_request[identity_table]
        if key == "room":
            sample_data.hotel.refresh_from_db()
            assert sample_data.hotel.min_price == 0
        if key == "hotel":
            assert not Room.objects.filter(hotel_id=record_id).exists()
        if key == "payment":
            sample_data.booking.refresh_from_db()
            assert (
                sample_data.booking.total_price
                == sample_data.booking.final_price
                == 100
            )


PAYMENT_CASES = [
    ("P-V01", "missing_booking"),
    ("P-V02", "unknown_booking"),
    ("P-V03", "duplicate_booking"),
    ("P-V04", "missing_urls"),
    ("P-V05", "checkout_ok"),
    ("P-V06", "checkout_error"),
    ("P-V07", "processed_success"),
    ("P-V08", "processed_paid"),
    ("P-V09", "processed_unpaid"),
    ("P-V10", "tampered_amount"),
]


@pytest.mark.parametrize(
    "case_id,scenario",
    [
        pytest.param(
            case_id,
            scenario,
            id=case_id,
            marks=pytest.mark.case(
                module="Payments",
                objective="Validate payment creation and Stripe checkout state",
                inputs=scenario,
                expected={
                    "missing_booking": "400; no payment inserted",
                    "unknown_booking": "404; no payment inserted",
                    "duplicate_booking": "400; existing payment retained",
                    "missing_urls": "400; no gateway call",
                    "checkout_ok": "200; session ID persisted; gateway receives exact VND amount",
                    "checkout_error": "400; no transaction ID stored",
                    "processed_success": "400; no gateway call",
                    "processed_paid": "400; no gateway call",
                    "processed_unpaid": "400; no gateway call",
                    "tampered_amount": "400; client cannot override booking amount",
                }[scenario],
                target="payments/views.py:PaymentViewSet.create/pay",
                technique="State transition; gateway mock; real DB",
            ),
        )
        for case_id, scenario in PAYMENT_CASES
    ],
)
def test_payment_checkout(case_id, scenario, sample_data, request_factory):
    """Verify payment checkout.

    Arrange: Persist the payment state and prepare exact VND amounts and redirect URLs.
    Act: Call payment creation or checkout with the Stripe boundary mocked.
    Assert and CheckDB: Check the response, gateway arguments, transaction ID and all persisted payment fields.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    payment = sample_data.payment
    state_before_operation = Payment.objects.count()
    if scenario in (
        "missing_booking",
        "unknown_booking",
        "duplicate_booking",
        "tampered_amount",
    ):
        payload = (
            {}
            if scenario == "missing_booking"
            else {
                "booking_id": (
                    999999 if scenario == "unknown_booking" else sample_data.booking.pk
                )
            }
        )
        if scenario == "tampered_amount":
            sample_data.payment.delete()
            state_before_operation = Payment.objects.count()
            payload["amount"] = 1
        response = request_view(
            request_factory, payment_views.PaymentViewSet, "post", payload
        )
        expected = 404 if scenario == "unknown_booking" else 400
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert (
            response.status_code == expected
        ), f"Expected {expected}, observed {response.status_code}; {response.data}"
        assert Payment.objects.count() == state_before_operation
    else:
        statuses = {
            "processed_success": PaymentStatus.SUCCESS,
            "processed_paid": PaymentStatus.PAID,
            "processed_unpaid": PaymentStatus.UNPAID,
        }
        if scenario in statuses:
            payment.status = statuses[scenario]
            payment.save()
        payload = (
            {}
            if scenario == "missing_urls"
            else {
                "success_url": "http://localhost/success",
                "cancel_url": "http://localhost/cancel",
            }
        )
        with patch("payments.views.stripe.checkout.Session.create") as create:
            create.return_value = SimpleNamespace(
                id="cs_unit_test", url="http://localhost/checkout"
            )
            if scenario == "checkout_error":
                create.side_effect = RuntimeError("Gateway unavailable")
            response = request_view(
                request_factory,
                payment_views.PaymentViewSet,
                "post",
                payload,
                action="pay",
                pk=payment.pk,
            )
            assert response.status_code == (
                200 if scenario == "checkout_ok" else 400
            ), response.data
            payment.refresh_from_db()
            if scenario == "checkout_ok":
                assert payment.transaction_id == "cs_unit_test"
                assert (
                    create.call_args.kwargs["line_items"][0]["price_data"][
                        "unit_amount"
                    ]
                    == 100
                )
            elif scenario == "checkout_error":
                assert payment.transaction_id is None
            else:
                create.assert_not_called()


@pytest.mark.parametrize(
    "case_id,kind",
    [
        pytest.param(
            f"P-E{case_index:02}",
            kind,
            id=f"P-E{case_index:02}",
            marks=pytest.mark.case(
                module="Payments",
                objective="Resolve booking email using user then guest",
                inputs=kind,
                expected={
                    "user": "guest@example.com",
                    "guest": "alice@example.com",
                    "none": None,
                }[kind],
                target="payments/views.py:PaymentViewSet.get_booking_email",
                technique="Decision table",
            ),
        )
        for case_index, kind in enumerate(["user", "guest", "none"], 1)
    ],
)
def test_payment_email(case_id, kind, sample_data):
    """Verify payment email.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    if kind != "user":
        sample_data.booking.user = None
        sample_data.booking.save()
    if kind == "guest":
        GuestInfo.objects.create(
            booking=sample_data.booking,
            full_name="Alice",
            email="alice@example.com",
            phone="123",
        )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert (
        checked_read(
            lambda: payment_views.PaymentViewSet().get_booking_email(
                sample_data.booking
            )
        )
        == {"user": "guest@example.com", "guest": "alice@example.com", "none": None}[
            kind
        ]
    )


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_resource_create_read_update_delete_contracts
# Test Case ID: HO-CRUD01-list
# Test Case ID: HO-CRUD01-retrieve
# Test Case ID: HO-CRUD01-create
# Test Case ID: HO-CRUD01-invalid_create
# Test Case ID: HO-CRUD01-update
# Test Case ID: HO-CRUD01-invalid_update
# Test Case ID: HO-CRUD01-delete
# Test Case ID: HO-CRUD01-missing
# Test Case ID: RO-CRUD02-list
# Test Case ID: RO-CRUD02-retrieve
# Test Case ID: RO-CRUD02-create
# Test Case ID: RO-CRUD02-invalid_create
# Test Case ID: RO-CRUD02-update
# Test Case ID: RO-CRUD02-invalid_update
# Test Case ID: RO-CRUD02-delete
# Test Case ID: RO-CRUD02-missing
# Test Case ID: RO-CRUD03-list
# Test Case ID: RO-CRUD03-retrieve
# Test Case ID: RO-CRUD03-create
# Test Case ID: RO-CRUD03-invalid_create
# Test Case ID: RO-CRUD03-update
# Test Case ID: RO-CRUD03-invalid_update
# Test Case ID: RO-CRUD03-delete
# Test Case ID: RO-CRUD03-missing
# Test Case ID: PA-CRUD04-list
# Test Case ID: PA-CRUD04-retrieve
# Test Case ID: PA-CRUD04-create
# Test Case ID: PA-CRUD04-invalid_create
# Test Case ID: PA-CRUD04-update
# Test Case ID: PA-CRUD04-invalid_update
# Test Case ID: PA-CRUD04-delete
# Test Case ID: PA-CRUD04-missing
# Test Case ID: PR-CRUD05-list
# Test Case ID: PR-CRUD05-retrieve
# Test Case ID: PR-CRUD05-update
# Test Case ID: PR-CRUD05-invalid_update
# Test Case ID: PR-CRUD05-delete
# Test Case ID: PR-CRUD05-missing
# Test Case ID: PR-CRUD06-list
# Test Case ID: PR-CRUD06-retrieve
# Test Case ID: PR-CRUD06-create
# Test Case ID: PR-CRUD06-invalid_create
# Test Case ID: PR-CRUD06-update
# Test Case ID: PR-CRUD06-invalid_update
# Test Case ID: PR-CRUD06-delete
# Test Case ID: PR-CRUD06-missing
# Test Case ID: PR-CRUD07-list
# Test Case ID: PR-CRUD07-retrieve
# Test Case ID: PR-CRUD07-create
# Test Case ID: PR-CRUD07-invalid_create
# Test Case ID: PR-CRUD07-update
# Test Case ID: PR-CRUD07-invalid_update
# Test Case ID: PR-CRUD07-delete
# Test Case ID: PR-CRUD07-missing
# Test Case ID: PR-CRUD08-list
# Test Case ID: PR-CRUD08-retrieve
# Test Case ID: PR-CRUD08-create
# Test Case ID: PR-CRUD08-invalid_create
# Test Case ID: PR-CRUD08-update
# Test Case ID: PR-CRUD08-invalid_update
# Test Case ID: PR-CRUD08-delete
# Test Case ID: PR-CRUD08-missing
# Test Case ID: PR-CRUD09-list
# Test Case ID: PR-CRUD09-retrieve
# Test Case ID: PR-CRUD09-create
# Test Case ID: PR-CRUD09-invalid_create
# Test Case ID: PR-CRUD09-update
# Test Case ID: PR-CRUD09-invalid_update
# Test Case ID: PR-CRUD09-delete
# Test Case ID: PR-CRUD09-missing
# Test Case ID: BO-CRUD10-list
# Test Case ID: BO-CRUD10-retrieve
# Test Case ID: BO-CRUD10-create
# Test Case ID: BO-CRUD10-invalid_create
# Test Case ID: BO-CRUD10-update
# Test Case ID: BO-CRUD10-invalid_update
# Test Case ID: BO-CRUD10-delete
# Test Case ID: BO-CRUD10-missing
# Test Case ID: BO-CRUD11-list
# Test Case ID: BO-CRUD11-retrieve
# Test Case ID: BO-CRUD11-create
# Test Case ID: BO-CRUD11-invalid_create
# Test Case ID: BO-CRUD11-update
# Test Case ID: BO-CRUD11-invalid_update
# Test Case ID: BO-CRUD11-delete
# Test Case ID: BO-CRUD11-missing
# Function: test_payment_checkout
# Test Case ID: P-V01
# Test Case ID: P-V02
# Test Case ID: P-V03
# Test Case ID: P-V04
# Test Case ID: P-V05
# Test Case ID: P-V06
# Test Case ID: P-V07
# Test Case ID: P-V08
# Test Case ID: P-V09
# Test Case ID: P-V10
# Function: test_payment_email
# Test Case ID: P-E01
# Test Case ID: P-E02
# Test Case ID: P-E03
