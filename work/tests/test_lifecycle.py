"""Booking lifecycle, refund calculation and payment state transitions."""
from datetime import datetime,date,timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from django.utils import timezone
from bookings.models import Booking,GuestInfo,RefundPolicy
from bookings.views import BookingViewSet
from bookings.constants.booking_status import BookingStatus
from payments.constants.payment_status import PaymentStatus
from payments.constants.payment_method import PaymentMethod
from payments.models import Payment
from payments.views import PaymentViewSet,PaymentListOverviewView
from rooms.models import RoomBookingDetail
from cars.models import CarBookingDetail
from flights.models import FlightBookingDetail
from activities.models import ActivityDateBookingDetail
from test_views import request_view

def mark(cid,module,objective,inputs,expected,target,technique='Decision table; state transition; CheckDB'):
    return pytest.mark.case(module=module,objective=objective,inputs=inputs,expected=expected,target=target,technique=technique)

REFUNDS=[('B-R01',None,None,None,100),('B-R02',1,None,None,100),('B-R03',3,None,None,0),('B-R04',2,25,None,25),('B-R05',2,None,30,30),('B-R06',2,None,300,100),('B-R07',2,None,None,50),('B-R08',99,None,None,100),('B-R09',2,150,None,100)]
@pytest.mark.parametrize('cid,kind,percent,amount,expected',[
 pytest.param(*v,id=v[0],marks=mark(v[0],'Bookings','Calculate policy refund from final price',f'final=100; policy={v[1]}; percent={v[2]}; fixed={v[3]}',f'Refund={v[4]}','bookings/views.py:BookingViewSet.calculate_refund_amount')) for v in REFUNDS])
def test_refund_policy_decisions(cid,kind,percent,amount,expected,data):
    """Test Case IDs B-R01...B-R09: absent/full/none/partial refund boundaries."""
    if kind is not None:RefundPolicy.objects.create(name='Policy',service_type=1,policy_type=kind,refund_percentage=percent,refund_amount=amount,hours_before_start=24)
    assert BookingViewSet().calculate_refund_amount(data.booking)==expected

@pytest.mark.parametrize('cid,value,expected',[
 pytest.param('B-D01',None,None,id='B-D01',marks=mark('B-D01','Bookings','Keep missing datetime as None','None','None','bookings/views.py:ensure_datetime')),
 pytest.param('B-D02',date(2030,1,2),datetime(2030,1,2),id='B-D02',marks=mark('B-D02','Bookings','Convert date to midnight','2030-01-02','2030-01-02 00:00:00','bookings/views.py:ensure_datetime')),
 pytest.param('B-D03',datetime(2030,1,2,12),datetime(2030,1,2,12),id='B-D03',marks=mark('B-D03','Bookings','Preserve datetime','2030-01-02 12:00','Unchanged datetime','bookings/views.py:ensure_datetime')),
 pytest.param('B-D04','invalid','invalid',id='B-D04',marks=mark('B-D04','Bookings','Preserve non-date value in conversion helper','invalid','Unchanged string','bookings/views.py:ensure_datetime'))])
def test_datetime_conversion(cid,value,expected):
    """Test Case IDs B-D01...B-D04."""
    assert BookingViewSet().ensure_datetime(value)==expected

@pytest.mark.parametrize('cid,scenario',[
 pytest.param(f'B-G{i:02}',s,id=f'B-G{i:02}',marks=mark(f'B-G{i:02}','Bookings','Refund payment through isolated gateway',s,'Expected gateway result and exact API call; no gateway for unpaid/cash','bookings/views.py:process_payment_refund')) for i,s in enumerate(['unpaid','online_ok','online_error','cash'],1)])
def test_refund_gateway(cid,scenario,data):
    p=data.payment;p.status=PaymentStatus.SUCCESS if scenario!='unpaid' else PaymentStatus.PENDING;p.transaction_id='pi_unit';p.method=2 if scenario=='cash' else 1;p.save()
    with patch('bookings.views.stripe.Refund.create') as refund:
        refund.return_value=SimpleNamespace(id='re_unit')
        if scenario=='online_error':refund.side_effect=RuntimeError('Gateway unavailable')
        result=BookingViewSet().process_payment_refund(data.booking,20)
        if scenario=='online_ok':
            assert result.id=='re_unit'
            # Checkout explicitly uses zero-decimal VND. Refund must use same units.
            assert refund.call_args.kwargs['amount']==20, f"Expected VND 20, observed gateway amount {refund.call_args.kwargs['amount']}"
        else:assert result is None
        if scenario in ('cash','unpaid'):refund.assert_not_called()

@pytest.mark.parametrize('cid,status,policy,expected_code',[
 pytest.param(f'B-C{i:02}',status,policy,code,id=f'B-C{i:02}',marks=mark(f'B-C{i:02}','Bookings','Cancel booking according to lifecycle and refund policy',f'status={status}; policy={policy}',f'HTTP {code}; persisted cancellation only if allowed','bookings/views.py:cancel_booking')) for i,(status,policy,code) in enumerate([(1,1,200),(2,1,200),(3,1,400),(4,1,400),(5,1,400),(1,3,200)],1)])
def test_cancel_booking(cid,status,policy,expected_code,data,factory):
    """Test Case IDs B-C01...B-C06: cancellation rejection and zero-refund path."""
    b=data.booking;b.status=status;b.save()
    RefundPolicy.objects.create(service_type=1,name='Policy',policy_type=policy)
    response=request_view(factory,BookingViewSet,'post',action='cancel_booking',pk=b.pk)
    assert response.status_code==expected_code,response.data
    b.refresh_from_db()
    if expected_code==200:
        assert b.status==BookingStatus.CANCELLED
        assert b.refund_amount==(100 if policy==1 else 0)
    else:assert b.status==status

