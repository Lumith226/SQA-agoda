"""Business model tests. Test Case IDs are declared beside every parameter set.

Write paths use real model saves, refresh_from_db, and the shared rollback audit.
Floating-point comparisons use independently calculated monetary expectations.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch, PropertyMock
import math
import pytest
from django.utils import timezone
from django.db import IntegrityError, transaction
from hotels.models import Hotel, HotelImage, UserHotelInteraction
from rooms.models import Room, RoomImage, RoomAmenity, RoomBookingDetail
from bookings.models import Booking, GuestInfo, RefundPolicy
from payments.models import Payment
from promotions.models import Promotion, RoomPromotion, CarPromotion, FlightPromotion, ActivityPromotion
from conftest import case

HOTEL_CASES = [
    ('H-M01','Persist hotel name and readable label','Hotel name = Lotus Hotel','Saved name and string equal Lotus Hotel'),
    ('H-M02','Compute neutral sentiment without division by zero','No interactions','Sentiment = 0'),
    ('H-M03','Compute positive and negative sentiment','Positive=5; negative=2; neutral=2','Sentiment = 0.3'),
    ('H-M04','Compute logarithmic click score','Clicks = 9','Score = ln(10)'),
    ('H-M05','Persist weighted recommendation score','Stars=4; clicks=9; positive=5; negative=2; neutral=2','Score = 0.6*4 + 0.3*ln(10) + 0.1*0.3'),
    ('H-M06','Persist explicit weighted score refresh','Stars changed to 3','Stored score equals independent weighted formula'),
    ('H-M07','Return zero price for no available rooms','All rooms unavailable','Stored min_price = 0'),
    ('H-M08','Exclude unavailable rooms from price aggregation','Available price=100; unavailable price=500','Stored price = 100'),
    ('H-M09','Expose the lowest available nightly price','Available room prices = 100 and 300','min_price = 100'),
    ('H-M10','Render hotel image label','Hotel image with parent hotel','Image for Lotus Hotel'),
    ('H-M11','Persist individual interaction score','Clicks=4; positive=3; negative=1; neutral=0','0.7*(2/5) + 0.3*ln(5), persisted'),
    ('H-M12','Render interaction user and hotel label','User tester; hotel Lotus Hotel','Both names appear'),
    ('H-M13','Fallback when recommendation calculation raises','Property raises ValueError','Stored weighted score = 0'),
    ('H-M14','Enforce one interaction per user and hotel','Insert duplicate user/hotel pair','IntegrityError and original row preserved'),
]
@pytest.mark.parametrize('cid',[case(i,'Hotels',o,x,e,'hotels/models.py') for i,o,x,e in HOTEL_CASES])
def test_hotel_models(cid, data):
    """Test Case IDs H-M01 through H-M14: hotel persistence and scoring."""
    h = data.hotel
    if cid == 'H-M01':
        h.refresh_from_db(); assert h.name == str(h) == 'Lotus Hotel'
    elif cid == 'H-M02': assert h.sentiment_score == 0
    elif cid == 'H-M03':
        h.total_positive,h.total_negative,h.total_neutral=5,2,2
        assert h.sentiment_score == pytest.approx(0.3)
    elif cid == 'H-M04':
        h.total_click=9; assert h.click_score == pytest.approx(math.log(10))
    elif cid in ('H-M05','H-M06'):
        h.avg_star=4 if cid=='H-M05' else 3
        h.total_click=9; h.total_positive,h.total_negative,h.total_neutral=5,2,2
        expected=0.6*h.avg_star+0.3*math.log(10)+0.1*0.3
        h.save() if cid=='H-M05' else h.update_total_weighted_score()
        h.refresh_from_db(); assert h.total_weighted_score == pytest.approx(expected)
    elif cid=='H-M07':
        data.room.available_rooms=0; data.room.save(); h.refresh_from_db(); assert h.min_price == 0
    elif cid=='H-M08':
        Room.objects.create(hotel=h,room_type='Closed',price_per_night=500,available_rooms=0)
        h.refresh_from_db(); assert h.min_price==100
    elif cid=='H-M09':
        Room.objects.create(hotel=h,room_type='Suite',price_per_night=300)
        h.refresh_from_db(); assert h.min_price==100, f'Expected lowest price 100, observed {h.min_price}'
    elif cid=='H-M10': assert str(HotelImage.objects.create(hotel=h,image='hotel.png'))=='Image for Lotus Hotel'
    elif cid=='H-M11':
        obj=UserHotelInteraction.objects.create(user=data.user,hotel=h,click_count=4,positive_count=3,negative_count=1)
        obj.update_weighted_score(); obj.refresh_from_db()
        assert obj.weighted_score==pytest.approx(0.7*2/5+0.3*math.log(5))
    elif cid=='H-M12': assert all(s in str(UserHotelInteraction(user=data.user,hotel=h)) for s in ('tester','Lotus Hotel'))
    elif cid=='H-M13':
        with patch.object(Hotel,'calc_total_weighted_score',new_callable=PropertyMock,side_effect=ValueError('invalid score')): h.save()
        h.refresh_from_db(); assert h.total_weighted_score==0
    elif cid=='H-M14':
        UserHotelInteraction.objects.create(user=data.user,hotel=h)
        with pytest.raises(IntegrityError),transaction.atomic(): UserHotelInteraction.objects.create(user=data.user,hotel=h)
        assert UserHotelInteraction.objects.filter(user=data.user,hotel=h).count()==1

ROOM_CASES=[
 ('R-M01','Sum adult and child capacity','Adults=2; children=1','Capacity=3'),
 ('R-M02','Disable room when inventory is zero','Available rooms=0','available=False persisted'),
 ('R-M03','Disable expired room','End date=yesterday','available=False persisted'),
 ('R-M04','Keep room available on end date','End date=today; inventory=10','available=True persisted'),
 ('R-M05','Decrease inventory without negative balance','Inventory=10; decrease=20','Inventory=0 persisted'),
 ('R-M06','Decrease inventory by default quantity','Inventory=10; no argument','Inventory=9 persisted'),
 ('R-M07','Refresh hotel price after deleting last room','Delete sole room','No room remains; hotel price=0'),
 ('R-M08','Persist standalone room without hotel','hotel=None','Room saved and deleted successfully'),
 ('R-M09','Render room and amenity labels','Deluxe room in Lotus Hotel','Labels contain parent names'),
 ('R-M10','Return no promotion when none is linked','No room promotions','None'),
 ('R-M11','Ignore inactive promotion','is_active=False','None'),
 ('R-M12','Ignore future promotion','Start date=tomorrow','None'),
 ('R-M13','Ignore expired promotion','End date=yesterday','None'),
 ('R-M14','Use campaign discount when room override is zero','Campaign 10%; room override 0','Effective 10%'),
 ('R-M15','Use room-specific discount','Campaign 10%; room override 20','Effective 20%'),
 ('R-M16','Choose greatest effective percent discount','Campaign 40% with room 0; campaign 10% with room 20','Effective best discount=40%'),
]
@pytest.mark.parametrize('cid',[case(i,'Rooms',o,x,e,'rooms/models.py:Room') for i,o,x,e in ROOM_CASES])
def test_room_models(cid,data):
    """Test Case IDs R-M01 through R-M16: inventory boundaries and promotions."""
    r=data.room
    if cid=='R-M01': assert r.capacity==3
    elif cid in ('R-M02','R-M03','R-M04'):
        if cid=='R-M02': r.available_rooms=0
        else: r.end_date=(data.now+timedelta(days=-1 if cid=='R-M03' else 0)).date()
        r.save(); r.refresh_from_db(); assert r.available==(cid=='R-M04')
    elif cid in ('R-M05','R-M06'):
        r.decrease_available_rooms(20) if cid=='R-M05' else r.decrease_available_rooms()
        r.refresh_from_db(); assert r.available_rooms==(0 if cid=='R-M05' else 9)
    elif cid=='R-M07':
        pk=r.pk; r.delete(); data.hotel.refresh_from_db(); assert not Room.objects.filter(pk=pk).exists(); assert data.hotel.min_price==0
    elif cid=='R-M08':
        obj=Room.objects.create(room_type='Standalone',hotel=None); pk=obj.pk; obj.delete(); assert not Room.objects.filter(pk=pk).exists()
    elif cid=='R-M09':
        assert str(r)=='Lotus Hotel - Deluxe'
        assert str(RoomImage(room=r))=='Image for Deluxe in Lotus Hotel'
        assert str(RoomAmenity(room=r,name='WiFi'))=='WiFi (Deluxe)'
    elif cid=='R-M10': assert r.get_active_promotion() is None
    else:
        p=data.promotion
        if cid=='R-M11': p.is_active=False
        if cid=='R-M12': p.start_date=data.now+timedelta(days=1)
        if cid=='R-M13': p.start_date=data.now-timedelta(days=2);p.end_date=data.now-timedelta(days=1)
        p.save(); RoomPromotion.objects.create(room=r,promotion=p,discount_percent=20 if cid=='R-M15' else 0)
        if cid=='R-M16':
            p.discount_percent=40;p.save()
            p2=Promotion.objects.create(title='Second',discount_percent=10,start_date=p.start_date,end_date=p.end_date)
            RoomPromotion.objects.create(room=r,promotion=p2,discount_percent=20)
        actual=r.get_active_promotion()
        if cid in ('R-M11','R-M12','R-M13'): assert actual is None
        else:
            expected={'R-M14':10,'R-M15':20,'R-M16':40}[cid]
            assert actual['discount_percent']==expected, f'Expected effective discount {expected}, observed {actual}'

# Test Case IDs R-P01...R-P09: independent room price and stock oracles.
PRICE_CASES=[('R-P01','overnight',2,2,0,0,400,0),('R-P02','dayuse',0,2,0,0,120,0),('R-P03','overnight',0,1,0,0,100,0),('R-P04','overnight',2,1,10,0,200,20),('R-P05','overnight',2,1,10,15,200,15),('R-P06','overnight',2,1,0,300,200,200),('R-P07','overnight',2,1,0,20,200,20),('R-P08','overnight',2,1,0,0,200,0),('R-P09','overnight',2,1,150,0,200,200)]
@pytest.mark.parametrize('cid,stay,nights,count,percent,amount,total,discount',[
 pytest.param(*v,id=v[0],marks=pytest.mark.case(module='Rooms',objective='Calculate room total, discount, final price, parent booking and stock',inputs=f'stay={v[1]}, nights={v[2]}, rooms={v[3]}, percent={v[4]}, cap={v[5]}',expected=f'total={v[6]}, discount={v[7]}, final={v[6]-v[7]}; stock decremented once',target='rooms/models.py:RoomBookingDetail.save',technique='Boundary values; decision table; real DB side effects')) for v in PRICE_CASES])
def test_room_price_and_booking_sync(cid,stay,nights,count,percent,amount,total,discount,data):
    r=data.room;r.stay_type=stay;r.save()
    # R-P08 explicitly exercises an active campaign with zero discount.
    if percent or amount or cid=='R-P08':
        p=data.promotion;p.discount_percent=percent;p.discount_amount=amount;p.save()
        RoomPromotion.objects.create(room=r,promotion=p,discount_percent=percent,discount_amount=amount)
    detail=RoomBookingDetail.objects.create(booking=data.booking,room=r,check_in=data.now+timedelta(days=2),check_out=data.now+timedelta(days=2+nights),num_guests=2,room_count=count)
    detail.refresh_from_db();data.booking.refresh_from_db();r.refresh_from_db()
    assert detail.total_price==total
    assert detail.discount_amount==discount, f'Expected capped discount {discount}, observed {detail.discount_amount}'
    assert detail.final_price==total-discount
    assert data.booking.final_price==total-discount and data.booking.total_price==total
    assert detail.owner_hotel==data.user and detail.room_type=='Deluxe'
    assert r.available_rooms==10-count
    detail.save();r.refresh_from_db();assert r.available_rooms==10-count
    assert data.booking.booking_code in str(detail)

BOOKING_CASES=[('B-M01','Generate booking code','Blank booking code','AGD followed by 6 uppercase hexadecimal digits'),('B-M02','Preserve explicit booking code','booking_code=CUSTOM','Code remains CUSTOM after two saves'),('B-M03','Render booking and guest labels','Booking with guest','Booking code and guest name appear'),('B-M04','Cascade delete guest and payments','Booking with guest and payment','Related guest and payment rows deleted'),('B-M05','Keep booking after user deletion','Booking references user','Booking user becomes NULL'),('B-M06','Render refund policy type','Hotel policy','Policy name and Hotel appear'),('B-M07','Enforce unique booking code','Two identical codes','Duplicate rejected; existing row retained')]
@pytest.mark.parametrize('cid',[case(i,'Bookings',o,x,e,'bookings/models.py') for i,o,x,e in BOOKING_CASES])
def test_booking_models(cid,data):
    """Test Case IDs B-M01 through B-M07: identifiers and referential integrity."""
    import re
    b=data.booking
    if cid=='B-M01': assert re.fullmatch(r'AGD[0-9A-F]{6}',b.booking_code)
    elif cid=='B-M02':
        b.booking_code='CUSTOM';b.save();b.save();b.refresh_from_db();assert b.booking_code=='CUSTOM'
    elif cid=='B-M03':
        g=GuestInfo.objects.create(booking=b,full_name='Alice',email='alice@example.com',phone='123')
        assert str(g)=='Alice';assert b.booking_code in str(b)
    elif cid=='B-M04':
        GuestInfo.objects.create(booking=b,full_name='Alice',email='alice@example.com',phone='123')
        pk=b.pk;b.delete();assert not GuestInfo.objects.filter(booking_id=pk).exists();assert not Payment.objects.filter(booking_id=pk).exists()
    elif cid=='B-M05':
        data.user.delete();b.refresh_from_db();assert b.user_id is None
    elif cid=='B-M06': assert str(RefundPolicy(name='Standard',service_type=1))=='Standard - Hotel'
    elif cid=='B-M07':
        with pytest.raises(IntegrityError),transaction.atomic(): Booking.objects.create(service_type=1,booking_code=b.booking_code)
        assert Booking.objects.filter(booking_code=b.booking_code).count()==1

@pytest.mark.parametrize('cid',[case('P-M01','Payments','Persist payment amount and booking foreign key','Amount=125.5; method=1','Reloaded amount 125.5 and matching booking','payments/models.py:Payment')])
def test_payment_model(cid,data):
    """Test Case ID P-M01: real database payment persistence."""
    p=data.payment;p.amount=125.5;p.save();p.refresh_from_db();assert p.amount==125.5;assert p.booking_id==data.booking.pk

@pytest.mark.parametrize('cid',[case('PR-M01','Promotions','Render all promotion model labels','Hotel, flight, activity, room and car links','Correct parent title and service labels','promotions/models.py')])
def test_promotion_model_labels(cid,data):
    """Test Case ID PR-M01: labels and nullable link branches."""
    p=data.promotion
    assert str(p).startswith('Summer (')
    assert str(RoomPromotion(promotion=p,room=data.room))=='Summer -> Room: Deluxe'
    assert str(FlightPromotion(promotion=p,flight=None))=='Summer -> Flight: N/A'
    assert str(CarPromotion(promotion=p,car=None))=='Summer -> Car: N/A'
    from cars.models import Car
    from flights.models import Flight
    car=Car(id=7,name='Sedan');flight=Flight(id=8)
    assert str(CarPromotion(promotion=p,car=car))=='Summer -> Car: Sedan'
    assert str(FlightPromotion(promotion=p,flight=flight))=='Summer -> Flight: 8'
    from activities.models import ActivityDate
    assert str(ActivityPromotion(promotion=p,activity_date=ActivityDate(id=9)))=='Summer -> ActivityDate: 9'

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: B-M01
# Test Case ID: B-M02
# Test Case ID: B-M03
# Test Case ID: B-M04
# Test Case ID: B-M05
# Test Case ID: B-M06
# Test Case ID: B-M07
# Test Case ID: H-M01
# Test Case ID: H-M02
# Test Case ID: H-M03
# Test Case ID: H-M04
# Test Case ID: H-M05
# Test Case ID: H-M06
# Test Case ID: H-M07
# Test Case ID: H-M08
# Test Case ID: H-M09
# Test Case ID: H-M10
# Test Case ID: H-M11
# Test Case ID: H-M12
# Test Case ID: H-M13
# Test Case ID: H-M14
# Test Case ID: P-M01
# Test Case ID: PR-M01
# Test Case ID: R-M01
# Test Case ID: R-M02
# Test Case ID: R-M03
# Test Case ID: R-M04
# Test Case ID: R-M05
# Test Case ID: R-M06
# Test Case ID: R-M07
# Test Case ID: R-M08
# Test Case ID: R-M09
# Test Case ID: R-M10
# Test Case ID: R-M11
# Test Case ID: R-M12
# Test Case ID: R-M13
# Test Case ID: R-M14
# Test Case ID: R-M15
# Test Case ID: R-M16
# Test Case ID: R-P01
# Test Case ID: R-P02
# Test Case ID: R-P03
# Test Case ID: R-P04
# Test Case ID: R-P05
# Test Case ID: R-P06
# Test Case ID: R-P07
# Test Case ID: R-P08
# Test Case ID: R-P09
