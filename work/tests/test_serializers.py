"""Serializer validation, representation and real database create/update tests."""
from datetime import timedelta
from types import SimpleNamespace
import pytest
from django.contrib.auth.models import AnonymousUser
from hotels.models import HotelImage
from hotels.serializers import HotelSimpleSerializer, HotelSerializer, HotelCreateSerializer
from rooms.models import Room, RoomAmenity, RoomBookingDetail
from rooms.serializers import RoomCreateSerializer, RoomSerializer, RoomBookingDetailCreateSerializer
from bookings.models import Booking, GuestInfo, RefundPolicy
from bookings.serializers import BookingSerializer, GuestInfoSerializer, RefundPolicySerializer
from payments.serializers import PaymentSerializer, PaymentCreateSerializer
from promotions.models import RoomPromotion
from promotions.serializers import PromotionCreateSerializer, PromotionSerializer, RoomPromotionSerializer, CarPromotionSerializer, FlightPromotionSerializer, ActivityPromotionSerializer
from conftest import case

@pytest.mark.parametrize('cid',[case(f'H-S{i:02}','Hotels',o,x,e,'hotels/serializers.py') for i,o,x,e in [
 (1,'Return null thumbnail without images','No images','thumbnail=None'),(2,'Return first hotel image','Image=first.png','thumbnail=first.png'),(3,'Serialize hotel with no owner','owner=None','owner=None'),(4,'Serialize hotel owner','Owner tester','Nested owner username=tester'),(5,'Create hotel using valid city','Valid city and name','Row created with correct city and name')]])
def test_hotel_serializers(cid,data):
    """Test Case IDs H-S01...H-S05."""
    if cid=='H-S01': assert HotelSimpleSerializer(data.hotel).data['thumbnail'] is None
    elif cid=='H-S02':
        HotelImage.objects.create(hotel=data.hotel,image='first.png');assert HotelSimpleSerializer(data.hotel).data['thumbnail']=='first.png'
    elif cid=='H-S03':
        data.hotel.owner=None;assert HotelSerializer(data.hotel).data['owner'] is None
    elif cid=='H-S04': assert HotelSerializer(data.hotel).data['owner']['username']=='tester'
    elif cid=='H-S05':
        s=HotelCreateSerializer(data={'city':data.city.pk,'name':'New Hotel'});assert s.is_valid(),s.errors
        obj=s.save();obj.refresh_from_db();assert obj.name=='New Hotel' and obj.city==data.city

@pytest.mark.parametrize('cid',[case(f'R-S{i:02}','Rooms',o,x,e,'rooms/serializers.py:RoomCreateSerializer') for i,o,x,e in [
 (1,'Create room with default availability dates','Dates omitted; amenities WiFi and Pool','Today to today+365; both amenities persisted'),
 (2,'Preserve explicit room dates','Tomorrow to tomorrow+7','Supplied dates persisted'),
 (3,'Return no promotion fields','Room without campaign','promotion=None; has_promotion=False'),
 (4,'Return active room promotion','Linked 10% campaign','promotion percent=10; has_promotion=True')]])
def test_room_creation_serializers(cid,data):
    """Test Case IDs R-S01...R-S04: dates and nested amenities."""
    if cid in ('R-S01','R-S02'):
        payload={'hotel':data.hotel.pk,'room_type':'Twin','amenities_data':[{'name':'WiFi'},{'name':'Pool'}]}
        if cid=='R-S02': payload.update(start_date=(data.now+timedelta(days=1)).date().isoformat(),end_date=(data.now+timedelta(days=8)).date().isoformat())
        s=RoomCreateSerializer(data=payload);assert s.is_valid(),s.errors
        room=s.save();room.refresh_from_db()
        offset=0 if cid=='R-S01' else 1
        assert room.start_date==(data.now+timedelta(days=offset)).date()
        assert room.end_date==(data.now+timedelta(days=365 if cid=='R-S01' else 8)).date()
        assert set(room.amenities.values_list('name',flat=True))=={'WiFi','Pool'}
        assert s.get_has_promotion(room) is False;assert s.get_promotion(room) is None
    else:
        if cid=='R-S04': RoomPromotion.objects.create(room=data.room,promotion=data.promotion)
        out=RoomSerializer(data.room).data
        assert out['has_promotion']==(cid=='R-S04')
        if cid=='R-S03':assert out['promotion'] is None
        else:assert out['promotion']['discount_percent']==10