def attach_detail(data,services,kind):
    """Build a complete real booking graph for payment notifications."""
    b=data.booking;b.service_type=kind;b.save()
    GuestInfo.objects.create(booking=b,full_name='Alice',email='alice@example.com',phone='123')
    if kind==1:detail=RoomBookingDetail.objects.create(booking=b,room=data.room,check_in=data.now+timedelta(days=3),check_out=data.now+timedelta(days=4),num_guests=2)
    elif kind==2:detail=CarBookingDetail.objects.create(booking=b,car=services.car,driver=data.user,pickup_datetime=data.now+timedelta(days=3),dropoff_datetime=data.now+timedelta(days=3,hours=2),distance_km=10,total_time_estimate=2)
    elif kind==3:detail=FlightBookingDetail.objects.create(booking=b,flight=services.flight,num_passengers=1)
    elif kind==4:detail=ActivityDateBookingDetail.objects.create(booking=b,activity_date=services.ad,date_launch=services.ad.date_launch,price_adult=50,price_child=25,adult_quantity_booking=1,child_quantity_booking=1)
    else:detail=None
    b.refresh_from_db();return detail

@pytest.mark.parametrize('cid,kind,mode',[
 pytest.param(f'P-L{i:02}',kind,mode,id=f'P-L{i:02}',marks=mark(f'P-L{i:02}','Payments','Update payment, booking and notification on gateway result or cash selection',f'service={kind}; mode={mode}', 'Paid: SUCCESS/CONFIRMED/PAID; cash: UNPAID/CONFIRMED; unpaid: failure response','payments/views.py:PaymentViewSet.capture/confirm_cash')) for i,(kind,mode) in enumerate([(k,m) for k in [1,2,3,4,5] for m in ['paid','unpaid','cash','no_email']],1)])
def test_payment_lifecycle(cid,kind,mode,data,services,factory):
    """Test Case IDs P-L01...P-L20: service-specific notification branches."""
    attach_detail(data,services,kind)
    from accounts.models import CustomUser
    CustomUser.objects.create_user(username='admin_recipient',role='admin',email='admin@example.com')
    p=data.payment;p.method=2 if mode=='cash' else 1;p.transaction_id='cs_unit';p.save()
    if mode=='no_email':
        data.user.email='';data.user.save();GuestInfo.objects.filter(booking=data.booking).delete()
    with patch('payments.views.stripe.checkout.Session.retrieve',return_value=SimpleNamespace(payment_status='unpaid' if mode=='unpaid' else 'paid')),patch('payments.views.Notification.objects.create') as notification:
        response=request_view(factory,PaymentViewSet,'post',action='confirm_cash' if mode=='cash' else 'capture',pk=p.pk)
        assert response.status_code==(400 if mode=='unpaid' else 200),response.data
        p.refresh_from_db();data.booking.refresh_from_db()
        if mode!='unpaid':
            assert int(p.status)==(PaymentStatus.UNPAID if mode=='cash' else PaymentStatus.SUCCESS)
            assert data.booking.status==BookingStatus.CONFIRMED
            assert data.booking.payment_status==(PaymentStatus.UNPAID if mode=='cash' else PaymentStatus.PAID)
        if mode=='no_email':notification.assert_not_called()

@pytest.mark.parametrize('cid',[pytest.param('P-CASH01',id='P-CASH01',marks=mark('P-CASH01','Payments','Reject cash confirmation on online payment','method=ONLINE','HTTP 400; payment unchanged','payments/views.py:confirm_cash'))])
def test_reject_cash_on_online(cid,data,factory):
    response=request_view(factory,PaymentViewSet,'post',action='confirm_cash',pk=data.payment.pk)
    assert response.status_code==400
    data.payment.refresh_from_db();assert int(data.payment.status)==PaymentStatus.PENDING

@pytest.mark.parametrize('cid,period',[
 pytest.param(f'P-O{i:02}',p,id=f'P-O{i:02}',marks=mark(f'P-O{i:02}','Payments','Aggregate payment revenue over more than one period',f'Two payments in different years; statistic_by={p}','Revenue total equals sum of all periods; labels and series have equal lengths','payments/views.py:PaymentListOverviewView.list')) for i,p in enumerate(['day','month','quarter','year'],1)])
def test_payment_overview_totals(cid,period,data,factory):
    b=Booking.objects.create(service_type=1,user=data.user)
    p=Payment.objects.create(booking=b,amount=200,method=1)
    Payment.objects.filter(pk=data.payment.pk).update(created_at=data.now-timedelta(days=400))
    response=request_view(factory,PaymentListOverviewView,payload={'statistic_by':period})
    assert response.status_code==200
    out=response.data['data'];assert out['total_revenue']==300,f"Expected total 300; observed {out['total_revenue']}; period revenues={out['revenues']}"
    assert len(out['labels'])==len(out['revenues'])==2

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: B-C01
# Test Case ID: B-C02
# Test Case ID: B-C03
# Test Case ID: B-C04
# Test Case ID: B-C05
# Test Case ID: B-C06
# Test Case ID: B-D01
# Test Case ID: B-D02
# Test Case ID: B-D03
# Test Case ID: B-D04
# Test Case ID: B-G01
# Test Case ID: B-G02
# Test Case ID: B-G03
# Test Case ID: B-G04
# Test Case ID: B-R01
# Test Case ID: B-R02
# Test Case ID: B-R03
# Test Case ID: B-R04
# Test Case ID: B-R05
# Test Case ID: B-R06
# Test Case ID: B-R07
# Test Case ID: B-R08
# Test Case ID: B-R09
# Test Case ID: P-CASH01
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
# Test Case ID: P-O01
# Test Case ID: P-O02
# Test Case ID: P-O03
# Test Case ID: P-O04
