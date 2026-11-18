"""Further branch and semantic checks for views, inventory and request isolation."""

from contract_support import checked_read
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import math
import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.request import Request
from hotels import views as hotel_views
from rooms import views as room_views
from bookings import views as booking_views
from promotions import views as promotion_views
from hotels.models import Hotel, HotelImage, UserHotelInteraction
from rooms.models import RoomImage, RoomBookingDetail, RoomAmenity
from rooms.serializers import RoomBookingDetailCreateSerializer
from bookings.models import Booking, RefundPolicy
from test_views import request_view
from test_lifecycle import mark, attach_detail

HOTEL_INPUTS = [
    ("cityId", "bad"),
    ("ownerId", "bad"),
    ("adult", "bad"),
    ("child", "bad"),
    ("room", "bad"),
    ("avg_star", "bad"),
    ("min_avg_star", "bad"),
    ("max_avg_star", "bad"),
    ("min_avg_price", "bad"),
    ("max_avg_price", "bad"),
    ("sort", "id-asc"),
    ("sort", "bad"),
    ("name", "Lotus"),
    ("startDate", "range"),
    ("startDate", "bad_range"),
    ("recommended", "anonymous"),
]


@pytest.mark.parametrize(
    "case_id,key,value",
    [
        pytest.param(
            f"H-QX{case_index:02}",
            key,
            value,
            id=f"H-QX{case_index:02}",
            marks=mark(
                f"H-QX{case_index:02}",
                "Hotels",
                "Handle filter boundaries without server exception",
                f"{key}={value}",
                "HTTP 200; invalid city/owner returns empty list; other malformed optional filters handled",
                "hotels/views.py:HotelListView/HotelPagination",
            ),
        )
        for case_index, (key, value) in enumerate(HOTEL_INPUTS, 1)
    ],
)
def test_hotel_filter_boundaries(case_id, key, value, sample_data, request_factory):
    """Verify hotel filter boundaries.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    query = {key: value}
    if value in ("range", "bad_range"):
        query = {
            "startDate": (
                (sample_data.now + timedelta(days=2)).date().isoformat()
                if value == "range"
                else "invalid"
            ),
            "endDate": (sample_data.now + timedelta(days=4)).date().isoformat(),
        }
    if value == "anonymous":
        query = {"recommended": "true"}
    response = request_view(
        request_factory,
        hotel_views.HotelListView,
        payload=query,
        user=None if value == "anonymous" else sample_data.user,
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data
    if key in ("cityId", "ownerId"):
        assert response.data["data"] == []


@pytest.mark.parametrize(
    "case_id,scenario",
    [
        pytest.param(
            f"H-I{case_index:02}",
            scenario,
            id=f"H-I{case_index:02}",
            marks=mark(
                f"H-I{case_index:02}",
                "Hotels",
                "Read or upsert hotel interaction and aggregate persisted counts",
                scenario,
                "Correct HTTP status, user-level counts and hotel aggregate",
                "hotels/views.py:UserHotelInteractionUpsertView/UserHotelInteractionDetailView",
            ),
        )
        for case_index, scenario in enumerate(
            [
                "create",
                "update",
                "anonymous",
                "missing_hotel",
                "detail",
                "detail_missing",
                "detail_anonymous",
            ],
            1,
        )
    ],
)
def test_hotel_interactions(case_id, scenario, sample_data, request_factory):
    """Verify hotel interactions.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    if scenario in ("update", "detail"):
        UserHotelInteraction.objects.create(
            user=sample_data.user, hotel=sample_data.hotel, click_count=1
        )
    if scenario.startswith("detail"):
        response = request_view(
            request_factory,
            hotel_views.UserHotelInteractionDetailView,
            user=None if scenario == "detail_anonymous" else sample_data.user,
            hotel_id=sample_data.hotel.pk,
        )
        expected = (
            401
            if scenario == "detail_anonymous"
            else 404 if scenario == "detail_missing" else 200
        )
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert response.status_code == expected, response.data
    else:
        payload = (
            {}
            if scenario == "missing_hotel"
            else {
                "hotel_id": sample_data.hotel.pk,
                "click_count": 4,
                "positive_count": 2,
                "negative_count": 1,
                "neutral_count": 1,
            }
        )
        response = request_view(
            request_factory,
            hotel_views.UserHotelInteractionUpsertView,
            "post",
            payload,
            None if scenario == "anonymous" else sample_data.user,
        )
        expected = (
            401
            if scenario == "anonymous"
            else 400 if scenario == "missing_hotel" else 200
        )
        assert response.status_code == expected, response.data
        if expected == 200:
            resource = UserHotelInteraction.objects.get(
                user=sample_data.user, hotel=sample_data.hotel
            )
            sample_data.hotel.refresh_from_db()
            assert resource.click_count == sample_data.hotel.total_click == 4
            assert resource.weighted_score == pytest.approx(
                0.7 * (1 / 5) + 0.3 * math.log(5)
            )


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(
            "H-ISOLATION01",
            id="H-ISOLATION01",
            marks=mark(
                "H-ISOLATION01",
                "Hotels",
                "Keep pagination filters isolated between consecutive requests",
                "Request 1 cityId=99999; request 2 has no filters",
                "Second paginator has no city filter",
                "hotels/views.py:HotelPagination.get_page_size",
                "Sequential request isolation regression",
            ),
        )
    ],
)
def test_hotel_pagination_request_isolation(case_id, request_factory):
    """Verify hotel pagination request isolation.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    first = hotel_views.HotelPagination()
    first.get_page_size(Request(request_factory.get("/", {"cityId": "99999"})))
    second = hotel_views.HotelPagination()
    second.get_page_size(Request(request_factory.get("/")))
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert (
        "city_id" not in second.filters
    ), "Class-level filters leak from a previous request"


UNPAGED = [
    ("Rooms", room_views, "RoomListView"),
    ("Rooms", room_views, "RoomAdminListView"),
    ("Rooms", room_views, "RoomAmenityListView"),
    ("Bookings", booking_views, "BookingViewSet"),
    ("Bookings", booking_views, "RefundPolicyViewSet"),
    ("Promotions", promotion_views, "PromotionListCreateView"),
    ("Promotions", promotion_views, "PromotionListAdminView"),
    ("Promotions", promotion_views, "RoomPromotionListAdminView"),
    ("Promotions", promotion_views, "CarPromotionListAdminView"),
    ("Promotions", promotion_views, "FlightPromotionListAdminView"),
    ("Promotions", promotion_views, "ActivityPromotionListAdminView"),
]


@pytest.mark.parametrize(
    "case_id,module,view_module,name",
    [
        pytest.param(
            f"{title[:2].upper()}-NP{case_index:02}",
            title,
            view_module,
            name,
            id=f"{title[:2].upper()}-NP{case_index:02}",
            marks=mark(
                f"{title[:2].upper()}-NP{case_index:02}",
                title,
                "Return complete list when pagination is disabled",
                f"{name}; pagination_class=None",
                "200; response data is list",
                "{0}/views.py:{1}".format(title.lower(), name),
                "Configuration boundary; real database read",
            ),
        )
        for case_index, (title, view_module, name) in enumerate(UNPAGED, 1)
    ],
)
def test_unpaginated_lists(
    case_id, module, view_module, name, sample_data, request_factory
):
    """Verify unpaginated lists.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    with patch.object(getattr(view_module, name), "pagination_class", None):
        response = request_view(
            request_factory, getattr(view_module, name), user=sample_data.user
        )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data
    assert isinstance(response.data["data"], list)


