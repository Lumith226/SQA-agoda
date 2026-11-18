"""Booking orchestration over the service graphs used by the selected modules."""
from datetime import timedelta
import pytest
from bookings.models import Booking,GuestInfo
from bookings.views import BookingViewSet
from bookings.constants.booking_status import BookingStatus
from payments.constants.payment_status import PaymentStatus
from test_views import request_view
from test_lifecycle import mark,attach_detail

@pytest.mark.parametrize('cid,kind,many',[
 pytest.param(f'B-N{i:02}',kind,many,id=f'B-N{i:02}',marks=mark(f'B-N{i:02}','Bookings','Create booking with service detail and synchronized references',f'service={kind}; list payload={many}','201; exactly one booking and linked detail; service_ref_ids matches actual detail','bookings/views.py:BookingViewSet.create')) for i,(kind,many) in enumerate([(k,m) for k in [1,2,3,4] for m in [False,True]],1)])
def test_create_service_booking(cid,kind,many,data,services,factory):
    """Test Case IDs B-N01...B-N08: single/list serializer orchestration."""
    details={1:('room_details',{'room':data.room.pk,'check_in':(data.now+timedelta(days=3)).isoformat(),'check_out':(data.now+timedelta(days=4)).isoformat(),'num_guests':2,'room_count':1}),2:('car_detail',{'car':services.car.pk,'pickup_datetime':(data.now+timedelta(days=3)).isoformat(),'distance_km':10,'passenger_quantity_booking':1}),3:('flight_detail',{'flight':services.flight.pk,'seat_class':'economy','num_passengers':1}),4:('activity_date_detail',{'activity_date':services.ad.pk,'date_launch':services.ad.date_launch.isoformat(),'adult_quantity_booking':1,'child_quantity_booking':1,'price_adult':50,'price_child':25})}
    key,value=details[kind]
    before=Booking.objects.count()
    response=request_view(factory,BookingViewSet,'post',{'service_type':kind,key:[value] if many else value},data.user)
    assert response.status_code==201,response.data
    assert Booking.objects.count()==before+1
    b=Booking.objects.latest('pk');assert b.user==data.user;assert len(b.service_ref_ids)==1
    related={1:lambda:b.hotel_detail,2:lambda:b.car_detail,3:lambda:b.flight_details.get(),4:lambda:b.activity_date_detail}[kind]()
    assert related.pk==b.service_ref_ids[0]

@pytest.mark.parametrize('cid,kind,scenario',[
 pytest.param(f'B-X{i:02}',kind,s,id=f'B-X{i:02}',marks=mark(f'B-X{i:02}','Bookings','Reject invalid service without inserting orphan booking',f'service={kind}; {s}','HTTP 400; booking count unchanged','bookings/views.py:BookingViewSet.create')) for i,(kind,s) in enumerate([(2,'missing_id'),(2,'unknown_id'),(2,'missing_driver'),(2,'busy_driver'),(4,'missing_id'),(4,'unknown_id'),(4,'no_capacity')],1)])
def test_invalid_service_booking_atomicity(cid,kind,scenario,data,services,factory):
    key='car_detail' if kind==2 else 'activity_date_detail'
    value={'car':services.car.pk,'pickup_datetime':(data.now+timedelta(days=3)).isoformat()} if kind==2 else {'activity_date':services.ad.pk,'adult_quantity_booking':1,'child_quantity_booking':1}
    if scenario=='missing_id':value.pop('car' if kind==2 else 'activity_date')
    if scenario=='unknown_id':value['car' if kind==2 else 'activity_date']=999999
    if scenario=='missing_driver':services.car.user=None;services.car.save()
    if scenario=='busy_driver':data.user.driver_status='busy';data.user.save()
    if scenario=='no_capacity':services.ad.participants_available=0;services.ad.save()
    before=Booking.objects.count()
    response=request_view(factory,BookingViewSet,'post',{'service_type':kind,key:value})
    assert response.status_code==400,response.data
    assert Booking.objects.count()==before,'Rejected service request left an orphan booking'

@pytest.mark.parametrize('cid,kind',[
 pytest.param(f'B-RE{i:02}',kind,id=f'B-RE{i:02}',marks=mark(f'B-RE{i:02}','Bookings','Rebook cancelled booking and clone service and guest data',f'service={kind}; old booking=CANCELLED','New booking and detail created; old booking/payment marked REBOOKED','bookings/views.py:rebook_booking')) for i,kind in enumerate([1,2,3,4],1)])
def test_rebook_service(cid,kind,data,services,factory):
    attach_detail(data,services,kind)
    b=data.booking;b.status=BookingStatus.CANCELLED;b.save()
    if kind==2:data.user.driver_status='idle';data.user.save()
    response=request_view(factory,BookingViewSet,'post',action='rebook_booking',pk=b.pk)
    assert response.status_code==201,response.data
    new=Booking.objects.get(pk=response.data['new_booking_id']);b.refresh_from_db();data.payment.refresh_from_db()
    assert new.pk!=b.pk and new.service_type==kind and new.status==BookingStatus.PENDING
    assert new.guest_info.full_name=='Alice'
    assert b.status==BookingStatus.REBOOKED and int(data.payment.status)==PaymentStatus.REBOOKED

@pytest.mark.parametrize('cid',[pytest.param('B-RE05',id='B-RE05',marks=mark('B-RE05','Bookings','Reject rebooking a pending booking','status=PENDING','400; no new booking','bookings/views.py:rebook_booking'))])
def test_rebook_pending_rejected(cid,data,factory):
    count=Booking.objects.count();response=request_view(factory,BookingViewSet,'post',action='rebook_booking',pk=data.booking.pk)
    assert response.status_code==400;assert Booking.objects.count()==count

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: B-N01
# Test Case ID: B-N02
# Test Case ID: B-N03
# Test Case ID: B-N04
# Test Case ID: B-N05
# Test Case ID: B-N06
# Test Case ID: B-N07
# Test Case ID: B-N08
# Test Case ID: B-RE01
# Test Case ID: B-RE02
# Test Case ID: B-RE03
# Test Case ID: B-RE04
# Test Case ID: B-RE05
# Test Case ID: B-X01
# Test Case ID: B-X02
# Test Case ID: B-X03
# Test Case ID: B-X04
# Test Case ID: B-X05
# Test Case ID: B-X06
# Test Case ID: B-X07
