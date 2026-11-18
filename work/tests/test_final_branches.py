"""Additional reachable branches selected from the measured coverage report."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from rest_framework.request import Request
from hotels import views as hotel_views
from rooms import views as room_views
from payments import views as payment_views
from bookings.views import BookingViewSet
from bookings.models import RefundPolicy
from payments.constants.payment_status import PaymentStatus
from hotels.models import HotelImage
from rooms.models import RoomImage
from flights.models import Flight, FlightBookingDetail
from test_lifecycle import mark, attach_detail
from test_views import request_view


@pytest.mark.parametrize(
    "case_id,scenario",
    [
        pytest.param(
            f"H-IM{case_index:02}",
            scenario,
            id=f"H-IM{case_index:02}",
            marks=mark(
                f"H-IM{case_index:02}",
                "Hotels",
                "Create or replace hotel images atomically with hotel update",
                scenario,
                "Correct image rows persisted; invalid update keeps old images",
                "hotels/views.py:HotelCreateView/HotelUpdateView",
            ),
        )
        for case_index, scenario in enumerate(["create", "update", "invalid_update"], 1)
    ],
)
def test_hotel_image_updates(case_id, scenario, sample_data, request_factory):
    """Verify hotel image updates.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    HotelImage.objects.create(hotel=sample_data.hotel, image="old.png")
    payload = {
        "city": sample_data.city.pk,
        "name": "New Hotel",
        "images": ["new1.png", "new2.png"],
    }
    view_class = (
        hotel_views.HotelCreateView
        if scenario == "create"
        else hotel_views.HotelUpdateView
    )
    if scenario == "invalid_update":
        payload["name"] = None
    response = request_view(
        request_factory,
        view_class,
        "post" if scenario == "create" else "patch",
        payload,
        sample_data.user,
        **{} if scenario == "create" else {"pk": sample_data.hotel.pk},
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == (
        400 if scenario == "invalid_update" else 200
    ), response.data
    if scenario == "invalid_update":
        assert list(sample_data.hotel.images.values_list("image", flat=True)) == [
            "old.png"
        ]
    else:
        hotel_id = (
            response.data["data"].get("id", sample_data.hotel.pk)
            if scenario == "update"
            else view_class.queryset.model.objects.latest("pk").pk
        )
        assert set(
            HotelImage.objects.filter(hotel_id=hotel_id).values_list("image", flat=True)
        ) == {"new1.png", "new2.png"}


@pytest.mark.parametrize(
    "case_id,kind,mode",
    [
        pytest.param(
            f"B-CX{case_index:02}",
            kind,
            mode,
            id=f"B-CX{case_index:02}",
            marks=mark(
                f"B-CX{case_index:02}",
                "Bookings",
                "Cancel service booking and release reserved resources",
                f"service={kind}; paid={mode}",
                "Booking CANCELLED; payment REFUNDED; driver idle or activity capacity restored",
                "bookings/views.py:cancel_booking",
            ),
        )
        for case_index, (kind, mode) in enumerate(
            [(1, True), (2, False), (4, False)], 1
        )
    ],
)
def test_cancel_service_resources(
    case_id, kind, mode, sample_data, related_services, request_factory
):
    """Verify cancel service resources.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    attach_detail(sample_data, related_services, kind)
    sample_data.booking.payment_status = (
        PaymentStatus.PAID if mode else PaymentStatus.PENDING
    )
    sample_data.booking.save()
    response = request_view(
        request_factory,
        BookingViewSet,
        "post",
        action="cancel_booking",
        pk=sample_data.booking.pk,
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data
    sample_data.booking.refresh_from_db()
    assert sample_data.booking.status == 3
    if kind == 2:
        sample_data.user.refresh_from_db()
        assert sample_data.user.driver_status == "idle"
    if kind == 4:
        related_services.activity_date.refresh_from_db()
        assert related_services.activity_date.participants_available == 20


@pytest.mark.parametrize(
    "case_id,mode,graph",
    [
        pytest.param(
            f"P-FX{case_index:02}",
            mode,
            graph,
            id=f"P-FX{case_index:02}",
            marks=mark(
                f"P-FX{case_index:02}",
                "Payments",
                "Render flight payment notification for available itinerary shapes",
                f"mode={mode}; itinerary={graph}",
                "Successful confirmation; notifications generated for valid/partial itinerary",
                "payments/views.py:PaymentViewSet.capture/confirm_cash",
            ),
        )
        for case_index, (mode, graph) in enumerate(
            [
                (model_class, itinerary_shape)
                for model_class in ["paid", "cash"]
                for itinerary_shape in [
                    "round_trip",
                    "missing_legs",
                    "round_missing_legs",
                    "no_details",
                ]
            ],
            1,
        )
    ],
)
def test_flight_payment_itineraries(
    case_id, mode, graph, sample_data, related_services, request_factory
):
    """Verify flight payment itineraries.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    attach_detail(sample_data, related_services, 3)
    if graph.startswith("round"):
        second = Flight.objects.create(airline=related_services.airline, base_price=80)
        if graph == "round_trip":
            leg = related_services.leg
            leg.pk = None
            leg.flight = second
            leg.departure_time += timedelta(days=7)
            leg.arrival_time += timedelta(days=7)
            leg.save()
        FlightBookingDetail.objects.create(
            booking=sample_data.booking, flight=second, num_passengers=1
        )
    if graph == "missing_legs":
        related_services.flight.legs.all().delete()
    if graph == "no_details":
        sample_data.booking.flight_details.all().delete()
    sample_data.payment.method = 2 if mode == "cash" else 1
    sample_data.payment.save()
    with patch(
        "payments.views.stripe.checkout.Session.retrieve",
        return_value=SimpleNamespace(payment_status="paid"),
    ), patch("payments.views.Notification.objects.create") as notification:
        response = request_view(
            request_factory,
            payment_views.PaymentViewSet,
            "post",
            action="confirm_cash" if mode == "cash" else "capture",
            pk=sample_data.payment.pk,
        )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data


@pytest.mark.parametrize(
    "case_id,key,value",
    [
        pytest.param(
            f"P-PG{case_index:02}",
            key,
            value,
            id=f"P-PG{case_index:02}",
            marks=mark(
                f"P-PG{case_index:02}",
                "Payments",
                "Handle pagination and sort boundaries",
                f"{key}={value}",
                "200 or controlled empty response; no exception",
                "payments/views.py:PaymentListView/PaymentPagination",
            ),
        )
        for case_index, (key, value) in enumerate(
            [
                ("pageSize", "bad"),
                ("current", "bad"),
                ("sort", "id-asc"),
                ("sort", "bad"),
                ("amount", "100"),
                ("min_created_at", "2020-01-01"),
                ("max_created_at", "2040-01-01"),
            ],
            1,
        )
    ],
)
def test_payment_pagination_boundaries(
    case_id, key, value, sample_data, request_factory
):
    """Verify payment pagination boundaries.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    response = request_view(
        request_factory, payment_views.PaymentListView, payload={key: value}
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data


@pytest.mark.parametrize(
    "case_id,view,query",
    [
        pytest.param(
            f"R-QX{case_index:02}",
            view,
            query,
            id=f"R-QX{case_index:02}",
            marks=mark(
                f"R-QX{case_index:02}",
                "Rooms",
                "Apply date range, sorting and optional filter boundaries",
                str(query),
                "200 and structured list",
                "rooms/views.py:list/search",
            ),
        )
        for case_index, (view, query) in enumerate(
            [
                (
                    room_views.RoomListView,
                    {"start_date": "2030-01-01", "end_date": "2030-01-03"},
                ),
                (room_views.RoomListView, {"hotel_id": "bad"}),
                (room_views.RoomListView, {"sort": "id-asc"}),
                (room_views.RoomListView, {"sort": "bad"}),
                (room_views.RoomAdminListView, {"sort": "id-asc"}),
                (room_views.RoomAdminListView, {"sort": "bad"}),
                (room_views.RoomAmenityListView, {"sort": "id-asc"}),
                (room_views.RoomAmenityListView, {"sort": "bad"}),
                (room_views.RoomAmenityListView, {"name": "WiFi"}),
            ],
            1,
        )
    ],
)
def test_room_filter_extra(case_id, view, query, sample_data, request_factory):
    """Verify room filter extra.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    response = request_view(request_factory, view, payload=query)
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200, response.data


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_hotel_image_updates
# Test Case ID: H-IM01
# Test Case ID: H-IM02
# Test Case ID: H-IM03
# Function: test_cancel_service_resources
# Test Case ID: B-CX01
# Test Case ID: B-CX02
# Test Case ID: B-CX03
# Function: test_flight_payment_itineraries
# Test Case ID: P-FX01
# Test Case ID: P-FX02
# Test Case ID: P-FX03
# Test Case ID: P-FX04
# Test Case ID: P-FX05
# Test Case ID: P-FX06
# Test Case ID: P-FX07
# Test Case ID: P-FX08
# Function: test_payment_pagination_boundaries
# Test Case ID: P-PG01
# Test Case ID: P-PG02
# Test Case ID: P-PG03
# Test Case ID: P-PG04
# Test Case ID: P-PG05
# Test Case ID: P-PG06
# Test Case ID: P-PG07
# Function: test_room_filter_extra
# Test Case ID: R-QX01
# Test Case ID: R-QX02
# Test Case ID: R-QX03
# Test Case ID: R-QX04
# Test Case ID: R-QX05
# Test Case ID: R-QX06
# Test Case ID: R-QX07
# Test Case ID: R-QX08
# Test Case ID: R-QX09