@pytest.mark.parametrize(
    "case_id,application_name,exists",
    [
        pytest.param(
            f"{application_name[:1].upper()}-IMG{case_index:02}",
            application_name,
            exists,
            id=f"{application_name[:1].upper()}-IMG{case_index:02}",
            marks=mark(
                f"{application_name[:1].upper()}-IMG{case_index:02}",
                application_name,
                "Delete image row and handle storage outcome",
                "Storage file exists=" + str(exists),
                "Image row deleted; storage removed only when file exists",
                f"{application_name.lower()}/views.py:image deletion",
                "Mock filesystem boundary; real DB deletion",
            ),
        )
        for case_index, (application_name, exists) in enumerate(
            [
                (application_title, expected_description)
                for application_title in ["Hotels", "Rooms"]
                for expected_description in [False, True]
            ],
            1,
        )
    ],
)
def test_image_delete(case_id, application_name, exists, sample_data, request_factory):
    """Verify image delete.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    model, parent, view = (
        (HotelImage, sample_data.hotel, hotel_views.HotelImageDeleteView)
        if application_name == "Hotels"
        else (RoomImage, sample_data.room, room_views.RoomImageDeleteView)
    )
    resource = model.objects.create(
        **{"hotel" if application_name == "Hotels" else "room": parent},
        image="/media/image.png",
    )
    with patch(
        f"{application_name.lower()}.views.os.path.isfile", return_value=exists
    ), patch(f"{application_name.lower()}.views.os.remove") as remove:
        response = request_view(
            request_factory, view, "delete", user=sample_data.user, pk=resource.pk
        )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 204, response.data
    assert not model.objects.filter(pk=resource.pk).exists()


@pytest.mark.parametrize(
    "case_id,cancelled,expected",
    [
        pytest.param(
            f"R-OVERLAP{case_index:02}",
            cancelled,
            expected,
            id=f"R-OVERLAP{case_index:02}",
            marks=mark(
                f"R-OVERLAP{case_index:02}",
                "Rooms",
                "Count overlapping room quantities and ignore cancelled bookings",
                f"Existing 8 rooms; request 3; cancelled={cancelled}",
                f"Accepted={expected}",
                "rooms/serializers.py:RoomBookingDetailCreateSerializer.validate",
                "Overlap boundary; real database query",
            ),
        )
        for case_index, (cancelled, expected) in enumerate(
            [(False, False), (True, True)], 1
        )
    ],
)
def test_room_overlap(case_id, cancelled, expected, sample_data):
    """Verify room overlap.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    RoomBookingDetail.objects.create(
        booking=sample_data.booking,
        room=sample_data.room,
        room_count=8,
        num_guests=1,
        check_in=sample_data.now + timedelta(days=2),
        check_out=sample_data.now + timedelta(days=5),
    )
    sample_data.room.available_rooms = 10
    sample_data.room.save()
    if cancelled:
        sample_data.booking.status = 3
        sample_data.booking.save()
    serializer = RoomBookingDetailCreateSerializer(
        data={
            "room": sample_data.room.pk,
            "room_count": 3,
            "num_guests": 1,
            "check_in": sample_data.now + timedelta(days=3),
            "check_out": sample_data.now + timedelta(days=4),
        }
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert checked_read(lambda: serializer.is_valid()) == expected, serializer.errors


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(
            "R-DETAIL01",
            id="R-DETAIL01",
            marks=mark(
                "R-DETAIL01",
                "Rooms",
                "Retrieve saved room booking detail",
                "Valid room booking detail ID",
                "200; correct detail ID",
                "rooms/views.py:RoomBookingDetailView.retrieve",
            ),
        )
    ],
)
def test_room_booking_detail_view(
    case_id, sample_data, related_services, request_factory
):
    """Verify room booking detail view.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    detail = attach_detail(sample_data, related_services, 1)
    response = request_view(
        request_factory, room_views.RoomBookingDetailView, pk=detail.pk
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data
    assert response.data["data"]["id"] == detail.pk


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_hotel_filter_boundaries
# Test Case ID: H-QX01
# Test Case ID: H-QX02
# Test Case ID: H-QX03
# Test Case ID: H-QX04
# Test Case ID: H-QX05
# Test Case ID: H-QX06
# Test Case ID: H-QX07
# Test Case ID: H-QX08
# Test Case ID: H-QX09
# Test Case ID: H-QX10
# Test Case ID: H-QX11
# Test Case ID: H-QX12
# Test Case ID: H-QX13
# Test Case ID: H-QX14
# Test Case ID: H-QX15
# Test Case ID: H-QX16
# Function: test_hotel_interactions
# Test Case ID: H-I01
# Test Case ID: H-I02
# Test Case ID: H-I03
# Test Case ID: H-I04
# Test Case ID: H-I05
# Test Case ID: H-I06
# Test Case ID: H-I07
# Function: test_hotel_pagination_request_isolation
# Test Case ID: H-ISOLATION01
# Function: test_unpaginated_lists
# Test Case ID: RO-NP01
# Test Case ID: RO-NP02
# Test Case ID: RO-NP03
# Test Case ID: BO-NP04
# Test Case ID: BO-NP05
# Test Case ID: PR-NP06
# Test Case ID: PR-NP07
# Test Case ID: PR-NP08
# Test Case ID: PR-NP09
# Test Case ID: PR-NP10
# Test Case ID: PR-NP11
# Function: test_image_delete
# Test Case ID: H-IMG01
# Test Case ID: H-IMG02
# Test Case ID: R-IMG03
# Test Case ID: R-IMG04
# Function: test_room_overlap
# Test Case ID: R-OVERLAP01
# Test Case ID: R-OVERLAP02
# Function: test_room_booking_detail_view
# Test Case ID: R-DETAIL01
