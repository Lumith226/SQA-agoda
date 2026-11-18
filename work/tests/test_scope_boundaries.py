"""Final independent semantic and branch boundaries across the selected scope."""

from contract_support import checked_read
from datetime import timedelta
from unittest.mock import patch
import pytest
from promotions import views as promotion_views
from promotions.models import Promotion, RoomPromotion
from hotels import views as hotel_views
from bookings.models import RefundPolicy
from bookings.views import BookingViewSet
from test_views import request_view
from test_lifecycle import mark

LISTS = [
    "PromotionListCreateView",
    "PromotionListAdminView",
    "RoomPromotionListAdminView",
    "CarPromotionListAdminView",
    "FlightPromotionListAdminView",
    "ActivityPromotionListAdminView",
]


@pytest.mark.parametrize(
    "case_id,name,sort",
    [
        pytest.param(
            f"PR-SORT{case_index:02}",
            name,
            sort,
            id=f"PR-SORT{case_index:02}",
            marks=mark(
                f"PR-SORT{case_index:02}",
                "Promotions",
                "Handle ascending and malformed sort expressions",
                f"{name}; sort={sort}",
                "200; JSON list response",
                "promotions/views.py:" + name,
                "Sort input boundary",
            ),
        )
        for case_index, (name, sort) in enumerate(
            [
                (view_name, sort_expression)
                for view_name in LISTS
                for sort_expression in ["id-asc", "invalid"]
            ],
            1,
        )
    ],
)
def test_campaign_sort_boundaries(case_id, name, sort, sample_data, request_factory):
    """Verify campaign sort boundaries.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    response = request_view(
        request_factory, getattr(promotion_views, name), payload={"sort": sort}
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data
    assert isinstance(response.data["data"], list)


@pytest.mark.parametrize(
    "case_id,city,user",
    [
        pytest.param(
            f"H-CITY{case_index:02}",
            city,
            user,
            id=f"H-CITY{case_index:02}",
            marks=mark(
                f"H-CITY{case_index:02}",
                "Hotels",
                "Handle absent or invalid city and anonymous recommendations",
                f"city={city}; authenticated={user}",
                "200; empty for missing/invalid city",
                "hotels/views.py:HotelByCityView",
                "Argument boundary",
            ),
        )
        for case_index, (city, user) in enumerate(
            [(None, False), ("bad", False), ("valid", False)], 1
        )
    ],
)
def test_hotel_city_boundary(case_id, city, user, sample_data, request_factory):
    """Verify hotel city boundary.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    kwargs = (
        {}
        if city is None
        else {"city_id": sample_data.city.pk if city == "valid" else city}
    )
    response = request_view(
        request_factory,
        hotel_views.HotelByCityView,
        payload={"recommended": "true"} if city == "valid" else {},
        **kwargs,
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data
    if city != "valid":
        assert response.data["data"] == []


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(
            "PR-PARTIAL01",
            id="PR-PARTIAL01",
            marks=mark(
                "PR-PARTIAL01",
                "Promotions",
                "Report per-item errors when valid and unknown rooms are mixed",
                "One real room and one unknown room",
                "201; one link persisted; errors returned for unknown room",
                "promotions/views.py:PromotionCreateView",
                "Mixed batch decision",
            ),
        )
    ],
)
def test_campaign_partial_success(case_id, sample_data, request_factory):
    """Verify campaign partial success.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    payload = {
        "type": "hotel",
        "title": "Mixed Sale",
        "start_date": sample_data.now.isoformat(),
        "end_date": (sample_data.now + timedelta(days=2)).isoformat(),
        "discount_percent": 10,
        "discount_amount": 20,
        "rooms": [{"id": sample_data.room.pk}, {"id": 999999}],
    }
    response = request_view(
        request_factory, promotion_views.PromotionCreateView, "post", payload
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 201, response.data
    result = response.data["data"]
    assert len(result["rooms"]) == 1
    assert len(result["errors"]) == 1
    assert (
        RoomPromotion.objects.filter(promotion_id=result["promotion_id"]).count() == 1
    )


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(
            "B-NULLTIME01",
            id="B-NULLTIME01",
            marks=mark(
                "B-NULLTIME01",
                "Bookings",
                "Fallback to final price when start time is absent",
                "Policy exists; unsaved booking created_at=None",
                "Full final price returned",
                "bookings/views.py:calculate_refund_amount",
                "Helper boundary",
            ),
        )
    ],
)
def test_refund_missing_time(case_id, sample_data):
    """Verify refund missing time.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    RefundPolicy.objects.create(
        name="Standard", service_type=1, policy_type=2, refund_percentage=25
    )
    sample_data.booking.created_at = None
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert (
        checked_read(
            lambda: BookingViewSet().calculate_refund_amount(sample_data.booking)
        )
        == 100
    )


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_campaign_sort_boundaries
# Test Case ID: PR-SORT01
# Test Case ID: PR-SORT02
# Test Case ID: PR-SORT03
# Test Case ID: PR-SORT04
# Test Case ID: PR-SORT05
# Test Case ID: PR-SORT06
# Test Case ID: PR-SORT07
# Test Case ID: PR-SORT08
# Test Case ID: PR-SORT09
# Test Case ID: PR-SORT10
# Test Case ID: PR-SORT11
# Test Case ID: PR-SORT12
# Function: test_hotel_city_boundary
# Test Case ID: H-CITY01
# Test Case ID: H-CITY02
# Test Case ID: H-CITY03
# Function: test_campaign_partial_success
# Test Case ID: PR-PARTIAL01
# Function: test_refund_missing_time
# Test Case ID: B-NULLTIME01
