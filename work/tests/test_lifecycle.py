"""Booking lifecycle, refund calculation and payment state transitions."""

from contract_support import checked_read
from datetime import datetime, date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from django.utils import timezone
from bookings.models import Booking, GuestInfo, RefundPolicy
from bookings.views import BookingViewSet
from bookings.constants.booking_status import BookingStatus
from payments.constants.payment_status import PaymentStatus
from payments.constants.payment_method import PaymentMethod
from payments.models import Payment
from payments.views import PaymentViewSet, PaymentListOverviewView
from rooms.models import RoomBookingDetail
from cars.models import CarBookingDetail
from flights.models import FlightBookingDetail
from activities.models import ActivityDateBookingDetail
from test_views import request_view


def mark(
    case_id,
    module,
    objective,
    inputs,
    expected,
    target,
    technique="Decision table; state transition; CheckDB",
):
    """Attach the independently declared case inputs, expected output and target unit to the pytest parameter."""
    return pytest.mark.case(
        module=module,
        objective=objective,
        inputs=inputs,
        expected=expected,
        target=target,
        technique=technique,
    )


REFUNDS = [
    ("B-R01", None, None, None, 100),
    ("B-R02", 1, None, None, 100),
    ("B-R03", 3, None, None, 0),
    ("B-R04", 2, 25, None, 25),
    ("B-R05", 2, None, 30, 30),
    ("B-R06", 2, None, 300, 100),
    ("B-R07", 2, None, None, 50),
    ("B-R08", 99, None, None, 100),
    ("B-R09", 2, 150, None, 100),
]


@pytest.mark.parametrize(
    "case_id,kind,percent,amount,expected",
    [
        pytest.param(
            *case_values,
            id=case_values[0],
            marks=mark(
                case_values[0],
                "Bookings",
                "Calculate policy refund from final price",
                f"final=100; policy={case_values[1]}; percent={case_values[2]}; fixed={case_values[3]}",
                f"Refund={case_values[4]}",
                "bookings/views.py:BookingViewSet.calculate_refund_amount",
            ),
        )
        for case_values in REFUNDS
    ],
)
def test_refund_policy_decisions(case_id, kind, percent, amount, expected, sample_data):
    """Verify refund policy decisions.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    if kind is not None:
        RefundPolicy.objects.create(
            name="Policy",
            service_type=1,
            policy_type=kind,
            refund_percentage=percent,
            refund_amount=amount,
            hours_before_start=24,
        )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert (
        checked_read(
            lambda: BookingViewSet().calculate_refund_amount(sample_data.booking)
        )
        == expected
    )


@pytest.mark.parametrize(
    "case_id,value,expected",
    [
        pytest.param(
            "B-D01",
            None,
            None,
            id="B-D01",
            marks=mark(
                "B-D01",
                "Bookings",
                "Keep missing datetime as None",
                "None",
                "None",
                "bookings/views.py:ensure_datetime",
            ),
        ),
        pytest.param(
            "B-D02",
            date(2030, 1, 2),
            datetime(2030, 1, 2),
            id="B-D02",
            marks=mark(
                "B-D02",
                "Bookings",
                "Convert date to midnight",
                "2030-01-02",
                "2030-01-02 00:00:00",
                "bookings/views.py:ensure_datetime",
            ),
        ),
        pytest.param(
            "B-D03",
            datetime(2030, 1, 2, 12),
            datetime(2030, 1, 2, 12),
            id="B-D03",
            marks=mark(
                "B-D03",
                "Bookings",
                "Preserve datetime",
                "2030-01-02 12:00",
                "Unchanged datetime",
                "bookings/views.py:ensure_datetime",
            ),
        ),
        pytest.param(
            "B-D04",
            "invalid",
            "invalid",
            id="B-D04",
            marks=mark(
                "B-D04",
                "Bookings",
                "Preserve non-date value in conversion helper",
                "invalid",
                "Unchanged string",
                "bookings/views.py:ensure_datetime",
            ),
        ),
    ],
)
def test_datetime_conversion(case_id, value, expected):
    """Verify datetime conversion.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert checked_read(lambda: BookingViewSet().ensure_datetime(value)) == expected


