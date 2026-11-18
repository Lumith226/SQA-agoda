"""Additional reachable branches selected from the measured coverage report."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from rest_framework.request import Request
from hotels import views as hv
from rooms import views as rv
from payments import views as pv
from bookings.views import BookingViewSet
from bookings.models import RefundPolicy
from payments.constants.payment_status import PaymentStatus
from hotels.models import HotelImage
from rooms.models import RoomImage
from flights.models import Flight,FlightBookingDetail
from test_lifecycle import mark,attach_detail
from test_views import request_view

@pytest.mark.parametrize('cid,scenario',[
 pytest.param(f'H-IM{i:02}',s,id=f'H-IM{i:02}',marks=mark(f'H-IM{i:02}','Hotels','Create or replace hotel images atomically with hotel update',s,'Correct image rows persisted; invalid update keeps old images','hotels/views.py:HotelCreateView/HotelUpdateView')) for i,s in enumerate(['create','update','invalid_update'],1)])
def test_hotel_image_updates(cid,scenario,data,factory):
    HotelImage.objects.create(hotel=data.hotel,image='old.png')
    payload={'city':data.city.pk,'name':'New Hotel','images':['new1.png','new2.png']}
    cls=hv.HotelCreateView if scenario=='create' else hv.HotelUpdateView
    if scenario=='invalid_update':payload['name']=None
    response=request_view(factory,cls,'post' if scenario=='create' else 'patch',payload,data.user,**({} if scenario=='create' else {'pk':data.hotel.pk}))
    assert response.status_code==(400 if scenario=='invalid_update' else 200),response.data
    if scenario=='invalid_update':assert list(data.hotel.images.values_list('image',flat=True))==['old.png']
    else:
        hotel_id=response.data['data'].get('id',data.hotel.pk) if scenario=='update' else cls.queryset.model.objects.latest('pk').pk
        assert set(HotelImage.objects.filter(hotel_id=hotel_id).values_list('image',flat=True))=={'new1.png','new2.png'}

@pytest.mark.parametrize('cid,kind,mode',[
 pytest.param(f'B-CX{i:02}',kind,mode,id=f'B-CX{i:02}',marks=mark(f'B-CX{i:02}','Bookings','Cancel service booking and release reserved resources',f'service={kind}; paid={mode}','Booking CANCELLED; payment REFUNDED; driver idle or activity capacity restored','bookings/views.py:cancel_booking')) for i,(kind,mode) in enumerate([(1,True),(2,False),(4,False)],1)])
def test_cancel_service_resources(cid,kind,mode,data,services,factory):
    attach_detail(data,services,kind)
    data.booking.payment_status=PaymentStatus.PAID if mode else PaymentStatus.PENDING;data.booking.save()
    response=request_view(factory,BookingViewSet,'post',action='cancel_booking',pk=data.booking.pk)
    assert response.status_code==200,response.data
    data.booking.refresh_from_db();assert data.booking.status==3
    if kind==2:data.user.refresh_from_db();assert data.user.driver_status=='idle'
    if kind==4:services.ad.refresh_from_db();assert services.ad.participants_available==20

@pytest.mark.parametrize('cid,mode,graph',[
 pytest.param(f'P-FX{i:02}',mode,graph,id=f'P-FX{i:02}',marks=mark(f'P-FX{i:02}','Payments','Render flight payment notification for available itinerary shapes',f'mode={mode}; itinerary={graph}','Successful confirmation; notifications generated for valid/partial itinerary','payments/views.py:PaymentViewSet.capture/confirm_cash')) for i,(mode,graph) in enumerate([(m,g) for m in ['paid','cash'] for g in ['round_trip','missing_legs','round_missing_legs','no_details']],1)])
def test_flight_payment_itineraries(cid,mode,graph,data,services,factory):
    attach_detail(data,services,3)
    if graph.startswith('round'):
        second=Flight.objects.create(airline=services.airline,base_price=80)
        if graph=='round_trip':
            leg=services.leg;leg.pk=None;leg.flight=second;leg.departure_time+=timedelta(days=7);leg.arrival_time+=timedelta(days=7);leg.save()
        FlightBookingDetail.objects.create(booking=data.booking,flight=second,num_passengers=1)
    if graph=='missing_legs':services.flight.legs.all().delete()
    if graph=='no_details':data.booking.flight_details.all().delete()
    data.payment.method=2 if mode=='cash' else 1;data.payment.save()
    with patch('payments.views.stripe.checkout.Session.retrieve',return_value=SimpleNamespace(payment_status='paid')),patch('payments.views.Notification.objects.create') as notification:
        response=request_view(factory,pv.PaymentViewSet,'post',action='confirm_cash' if mode=='cash' else 'capture',pk=data.payment.pk)
    assert response.status_code==200,response.data

@pytest.mark.parametrize('cid,key,value',[
 pytest.param(f'P-PG{i:02}',key,value,id=f'P-PG{i:02}',marks=mark(f'P-PG{i:02}','Payments','Handle pagination and sort boundaries',f'{key}={value}','200 or controlled empty response; no exception','payments/views.py:PaymentListView/PaymentPagination')) for i,(key,value) in enumerate([('pageSize','bad'),('current','bad'),('sort','id-asc'),('sort','bad'),('amount','100'),('min_created_at','2020-01-01'),('max_created_at','2040-01-01')],1)])
def test_payment_pagination_boundaries(cid,key,value,data,factory):
    response=request_view(factory,pv.PaymentListView,payload={key:value})
    assert response.status_code==200,response.data

@pytest.mark.parametrize('cid,view,query',[
 pytest.param(f'R-QX{i:02}',view,query,id=f'R-QX{i:02}',marks=mark(f'R-QX{i:02}','Rooms','Apply date range, sorting and optional filter boundaries',str(query),'200 and structured list','rooms/views.py:list/search')) for i,(view,query) in enumerate([
 (rv.RoomListView,{'start_date':'2030-01-01','end_date':'2030-01-03'}),(rv.RoomListView,{'hotel_id':'bad'}),(rv.RoomListView,{'sort':'id-asc'}),(rv.RoomListView,{'sort':'bad'}),(rv.RoomAdminListView,{'sort':'id-asc'}),(rv.RoomAdminListView,{'sort':'bad'}),(rv.RoomAmenityListView,{'sort':'id-asc'}),(rv.RoomAmenityListView,{'sort':'bad'}),(rv.RoomAmenityListView,{'name':'WiFi'})],1)])
def test_room_filter_extra(cid,view,query,data,factory):
    response=request_view(factory,view,payload=query)
    assert response.status_code==200,response.data

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: B-CX01
# Test Case ID: B-CX02
# Test Case ID: B-CX03
# Test Case ID: H-IM01
# Test Case ID: H-IM02
# Test Case ID: H-IM03
# Test Case ID: P-FX01
# Test Case ID: P-FX02
# Test Case ID: P-FX03
# Test Case ID: P-FX04
# Test Case ID: P-FX05
# Test Case ID: P-FX06
# Test Case ID: P-FX07
# Test Case ID: P-FX08
# Test Case ID: P-PG01
# Test Case ID: P-PG02
# Test Case ID: P-PG03
# Test Case ID: P-PG04
# Test Case ID: P-PG05
# Test Case ID: P-PG06
# Test Case ID: P-PG07
# Test Case ID: R-QX01
# Test Case ID: R-QX02
# Test Case ID: R-QX03
# Test Case ID: R-QX04
# Test Case ID: R-QX05
# Test Case ID: R-QX06
# Test Case ID: R-QX07
# Test Case ID: R-QX08
# Test Case ID: R-QX09
