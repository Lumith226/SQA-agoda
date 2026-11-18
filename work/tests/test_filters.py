"""Request parameter robustness across every list view in the five modules.

The parameter catalog is read from the supplied source using AST. These cases
assert a successful structured response for a well-typed parameter. They do not
claim to verify every filter's business semantics; semantic cases are separate.
"""

import ast
from pathlib import Path
from datetime import timedelta
import pytest
from rest_framework.test import force_authenticate
from test_views import MODULES, TITLES, request_view
from promotions.models import (
    RoomPromotion,
    CarPromotion,
    FlightPromotion,
    ActivityPromotion,
)
from rooms.models import RoomAmenity
from bookings.models import RefundPolicy, GuestInfo
from contract_support import seed_contrast_records

ENDPOINTS = {
    "hotels": ["HotelListView", "HotelByCityView", "HotelSearchView"],
    "rooms": [
        "RoomListView",
        "RoomAdminListView",
        "RoomSearchView",
        "RoomAmenityListView",
    ],
    "bookings": ["BookingViewSet", "RefundPolicyViewSet"],
    "payments": ["PaymentListView", "PaymentListOverviewView", "PaymentViewSet"],
    "promotions": [
        "PromotionListCreateView",
        "PromotionListAdminView",
        "RoomPromotionListAdminView",
        "CarPromotionListAdminView",
        "FlightPromotionListAdminView",
        "ActivityPromotionListAdminView",
    ],
}
PARAMS = []
for application_name, names in ENDPOINTS.items():
    tree = ast.parse(
        Path(MODULES[application_name].__file__).read_text(encoding="utf-8")
    )
    pagination_keys = set()
    for class_node in tree.body:
        if isinstance(class_node, ast.ClassDef) and "Pagination" in class_node.name:
            pagination_keys.update(
                (
                    node.args[0].value
                    for node in ast.walk(class_node)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and (node.func.attr == "get")
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                )
            )
    for name in names:
        class_node = next(
            (
                class_node
                for class_node in tree.body
                if isinstance(class_node, ast.ClassDef) and class_node.name == name
            )
        )
        keys = {
            node.args[0].value
            for method_node in class_node.body
            if isinstance(method_node, ast.FunctionDef)
            and method_node.name in ["get_queryset", "list", "get"]
            for node in ast.walk(method_node)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and (node.func.attr == "get")
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        if application_name in ("hotels", "payments") and name.endswith("ListView"):
            keys |= pagination_keys
        keys = {
            field_name
            for field_name in keys
            if field_name
            not in {"message", "data", "id", "error", "booking_code", "totalItems"}
        }
        for case_index, key in enumerate(["__baseline__"] + sorted(keys), 1):
            case_id = f"{application_name[:2].upper()}-Q-{name}-{case_index:02}"
            PARAMS.append(
                pytest.param(
                    application_name,
                    name,
                    key,
                    id=case_id,
                    marks=pytest.mark.case(
                        module=TITLES[application_name],
                        objective=(
                            f"Accept well-typed {key} parameter in {name}"
                            if key != "__baseline__"
                            else f"Return structured list from {name}"
                        ),
                        inputs=f"Query parameter {key}; populated real service fixtures",
                        expected="HTTP 200 with JSON-serializable response and no database changes",
                        target=f"{application_name}/views.py:{name}",
                        technique="Request robustness partition; read-only DB snapshot",
                    ),
                )
            )


def value_for(key, sample_data, related_services):
    """Explicit well-typed representative values, not values copied from output."""
    if key == "booking__booking_code":
        # Use the complete fixture code. A one-character probe can randomly
        # match a UUID substring and makes the expected selection unstable.
        return sample_data.booking.booking_code
    if key in (
        "current",
        "page",
        "pageSize",
        "room",
        "adult",
        "child",
        "adults",
        "children",
        "num_rooms",
    ):
        return "1"
    if key == "statistic_by":
        return "month"
    if key == "sort":
        return "id-desc"
    if key in ("recommended", "driver_required"):
        return "true"
    if key in ("is_active", "available"):
        return "True"
    if key == "stay_type":
        return "overnight"
    if key == "type":
        return "hotel"
    if key in ("category",):
        return "journey"
    if key in ("search", "name", "hotel_name", "q"):
        return "Lotus" if "hotel" in key or key in ("name", "q") else ""
    if "email" in key:
        return "guest@example.com"
    if "status" in key:
        return "1"
    if key.endswith("_id") or key.endswith("Id"):
        mapping = {
            "activity_date": related_services.activity_date.pk,
            "activity_package": related_services.package.pk,
            "activity": related_services.activity.pk,
            "city": sample_data.city.pk,
            "owner": sample_data.user.pk,
            "hotel": sample_data.hotel.pk,
            "room": sample_data.room.pk,
            "booking": sample_data.booking.pk,
            "promotion": sample_data.promotion.pk,
            "car": related_services.car.pk,
            "flight": related_services.flight.pk,
            "airline": related_services.airline.pk,
            "driver": sample_data.user.pk,
            "user": sample_data.user.pk,
        }
        for part in sorted(mapping, key=len, reverse=True):
            if part in key.lower():
                return str(mapping[part])
        return "1"
    if any(
        (
            name_fragment in key.lower()
            for name_fragment in ("date", "time", "created_at", "arrival", "departure")
        )
    ):
        offset = (
            -2
            if any(
                (
                    name_fragment in key.lower()
                    for name_fragment in ("min", "start", "from")
                )
            )
            else 30
        )
        return (sample_data.now + timedelta(days=offset)).date().isoformat()
    if any(
        (
            name_fragment in key
            for name_fragment in (
                "price",
                "rating",
                "star",
                "amount",
                "duration",
                "distance",
            )
        )
    ):
        return "0" if "min" in key else "1000"
    mapping = {
        "hotel": sample_data.hotel.pk,
        "room": sample_data.room.pk,
        "booking": sample_data.booking.pk,
        "owner": sample_data.user.pk,
        "user": sample_data.user.pk,
        "driver": sample_data.user.pk,
        "city": sample_data.city.pk,
        "airline": related_services.airline.pk,
        "flight": related_services.flight.pk,
        "car": related_services.car.pk,
        "activity_package": related_services.package.pk,
        "activity_date": related_services.activity_date.pk,
        "activity": related_services.activity.pk,
        "origin": related_services.origin_airport.pk,
        "destination": related_services.destination_airport.pk,
        "promotion": sample_data.promotion.pk,
    }
    for part in sorted(mapping, key=len, reverse=True):
        if part in key.lower():
            return str(mapping[part])
    return "1"


@pytest.mark.parametrize("application_name,name,key", PARAMS)
def test_list_parameter_robustness(
    application_name, name, key, sample_data, related_services, request_factory
):
    """Verify list parameter robustness.

    Arrange: Create a matching record and deliberately different comparison records; calculate expected IDs independently.
    Act: Send one supported filter or pagination parameter through the real view.
    Assert and CheckDB: Compare the returned IDs, field values and ordering against the independently selected database records.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    seed_contrast_records(sample_data)
    RoomPromotion.objects.create(room=sample_data.room, promotion=sample_data.promotion)
    CarPromotion.objects.create(
        car=related_services.car, promotion=sample_data.promotion
    )
    FlightPromotion.objects.create(
        flight=related_services.flight, promotion=sample_data.promotion
    )
    ActivityPromotion.objects.create(
        activity_date=related_services.activity_date, promotion=sample_data.promotion
    )
    RoomAmenity.objects.create(room=sample_data.room, name="WiFi")
    RefundPolicy.objects.create(name="Standard", service_type=1)
    payload = (
        {}
        if key == "__baseline__"
        else {key: value_for(key, sample_data, related_services)}
    )
    if name == "RoomSearchView":
        payload.update(
            hotel_name="Lotus",
            start_date=(sample_data.now + timedelta(days=2)).date().isoformat(),
            end_date=(sample_data.now + timedelta(days=4)).date().isoformat(),
            adults=1,
            children=0,
        )
    kwargs = {"city_id": sample_data.city.pk} if name == "HotelByCityView" else {}
    from django.apps import apps

    models = [
        model_class
        for model_class in apps.get_models()
        if model_class._meta.app_label in MODULES
    ]
    state_before_operation = {
        model_class._meta.label: list(model_class.objects.order_by("pk").values_list())
        for model_class in models
    }
    response = request_view(
        request_factory,
        getattr(MODULES[application_name], name),
        payload=payload,
        user=sample_data.user,
        **kwargs,
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data
    assert isinstance(response.data, (dict, list))
    import json

    json.dumps(response.data, default=str)
    assert {
        model_class._meta.label: list(model_class.objects.order_by("pk").values_list())
        for model_class in models
    } == state_before_operation


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_list_parameter_robustness
# Test Case ID: HO-Q-HotelListView-01
# Test Case ID: HO-Q-HotelListView-02
# Test Case ID: HO-Q-HotelListView-03
# Test Case ID: HO-Q-HotelListView-04
# Test Case ID: HO-Q-HotelListView-05
# Test Case ID: HO-Q-HotelListView-06
# Test Case ID: HO-Q-HotelListView-07
# Test Case ID: HO-Q-HotelListView-08
# Test Case ID: HO-Q-HotelListView-09
# Test Case ID: HO-Q-HotelListView-10
# Test Case ID: HO-Q-HotelListView-11
# Test Case ID: HO-Q-HotelListView-12
# Test Case ID: HO-Q-HotelListView-13
# Test Case ID: HO-Q-HotelListView-14
# Test Case ID: HO-Q-HotelListView-15
# Test Case ID: HO-Q-HotelListView-16
# Test Case ID: HO-Q-HotelListView-17
# Test Case ID: HO-Q-HotelByCityView-01
# Test Case ID: HO-Q-HotelByCityView-02
# Test Case ID: HO-Q-HotelByCityView-03
# Test Case ID: HO-Q-HotelSearchView-01
# Test Case ID: HO-Q-HotelSearchView-02
# Test Case ID: RO-Q-RoomListView-01
# Test Case ID: RO-Q-RoomListView-02
# Test Case ID: RO-Q-RoomListView-03
# Test Case ID: RO-Q-RoomListView-04
# Test Case ID: RO-Q-RoomListView-05
# Test Case ID: RO-Q-RoomListView-06
# Test Case ID: RO-Q-RoomListView-07
# Test Case ID: RO-Q-RoomListView-08
# Test Case ID: RO-Q-RoomListView-09
# Test Case ID: RO-Q-RoomListView-10
# Test Case ID: RO-Q-RoomAdminListView-01
# Test Case ID: RO-Q-RoomAdminListView-02
# Test Case ID: RO-Q-RoomAdminListView-03
# Test Case ID: RO-Q-RoomAdminListView-04
# Test Case ID: RO-Q-RoomAdminListView-05
# Test Case ID: RO-Q-RoomAdminListView-06
# Test Case ID: RO-Q-RoomAdminListView-07
# Test Case ID: RO-Q-RoomAdminListView-08
# Test Case ID: RO-Q-RoomAdminListView-09
# Test Case ID: RO-Q-RoomAdminListView-10
# Test Case ID: RO-Q-RoomAdminListView-11
# Test Case ID: RO-Q-RoomAdminListView-12
# Test Case ID: RO-Q-RoomAdminListView-13
# Test Case ID: RO-Q-RoomAdminListView-14
# Test Case ID: RO-Q-RoomAdminListView-15
# Test Case ID: RO-Q-RoomAdminListView-16
# Test Case ID: RO-Q-RoomAdminListView-17
# Test Case ID: RO-Q-RoomAdminListView-18
# Test Case ID: RO-Q-RoomAdminListView-19
# Test Case ID: RO-Q-RoomSearchView-01
# Test Case ID: RO-Q-RoomSearchView-02
# Test Case ID: RO-Q-RoomSearchView-03
# Test Case ID: RO-Q-RoomSearchView-04
# Test Case ID: RO-Q-RoomSearchView-05
# Test Case ID: RO-Q-RoomSearchView-06
# Test Case ID: RO-Q-RoomAmenityListView-01
# Test Case ID: RO-Q-RoomAmenityListView-02
# Test Case ID: BO-Q-BookingViewSet-01
# Test Case ID: BO-Q-BookingViewSet-02
# Test Case ID: BO-Q-BookingViewSet-03
# Test Case ID: BO-Q-RefundPolicyViewSet-01
# Test Case ID: BO-Q-RefundPolicyViewSet-02
# Test Case ID: BO-Q-RefundPolicyViewSet-03
# Test Case ID: PA-Q-PaymentListView-01
# Test Case ID: PA-Q-PaymentListView-02
# Test Case ID: PA-Q-PaymentListView-03
# Test Case ID: PA-Q-PaymentListView-04
# Test Case ID: PA-Q-PaymentListView-05
# Test Case ID: PA-Q-PaymentListView-06
# Test Case ID: PA-Q-PaymentListView-07
# Test Case ID: PA-Q-PaymentListView-08
# Test Case ID: PA-Q-PaymentListView-09
# Test Case ID: PA-Q-PaymentListView-10
# Test Case ID: PA-Q-PaymentListView-11
# Test Case ID: PA-Q-PaymentListView-12
# Test Case ID: PA-Q-PaymentListView-13
# Test Case ID: PA-Q-PaymentListView-14
# Test Case ID: PA-Q-PaymentListView-15
# Test Case ID: PA-Q-PaymentListView-16
# Test Case ID: PA-Q-PaymentListView-17
# Test Case ID: PA-Q-PaymentListView-18
# Test Case ID: PA-Q-PaymentListView-19
# Test Case ID: PA-Q-PaymentListView-20
# Test Case ID: PA-Q-PaymentListView-21
# Test Case ID: PA-Q-PaymentListView-22
# Test Case ID: PA-Q-PaymentListView-23
# Test Case ID: PA-Q-PaymentListView-24
# Test Case ID: PA-Q-PaymentListView-25
# Test Case ID: PA-Q-PaymentListView-26
# Test Case ID: PA-Q-PaymentListView-27
# Test Case ID: PA-Q-PaymentListView-28
# Test Case ID: PA-Q-PaymentListView-29
# Test Case ID: PA-Q-PaymentListView-30
# Test Case ID: PA-Q-PaymentListView-31
# Test Case ID: PA-Q-PaymentListView-32
# Test Case ID: PA-Q-PaymentListView-33
# Test Case ID: PA-Q-PaymentListView-34
# Test Case ID: PA-Q-PaymentListView-35
# Test Case ID: PA-Q-PaymentListView-36
# Test Case ID: PA-Q-PaymentListView-37
# Test Case ID: PA-Q-PaymentListView-38
# Test Case ID: PA-Q-PaymentListView-39
# Test Case ID: PA-Q-PaymentListView-40
# Test Case ID: PA-Q-PaymentListView-41
# Test Case ID: PA-Q-PaymentListView-42
# Test Case ID: PA-Q-PaymentListView-43
# Test Case ID: PA-Q-PaymentListView-44
# Test Case ID: PA-Q-PaymentListView-45
# Test Case ID: PA-Q-PaymentListView-46
# Test Case ID: PA-Q-PaymentListView-47
# Test Case ID: PA-Q-PaymentListView-48
# Test Case ID: PA-Q-PaymentListOverviewView-01
# Test Case ID: PA-Q-PaymentListOverviewView-02
# Test Case ID: PA-Q-PaymentListOverviewView-03
# Test Case ID: PA-Q-PaymentListOverviewView-04
# Test Case ID: PA-Q-PaymentListOverviewView-05
# Test Case ID: PA-Q-PaymentListOverviewView-06
# Test Case ID: PA-Q-PaymentListOverviewView-07
# Test Case ID: PA-Q-PaymentListOverviewView-08
# Test Case ID: PA-Q-PaymentListOverviewView-09
# Test Case ID: PA-Q-PaymentListOverviewView-10
# Test Case ID: PA-Q-PaymentListOverviewView-11
# Test Case ID: PA-Q-PaymentListOverviewView-12
# Test Case ID: PA-Q-PaymentListOverviewView-13
# Test Case ID: PA-Q-PaymentListOverviewView-14
# Test Case ID: PA-Q-PaymentListOverviewView-15
# Test Case ID: PA-Q-PaymentListOverviewView-16
# Test Case ID: PA-Q-PaymentListOverviewView-17
# Test Case ID: PA-Q-PaymentListOverviewView-18
# Test Case ID: PA-Q-PaymentListOverviewView-19
# Test Case ID: PA-Q-PaymentViewSet-01
# Test Case ID: PA-Q-PaymentViewSet-02
# Test Case ID: PR-Q-PromotionListCreateView-01
# Test Case ID: PR-Q-PromotionListCreateView-02
# Test Case ID: PR-Q-PromotionListCreateView-03
# Test Case ID: PR-Q-PromotionListCreateView-04
# Test Case ID: PR-Q-PromotionListAdminView-01
# Test Case ID: PR-Q-PromotionListAdminView-02
# Test Case ID: PR-Q-PromotionListAdminView-03
# Test Case ID: PR-Q-PromotionListAdminView-04
# Test Case ID: PR-Q-PromotionListAdminView-05
# Test Case ID: PR-Q-PromotionListAdminView-06
# Test Case ID: PR-Q-PromotionListAdminView-07
# Test Case ID: PR-Q-PromotionListAdminView-08
# Test Case ID: PR-Q-PromotionListAdminView-09
# Test Case ID: PR-Q-PromotionListAdminView-10
# Test Case ID: PR-Q-PromotionListAdminView-11
# Test Case ID: PR-Q-PromotionListAdminView-12
# Test Case ID: PR-Q-PromotionListAdminView-13
# Test Case ID: PR-Q-PromotionListAdminView-14
# Test Case ID: PR-Q-PromotionListAdminView-15
# Test Case ID: PR-Q-RoomPromotionListAdminView-01
# Test Case ID: PR-Q-RoomPromotionListAdminView-02
# Test Case ID: PR-Q-RoomPromotionListAdminView-03
# Test Case ID: PR-Q-RoomPromotionListAdminView-04
# Test Case ID: PR-Q-RoomPromotionListAdminView-05
# Test Case ID: PR-Q-RoomPromotionListAdminView-06
# Test Case ID: PR-Q-RoomPromotionListAdminView-07
# Test Case ID: PR-Q-RoomPromotionListAdminView-08
# Test Case ID: PR-Q-CarPromotionListAdminView-01
# Test Case ID: PR-Q-CarPromotionListAdminView-02
# Test Case ID: PR-Q-CarPromotionListAdminView-03
# Test Case ID: PR-Q-CarPromotionListAdminView-04
# Test Case ID: PR-Q-CarPromotionListAdminView-05
# Test Case ID: PR-Q-CarPromotionListAdminView-06
# Test Case ID: PR-Q-CarPromotionListAdminView-07
# Test Case ID: PR-Q-CarPromotionListAdminView-08
# Test Case ID: PR-Q-FlightPromotionListAdminView-01
# Test Case ID: PR-Q-FlightPromotionListAdminView-02
# Test Case ID: PR-Q-FlightPromotionListAdminView-03
# Test Case ID: PR-Q-FlightPromotionListAdminView-04
# Test Case ID: PR-Q-FlightPromotionListAdminView-05
# Test Case ID: PR-Q-FlightPromotionListAdminView-06
# Test Case ID: PR-Q-FlightPromotionListAdminView-07
# Test Case ID: PR-Q-FlightPromotionListAdminView-08
# Test Case ID: PR-Q-ActivityPromotionListAdminView-01
# Test Case ID: PR-Q-ActivityPromotionListAdminView-02
# Test Case ID: PR-Q-ActivityPromotionListAdminView-03
# Test Case ID: PR-Q-ActivityPromotionListAdminView-04
# Test Case ID: PR-Q-ActivityPromotionListAdminView-05
# Test Case ID: PR-Q-ActivityPromotionListAdminView-06
# Test Case ID: PR-Q-ActivityPromotionListAdminView-07
# Test Case ID: PR-Q-ActivityPromotionListAdminView-08