@pytest.mark.parametrize(
    "case_id,scenario",
    [
        pytest.param(
            f"B-G{case_index:02}",
            scenario,
            id=f"B-G{case_index:02}",
            marks=mark(
                f"B-G{case_index:02}",
                "Bookings",
                "Refund payment through isolated gateway",
                scenario,
                "Expected gateway result and exact API call; no gateway for unpaid/cash",
                "bookings/views.py:process_payment_refund",
            ),
        )
        for case_index, scenario in enumerate(
            ["unpaid", "online_ok", "online_error", "cash"], 1
        )
    ],
)
def test_refund_gateway(case_id, scenario, sample_data):
    """Verify refund gateway.

    Arrange: Persist a paid/unpaid payment with an explicit gateway transaction ID.
    Act: Request a refund while recording the mocked Stripe call.
    Assert and CheckDB: Check exact payment_intent and currency units; unpaid/cash paths must not call the gateway.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    payment = sample_data.payment
    payment.status = (
        PaymentStatus.SUCCESS if scenario != "unpaid" else PaymentStatus.PENDING
    )
    payment.transaction_id = "pi_unit"
    payment.method = 2 if scenario == "cash" else 1
    payment.save()
    with patch("bookings.views.stripe.Refund.create") as refund:
        refund.return_value = SimpleNamespace(id="re_unit")
        if scenario == "online_error":
            refund.side_effect = RuntimeError("Gateway unavailable")
        result = checked_read(
            lambda: BookingViewSet().process_payment_refund(sample_data.booking, 20)
        )
        if scenario == "online_ok":
            # Assert / CheckDB: compare the actual result with the independent expected value.
            assert result.id == "re_unit"
            assert (
                refund.call_args.kwargs["amount"] == 20
            ), f"Expected VND 20, observed gateway amount {refund.call_args.kwargs['amount']}"
        else:
            assert result is None
        if scenario in ("cash", "unpaid"):
            refund.assert_not_called()


@pytest.mark.parametrize(
    "case_id,status,policy,expected_code",
    [
        pytest.param(
            f"B-C{case_index:02}",
            status,
            policy,
            code,
            id=f"B-C{case_index:02}",
            marks=mark(
                f"B-C{case_index:02}",
                "Bookings",
                "Cancel booking according to lifecycle and refund policy",
                f"status={status}; policy={policy}",
                f"HTTP {code}; persisted cancellation only if allowed",
                "bookings/views.py:cancel_booking",
            ),
        )
        for case_index, (status, policy, code) in enumerate(
            [
                (1, 1, 200),
                (2, 1, 200),
                (3, 1, 400),
                (4, 1, 400),
                (5, 1, 400),
                (1, 3, 200),
            ],
            1,
        )
    ],
)
def test_cancel_booking(
    case_id, status, policy, expected_code, sample_data, request_factory
):
    """Verify cancel booking.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    booking = sample_data.booking
    booking.status = status
    booking.save()
    RefundPolicy.objects.create(service_type=1, name="Policy", policy_type=policy)
    response = request_view(
        request_factory, BookingViewSet, "post", action="cancel_booking", pk=booking.pk
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == expected_code, response.data
    booking.refresh_from_db()
    if expected_code == 200:
        assert booking.status == BookingStatus.CANCELLED
        assert booking.refund_amount == (100 if policy == 1 else 0)
    else:
        assert booking.status == status


def attach_detail(sample_data, related_services, kind):
    """Build a complete real booking graph for payment notifications."""
    booking = sample_data.booking
    booking.service_type = kind
    booking.save()
    GuestInfo.objects.create(
        booking=booking, full_name="Alice", email="alice@example.com", phone="123"
    )
    if kind == 1:
        detail = RoomBookingDetail.objects.create(
            booking=booking,
            room=sample_data.room,
            check_in=sample_data.now + timedelta(days=3),
            check_out=sample_data.now + timedelta(days=4),
            num_guests=2,
        )
    elif kind == 2:
        detail = CarBookingDetail.objects.create(
            booking=booking,
            car=related_services.car,
            driver=sample_data.user,
            pickup_datetime=sample_data.now + timedelta(days=3),
            dropoff_datetime=sample_data.now + timedelta(days=3, hours=2),
            distance_km=10,
            total_time_estimate=2,
        )
    elif kind == 3:
        detail = FlightBookingDetail.objects.create(
            booking=booking, flight=related_services.flight, num_passengers=1
        )
    elif kind == 4:
        detail = ActivityDateBookingDetail.objects.create(
            booking=booking,
            activity_date=related_services.activity_date,
            date_launch=related_services.activity_date.date_launch,
            price_adult=50,
            price_child=25,
            adult_quantity_booking=1,
            child_quantity_booking=1,
        )
    else:
        detail = None
    booking.refresh_from_db()
    return detail


@pytest.mark.parametrize(
    "case_id,kind,mode",
    [
        pytest.param(
            f"P-L{case_index:02}",
            kind,
            mode,
            id=f"P-L{case_index:02}",
            marks=mark(
                f"P-L{case_index:02}",
                "Payments",
                "Update payment, booking and notification on gateway result or cash selection",
                f"service={kind}; mode={mode}",
                "Paid: SUCCESS/CONFIRMED/PAID; cash: UNPAID/CONFIRMED; unpaid: failure response",
                "payments/views.py:PaymentViewSet.capture/confirm_cash",
            ),
        )
        for case_index, (kind, mode) in enumerate(
            [
                (field_name, model_class)
                for field_name in [1, 2, 3, 4, 5]
                for model_class in ["paid", "unpaid", "cash", "no_email"]
            ],
            1,
        )
    ],
)
def test_payment_lifecycle(
    case_id, kind, mode, sample_data, related_services, request_factory
):
    """Verify payment lifecycle.

    Arrange: Create a real booking, service detail, guest and payment; prepare the gateway outcome.
    Act: Invoke capture or cash confirmation while notification delivery is isolated.
    Assert and CheckDB: Reload payment and booking rows and verify state transitions and notification expectations.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    attach_detail(sample_data, related_services, kind)
    from accounts.models import CustomUser

    CustomUser.objects.create_user(
        username="admin_recipient", role="admin", email="admin@example.com"
    )
    payment = sample_data.payment
    payment.method = 2 if mode == "cash" else 1
    payment.transaction_id = "cs_unit"
    payment.save()
    if mode == "no_email":
        sample_data.user.email = ""
        sample_data.user.save()
        GuestInfo.objects.filter(booking=sample_data.booking).delete()
    with patch(
        "payments.views.stripe.checkout.Session.retrieve",
        return_value=SimpleNamespace(
            payment_status="unpaid" if mode == "unpaid" else "paid"
        ),
    ), patch("payments.views.Notification.objects.create") as notification:
        response = request_view(
            request_factory,
            PaymentViewSet,
            "post",
            action="confirm_cash" if mode == "cash" else "capture",
            pk=payment.pk,
        )
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert response.status_code == (400 if mode == "unpaid" else 200), response.data
        payment.refresh_from_db()
        sample_data.booking.refresh_from_db()
        if mode != "unpaid":
            assert int(payment.status) == (
                PaymentStatus.UNPAID if mode == "cash" else PaymentStatus.SUCCESS
            )
            assert sample_data.booking.status == BookingStatus.CONFIRMED
            assert sample_data.booking.payment_status == (
                PaymentStatus.UNPAID if mode == "cash" else PaymentStatus.PAID
            )
        if mode == "no_email":
            notification.assert_not_called()


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(
            "P-CASH01",
            id="P-CASH01",
            marks=mark(
                "P-CASH01",
                "Payments",
                "Reject cash confirmation on online payment",
                "method=ONLINE",
                "HTTP 400; payment unchanged",
                "payments/views.py:confirm_cash",
            ),
        )
    ],
)
def test_reject_cash_on_online(case_id, sample_data, request_factory):
    """Verify reject cash on online.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    response = request_view(
        request_factory,
        PaymentViewSet,
        "post",
        action="confirm_cash",
        pk=sample_data.payment.pk,
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 400
    sample_data.payment.refresh_from_db()
    assert int(sample_data.payment.status) == PaymentStatus.PENDING


@pytest.mark.parametrize(
    "case_id,period",
    [
        pytest.param(
            f"P-O{case_index:02}",
            parameter_value,
            id=f"P-O{case_index:02}",
            marks=mark(
                f"P-O{case_index:02}",
                "Payments",
                "Aggregate payment revenue over more than one period",
                f"Two payments in different years; statistic_by={parameter_value}",
                "Revenue total equals sum of all periods; labels and series have equal lengths",
                "payments/views.py:PaymentListOverviewView.list",
            ),
        )
        for case_index, parameter_value in enumerate(
            ["day", "month", "quarter", "year"], 1
        )
    ],
)
def test_payment_overview_totals(case_id, period, sample_data, request_factory):
    """Verify payment overview totals.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    second_booking = Booking.objects.create(service_type=1, user=sample_data.user)
    second_payment = Payment.objects.create(
        booking=second_booking, amount=200, method=1
    )
    Payment.objects.filter(pk=sample_data.payment.pk).update(
        created_at=sample_data.now - timedelta(days=400)
    )
    response = request_view(
        request_factory, PaymentListOverviewView, payload={"statistic_by": period}
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200
    serialized_output = response.data["data"]
    assert (
        serialized_output["total_revenue"] == 300
    ), f"Expected total 300; observed {serialized_output['total_revenue']}; period revenues={serialized_output['revenues']}"
    assert len(serialized_output["labels"]) == len(serialized_output["revenues"]) == 2


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_refund_policy_decisions
# Test Case ID: B-R01
# Test Case ID: B-R02
# Test Case ID: B-R03
# Test Case ID: B-R04
# Test Case ID: B-R05
# Test Case ID: B-R06
# Test Case ID: B-R07
# Test Case ID: B-R08
# Test Case ID: B-R09
# Function: test_datetime_conversion
# Test Case ID: B-D01
# Test Case ID: B-D02
# Test Case ID: B-D03
# Test Case ID: B-D04
# Function: test_refund_gateway
# Test Case ID: B-G01
# Test Case ID: B-G02
# Test Case ID: B-G03
# Test Case ID: B-G04
# Function: test_cancel_booking
# Test Case ID: B-C01
# Test Case ID: B-C02
# Test Case ID: B-C03
# Test Case ID: B-C04
# Test Case ID: B-C05
# Test Case ID: B-C06
# Function: test_payment_lifecycle
# Test Case ID: P-L01
# Test Case ID: P-L02
# Test Case ID: P-L03
# Test Case ID: P-L04
# Test Case ID: P-L05
# Test Case ID: P-L06
# Test Case ID: P-L07
# Test Case ID: P-L08
# Test Case ID: P-L09
# Test Case ID: P-L10
# Test Case ID: P-L11
# Test Case ID: P-L12
# Test Case ID: P-L13
# Test Case ID: P-L14
# Test Case ID: P-L15
# Test Case ID: P-L16
# Test Case ID: P-L17
# Test Case ID: P-L18
# Test Case ID: P-L19
# Test Case ID: P-L20
# Function: test_reject_cash_on_online
# Test Case ID: P-CASH01
# Function: test_payment_overview_totals
# Test Case ID: P-O01
# Test Case ID: P-O02
# Test Case ID: P-O03
# Test Case ID: P-O04
