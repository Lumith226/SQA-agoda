"""Isolated serializer filter contracts using explicit method input doubles.

Parent serialization is mocked because these tests exercise only filtering.
The actual ActivityPromotion model contract is tested separately below; its
missing `activity` attribute must not be hidden by these isolated unit tests.
"""

from contract_support import checked_read
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from rest_framework.serializers import ModelSerializer
from promotions.serializers import (
    ActivityPromotionSerializer,
    FlightPromotionSerializer,
)
from promotions.models import ActivityPromotion, FlightPromotion
from test_lifecycle import mark

FLIGHT_FILTERS = [
    ("origin_id", "mismatch", True),
    ("destination_id", "mismatch", True),
    ("airline_id", "mismatch", True),
    ("start_date", "future", True),
    ("start_date", "invalid", False),
    ("origin_id", "match", False),
    ("destination_id", "match", False),
    ("airline_id", "match", False),
    ("start_date", "past", False),
    ("legs", "missing", True),
]


@pytest.mark.parametrize(
    "case_id,key,mode,filtered",
    [
        pytest.param(
            f"PR-F{case_index:02}",
            key,
            mode,
            filtered,
            id=f"PR-F{case_index:02}",
            marks=mark(
                f"PR-F{case_index:02}",
                "Promotions",
                "Filter serialized flight promotion by route, airline and departure date",
                f"{key}={mode}",
                f"Filtered out={filtered}",
                "promotions/serializers.py:FlightPromotionSerializer.to_representation",
                "Decision table; parent serializer mocked; real flight query",
            ),
        )
        for case_index, (key, mode, filtered) in enumerate(FLIGHT_FILTERS, 1)
    ],
)
def test_flight_promotion_filters(
    case_id, key, mode, filtered, sample_data, related_services
):
    """Verify flight promotion filters.

    Arrange: Persist the flight route and prepare the origin, destination, airline or date filter.
    Act: Execute the real filter method with only parent representation isolated.
    Assert and CheckDB: Require None for excluded routes or the exact representation dictionary for included routes; no DB write is expected.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    if key == "legs":
        related_services.flight.legs.all().delete()
    resource = FlightPromotion(
        promotion=sample_data.promotion, flight=related_services.flight
    )
    actual = {
        "origin_id": related_services.origin_airport.pk,
        "destination_id": related_services.destination_airport.pk,
        "airline_id": related_services.airline.pk,
    }
    if key in actual:
        context = {key: str(actual[key] if mode == "match" else 99999)}
    elif key == "start_date":
        context = {
            key: (
                "invalid-date"
                if mode == "invalid"
                else (sample_data.now + timedelta(days=5 if mode == "future" else 1))
                .date()
                .isoformat()
            )
        }
    else:
        context = {}
    with patch.object(
        ModelSerializer,
        "to_representation",
        return_value={"id": 9, "discount_percent": 10, "discount_amount": 20},
    ):
        serialized_output = checked_read(
            lambda: FlightPromotionSerializer(context=context).to_representation(
                resource
            )
        )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert (serialized_output is None) == filtered
    if serialized_output is not None:
        assert serialized_output == {"id": 9}


ACTIVITY_FILTERS = [
    ("none", "all", False),
    ("city_id", "mismatch", True),
    ("category", "mismatch", True),
    ("min_rating", "higher", True),
    ("min_price", "higher", True),
    ("min_price", "invalid", False),
    ("max_price", "lower", True),
    ("max_price", "invalid", False),
    ("search", "missing", True),
    ("search", "name", False),
    ("search", "description", False),
    ("start_date", "before", False),
    ("start_date", "after", True),
    ("end_date", "before", True),
    ("end_date", "after", False),
    ("start_date", "invalid", False),
    ("start_date", "missing_date", True),
    ("start_date", "second_package", False),
]


@pytest.mark.parametrize(
    "case_id,key,mode,filtered",
    [
        pytest.param(
            f"PR-AF{case_index:02}",
            key,
            mode,
            filtered,
            id=f"PR-AF{case_index:02}",
            marks=mark(
                f"PR-AF{case_index:02}",
                "Promotions",
                "Apply isolated activity-promotion filter contract",
                f"{key}={mode}; explicit activity interface double",
                f"Filtered out={filtered}",
                "promotions/serializers.py:ActivityPromotionSerializer.to_representation",
                "Unit input double; parent representation mocked; decision table",
            ),
        )
        for case_index, (key, mode, filtered) in enumerate(ACTIVITY_FILTERS, 1)
    ],
)
def test_activity_promotion_filter_contract(case_id, key, mode, filtered, sample_data):
    """Verify activity promotion filter contract.

    Arrange: Provide an explicit activity interface double with known rating, price, name and dates.
    Act: Execute the filter method with parent representation isolated.
    Assert and CheckDB: Assert the exact excluded/included dictionary and removal of internal fields; this is an isolated adapter contract.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """

    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    class Rows(list):

        def all(self):
            """Return the explicit in-memory rows used by the isolated adapter test double."""
            return self

        def prefetch_related(self, *args):
            """Match the queryset interface without changing the explicit in-memory rows or accessing a database."""
            return self

    dates = Rows(
        [
            SimpleNamespace(
                date_launch=(
                    None
                    if mode == "missing_date"
                    else sample_data.now + timedelta(days=3)
                )
            )
        ]
    )
    packages = Rows([SimpleNamespace(activitydate_set=dates)])
    if mode == "second_package":
        packages.insert(0, SimpleNamespace(activitydate_set=Rows([])))
    activity = SimpleNamespace(
        city_id=1,
        category="journey",
        avg_star=4,
        avg_price=100,
        name="Museum visit",
        short_description="Historic collection",
        activitypackage_set=packages,
    )
    resource = SimpleNamespace(activity=activity)
    values = {
        "city_id": "999",
        "category": "food",
        "min_rating": "5",
        "min_price": "bad" if mode == "invalid" else "200",
        "max_price": "bad" if mode == "invalid" else "50",
        "search": {
            "missing": "beach",
            "name": "MUSEUM",
            "description": "collection",
        }.get(mode, "beach"),
    }
    if key in ("start_date", "end_date"):
        offset = 2 if mode in ("before", "second_package") else 4
        context = {
            key: (
                "invalid-date"
                if mode == "invalid"
                else (sample_data.now + timedelta(days=offset)).date().isoformat()
            )
        }
    else:
        context = {} if key == "none" else {key: values[key]}
    with patch.object(
        ModelSerializer,
        "to_representation",
        return_value={"id": 9, "some_internal_field": "hidden"},
    ):
        serialized_output = checked_read(
            lambda: ActivityPromotionSerializer(context=context).to_representation(
                resource
            )
        )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert (serialized_output is None) == filtered
    if serialized_output is not None:
        assert "some_internal_field" not in serialized_output


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(
            "PR-ACTUAL01",
            id="PR-ACTUAL01",
            marks=mark(
                "PR-ACTUAL01",
                "Promotions",
                "Serialize an actual activity promotion without extra attributes",
                "Persisted ActivityPromotion with valid ActivityDate",
                "Non-null promotion data",
                "promotions/serializers.py:ActivityPromotionSerializer.to_representation",
                "Real model contract regression",
            ),
        )
    ],
)
def test_actual_activity_promotion_contract(case_id, sample_data, related_services):
    """Verify actual activity promotion contract.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    resource = ActivityPromotion.objects.create(
        promotion=sample_data.promotion, activity_date=related_services.activity_date
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    serialized_promotion = checked_read(
        lambda: ActivityPromotionSerializer().to_representation(resource)
    )
    assert (
        serialized_promotion is not None
    ), "Valid activity promotion is discarded because model has activity_date but serializer reads activity"
    assert serialized_promotion["id"] == resource.pk
    assert serialized_promotion["promotion"] == sample_data.promotion.pk
    assert serialized_promotion["activity_date"] == related_services.activity_date.pk


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_flight_promotion_filters
# Test Case ID: PR-F01
# Test Case ID: PR-F02
# Test Case ID: PR-F03
# Test Case ID: PR-F04
# Test Case ID: PR-F05
# Test Case ID: PR-F06
# Test Case ID: PR-F07
# Test Case ID: PR-F08
# Test Case ID: PR-F09
# Test Case ID: PR-F10
# Function: test_activity_promotion_filter_contract
# Test Case ID: PR-AF01
# Test Case ID: PR-AF02
# Test Case ID: PR-AF03
# Test Case ID: PR-AF04
# Test Case ID: PR-AF05
# Test Case ID: PR-AF06
# Test Case ID: PR-AF07
# Test Case ID: PR-AF08
# Test Case ID: PR-AF09
# Test Case ID: PR-AF10
# Test Case ID: PR-AF11
# Test Case ID: PR-AF12
# Test Case ID: PR-AF13
# Test Case ID: PR-AF14
# Test Case ID: PR-AF15
# Test Case ID: PR-AF16
# Test Case ID: PR-AF17
# Test Case ID: PR-AF18
# Function: test_actual_activity_promotion_contract
# Test Case ID: PR-ACTUAL01