ROOM_VALIDATION=[('R-V01','Valid future interval',2,4,2,1,True),('R-V02','Equal check-in and check-out',2,2,2,1,False),('R-V03','Reversed interval',4,2,2,1,False),('R-V04','Past check-in',-1,2,2,1,False),('R-V05','Capacity exceeded',2,4,4,1,False),('R-V06','Inventory exceeded',2,4,2,11,False),('R-V07','Zero guests rejected',2,4,0,1,False),('R-V08','Negative guests rejected',2,4,-1,1,False),('R-V09','Zero rooms rejected',2,4,2,0,False)]
@pytest.mark.parametrize('cid,start,end,guests,count,valid',[
 pytest.param(cid,start,end,guests,count,valid,id=cid,marks=pytest.mark.case(module='Rooms',objective=obj,inputs=f'check-in=now+{start}d; check-out=now+{end}d; guests={guests}; rooms={count}',expected=f'Validation accepted={valid}; invalid input writes no rows',target='rooms/serializers.py:RoomBookingDetailCreateSerializer.validate',technique='Boundary values; negative inputs; database non-mutation')) for cid,obj,start,end,guests,count,valid in ROOM_VALIDATION])
def test_room_booking_validation(cid,start,end,guests,count,valid,data):
    """Test Case IDs R-V01...R-V09: date, quantity and capacity partitions."""
    before=RoomBookingDetail.objects.count()
    s=RoomBookingDetailCreateSerializer(data={'room':data.room.pk,'check_in':data.now+timedelta(days=start),'check_out':data.now+timedelta(days=end),'num_guests':guests,'room_count':count})
    assert s.is_valid()==valid, f'Expected accepted={valid}; observed errors={s.errors}'
    assert RoomBookingDetail.objects.count()==before

BOOKING_SERIALIZERS=[('B-S01','Create anonymous guest booking','Anonymous user and guest','User NULL; guest row linked'),('B-S02','Assign authenticated request user','Authenticated tester','Booking user=tester'),('B-S03','Create without request or guest','Only service_type','Booking persisted, no guest row'),('B-S04','Update booking and existing guest','Change total and guest name','Same guest ID; new name and total'),('B-S05','Create missing guest on update','Booking without guest','One guest created and linked'),('B-S06','Update booking without guest data','total_price=250','Price persisted; no guest created')]
@pytest.mark.parametrize('cid',[case(i,'Bookings',o,x,e,'bookings/serializers.py:BookingSerializer') for i,o,x,e in BOOKING_SERIALIZERS])
def test_booking_serializers(cid,data):
    """Test Case IDs B-S01...B-S06: create and update branches with CheckDB."""
    guest={'full_name':'Alice','email':'alice@example.com','phone':'123'}
    if cid in ('B-S01','B-S02','B-S03'):
        context={} if cid=='B-S03' else {'request':SimpleNamespace(user=data.user if cid=='B-S02' else AnonymousUser())}
        payload={'service_type':1}
        if cid=='B-S01':payload['guest_info']=guest
        s=BookingSerializer(data=payload,context=context);assert s.is_valid(),s.errors
        b=s.save();b.refresh_from_db();assert b.user_id==(data.user.pk if cid=='B-S02' else None)
        assert GuestInfo.objects.filter(booking=b).exists()==(cid=='B-S01')
    else:
        if cid=='B-S04':GuestInfo.objects.create(booking=data.booking,**guest)
        payload={'total_price':250}
        if cid!='B-S06':payload['guest_info']={**guest,'full_name':'Updated Alice'}
        s=BookingSerializer(data.booking,data=payload,partial=True);assert s.is_valid(),s.errors
        s.save();data.booking.refresh_from_db();assert data.booking.total_price==250
        if cid!='B-S06':assert GuestInfo.objects.get(booking=data.booking).full_name=='Updated Alice'
        else:assert not GuestInfo.objects.filter(booking=data.booking).exists()

# Test Case IDs B-SR01...B-SR05: service-specific output includes only relevant details.
@pytest.mark.parametrize('cid,service,field',[
 pytest.param(f'B-SR{i:02}',service,field,id=f'B-SR{i:02}',marks=pytest.mark.case(module='Bookings',objective='Select service detail fields and omit unrelated detail fields',inputs=f'service_type={service}; reference IDs empty',expected=f'Relevant detail field {field}; unrelated fields absent',target='bookings/serializers.py:BookingSerializer.to_representation',technique='Decision table')) for i,(service,field) in enumerate([(1,'room_details'),(2,'car_detail'),(3,'flight_detail'),(4,'activity_date_detail'),(5,None)],1)])
def test_booking_representation(cid,service,field,data):
    b=data.booking;b.service_type=service
    out=BookingSerializer(b).data
    all_fields={'room_details','car_detail','flight_detail','activity_date_detail'}
    assert all_fields.intersection(out)==({field} if field else all_fields)
    # Exercise query branches on real empty relations without fabricating ORM results.
    b.service_ref_ids=[999999]
    s=BookingSerializer()
    method={1:s.get_room_details,2:s.get_car_detail,3:s.get_flight_detail,4:s.get_activity_date_detail}.get(service)
    if method:assert method(b)==[]

@pytest.mark.parametrize('cid',[case('P-S01','Payments','Serialize booking and validate payment FK','Existing booking; amount=150','Nested booking ID correct; payment amount persisted','payments/serializers.py')])
def test_payment_serializers(cid,data):
    """Test Case ID P-S01."""
    assert PaymentSerializer(data.payment).data['booking']['id']==data.booking.pk
    s=PaymentCreateSerializer(data={'booking':data.booking.pk,'method':1,'amount':150});assert s.is_valid(),s.errors
    p=s.save();p.refresh_from_db();assert p.amount==150

# Test Case IDs PR-S01...PR-S08 cover all four required item collections.
@pytest.mark.parametrize('cid,kind,key,present',[
 pytest.param(f'PR-S{i:02}',kind,key,present,id=f'PR-S{i:02}',marks=pytest.mark.case(module='Promotions',objective=f'Validate required {key} collection for {kind} campaign',inputs=f'type={kind}; {key} present={present}',expected=f'Accepted={present}',target='promotions/serializers.py:PromotionCreateSerializer.validate',technique='Decision table; required fields')) for i,(kind,key,present) in enumerate([(k,key,p) for k,key in [('hotel','rooms'),('flight','flights'),('activity','actDates'),('car','cars')] for p in [False,True]],1)])
def test_promotion_create_validation(cid,kind,key,present,data):
    payload={'type':kind,'title':'Sale','start_date':data.now,'end_date':data.now+timedelta(days=2)}
    if present:payload[key]=[{'id':1}]
    s=PromotionCreateSerializer(data=payload);assert s.is_valid()==present,s.errors

# Test Case IDs PR-SR01...PR-SR05: every representation branch, including unknown type.
@pytest.mark.parametrize('cid,kind,field',[
 pytest.param(f'PR-SR{i:02}',kind,field,id=f'PR-SR{i:02}',marks=pytest.mark.case(module='Promotions',objective='Retain only campaign links matching service type',inputs=f'promotion_type={kind}',expected=f'Only {field} links retained' if field else 'All link fields retained for unknown type',target='promotions/serializers.py:PromotionSerializer.to_representation',technique='Decision table')) for i,(kind,field) in enumerate([(1,'room_promotions'),(2,'flight_promotions'),(3,'activity_promotions'),(4,'car_promotions'),(99,None)],1)])
def test_promotion_representation(cid,kind,field,data):
    p=data.promotion;p.promotion_type=kind
    out=PromotionSerializer(p).data
    fields={'room_promotions','flight_promotions','activity_promotions','car_promotions'}
    assert fields.intersection(out)==({field} if field else fields)

@pytest.mark.parametrize('cid',[case('PR-D01','Promotions','Apply child override and campaign fallback across all services','Override 0 then 25; campaign percent=10, amount=30','Fallback=10/30 then override=25/25','promotions/serializers.py:effective discount methods')])
def test_effective_discounts(cid,data):
    """Test Case ID PR-D01: pure methods isolated from nested serializers."""
    data.promotion.discount_amount=30
    for cls in [RoomPromotionSerializer,CarPromotionSerializer,FlightPromotionSerializer,ActivityPromotionSerializer]:
        s=cls();obj=SimpleNamespace(promotion=data.promotion,discount_percent=0,discount_amount=0)
        assert s.get_effective_discount_percent(obj)==10;assert s.get_effective_discount_amount(obj)==30
        obj.discount_percent=25;obj.discount_amount=25
        assert s.get_effective_discount_percent(obj)==25;assert s.get_effective_discount_amount(obj)==25

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: B-S01
# Test Case ID: B-S02
# Test Case ID: B-S03
# Test Case ID: B-S04
# Test Case ID: B-S05
# Test Case ID: B-S06
# Test Case ID: B-SR01
# Test Case ID: B-SR02
# Test Case ID: B-SR03
# Test Case ID: B-SR04
# Test Case ID: B-SR05
# Test Case ID: H-S01
# Test Case ID: H-S02
# Test Case ID: H-S03
# Test Case ID: H-S04
# Test Case ID: H-S05
# Test Case ID: P-S01
# Test Case ID: PR-D01
# Test Case ID: PR-S01
# Test Case ID: PR-S02
# Test Case ID: PR-S03
# Test Case ID: PR-S04
# Test Case ID: PR-S05
# Test Case ID: PR-S06
# Test Case ID: PR-S07
# Test Case ID: PR-S08
# Test Case ID: PR-SR01
# Test Case ID: PR-SR02
# Test Case ID: PR-SR03
# Test Case ID: PR-SR04
# Test Case ID: PR-SR05
# Test Case ID: R-S01
# Test Case ID: R-S02
# Test Case ID: R-S03
# Test Case ID: R-S04
# Test Case ID: R-V01
# Test Case ID: R-V02
# Test Case ID: R-V03
# Test Case ID: R-V04
# Test Case ID: R-V05
# Test Case ID: R-V06
# Test Case ID: R-V07
# Test Case ID: R-V08
# Test Case ID: R-V09
