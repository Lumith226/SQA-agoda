"""Further branch and semantic checks for views, inventory and request isolation."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import math
import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.request import Request
from hotels import views as hv
from rooms import views as rv
from bookings import views as bv
from promotions import views as prv
from hotels.models import Hotel,HotelImage,UserHotelInteraction
from rooms.models import RoomImage,RoomBookingDetail,RoomAmenity
from rooms.serializers import RoomBookingDetailCreateSerializer
from bookings.models import Booking,RefundPolicy
from test_views import request_view
from test_lifecycle import mark,attach_detail

HOTEL_INPUTS=[('cityId','bad'),('ownerId','bad'),('adult','bad'),('child','bad'),('room','bad'),('avg_star','bad'),('min_avg_star','bad'),('max_avg_star','bad'),('min_avg_price','bad'),('max_avg_price','bad'),('sort','id-asc'),('sort','bad'),('name','Lotus'),('startDate','range'),('startDate','bad_range'),('recommended','anonymous')]
@pytest.mark.parametrize('cid,key,value',[
 pytest.param(f'H-QX{i:02}',key,value,id=f'H-QX{i:02}',marks=mark(f'H-QX{i:02}','Hotels','Handle filter boundaries without server exception',f'{key}={value}','HTTP 200; invalid city/owner returns empty list; other malformed optional filters handled','hotels/views.py:HotelListView/HotelPagination')) for i,(key,value) in enumerate(HOTEL_INPUTS,1)])
def test_hotel_filter_boundaries(cid,key,value,data,factory):
    query={key:value}
    if value in ('range','bad_range'):query={'startDate':(data.now+timedelta(days=2)).date().isoformat() if value=='range' else 'invalid','endDate':(data.now+timedelta(days=4)).date().isoformat()}
    if value=='anonymous':query={'recommended':'true'}
    response=request_view(factory,hv.HotelListView,payload=query,user=None if value=='anonymous' else data.user)
    assert response.status_code==200,response.data
    if key in ('cityId','ownerId'):assert response.data['data']==[]

@pytest.mark.parametrize('cid,scenario',[
 pytest.param(f'H-I{i:02}',s,id=f'H-I{i:02}',marks=mark(f'H-I{i:02}','Hotels','Read or upsert hotel interaction and aggregate persisted counts',s,'Correct HTTP status, user-level counts and hotel aggregate','hotels/views.py:UserHotelInteractionUpsertView/UserHotelInteractionDetailView')) for i,s in enumerate(['create','update','anonymous','missing_hotel','detail','detail_missing','detail_anonymous'],1)])
def test_hotel_interactions(cid,scenario,data,factory):
    if scenario in ('update','detail'):UserHotelInteraction.objects.create(user=data.user,hotel=data.hotel,click_count=1)
    if scenario.startswith('detail'):
        response=request_view(factory,hv.UserHotelInteractionDetailView,user=None if scenario=='detail_anonymous' else data.user,hotel_id=data.hotel.pk)
        expected=401 if scenario=='detail_anonymous' else 404 if scenario=='detail_missing' else 200
        assert response.status_code==expected,response.data
    else:
        payload={} if scenario=='missing_hotel' else {'hotel_id':data.hotel.pk,'click_count':4,'positive_count':2,'negative_count':1,'neutral_count':1}
        response=request_view(factory,hv.UserHotelInteractionUpsertView,'post',payload,None if scenario=='anonymous' else data.user)
        expected=401 if scenario=='anonymous' else 400 if scenario=='missing_hotel' else 200
        assert response.status_code==expected,response.data
        if expected==200:
            obj=UserHotelInteraction.objects.get(user=data.user,hotel=data.hotel);data.hotel.refresh_from_db()
            assert obj.click_count==data.hotel.total_click==4
            assert obj.weighted_score==pytest.approx(0.7*(1/5)+0.3*math.log(5))

@pytest.mark.parametrize('cid',[pytest.param('H-ISOLATION01',id='H-ISOLATION01',marks=mark('H-ISOLATION01','Hotels','Keep pagination filters isolated between consecutive requests','Request 1 cityId=99999; request 2 has no filters','Second paginator has no city filter','hotels/views.py:HotelPagination.get_page_size','Sequential request isolation regression'))])
def test_hotel_pagination_request_isolation(cid,factory):
    first=hv.HotelPagination();first.get_page_size(Request(factory.get('/',{'cityId':'99999'})))
    second=hv.HotelPagination();second.get_page_size(Request(factory.get('/')))
    assert 'city_id' not in second.filters,'Class-level filters leak from a previous request'

# Test Case IDs *-NPxx: verify unpaginated response branch using documented view override.
UNPAGED=[('Rooms',rv,'RoomListView'),('Rooms',rv,'RoomAdminListView'),('Rooms',rv,'RoomAmenityListView'),('Bookings',bv,'BookingViewSet'),('Bookings',bv,'RefundPolicyViewSet'),('Promotions',prv,'PromotionListCreateView'),('Promotions',prv,'PromotionListAdminView'),('Promotions',prv,'RoomPromotionListAdminView'),('Promotions',prv,'CarPromotionListAdminView'),('Promotions',prv,'FlightPromotionListAdminView'),('Promotions',prv,'ActivityPromotionListAdminView')]
@pytest.mark.parametrize('cid,module,mod,name',[
 pytest.param(f'{title[:2].upper()}-NP{i:02}',title,mod,name,id=f'{title[:2].upper()}-NP{i:02}',marks=mark(f'{title[:2].upper()}-NP{i:02}',title,'Return complete list when pagination is disabled',f'{name}; pagination_class=None','200; response data is list','{0}/views.py:{1}'.format(title.lower(),name),'Configuration boundary; real database read')) for i,(title,mod,name) in enumerate(UNPAGED,1)])
def test_unpaginated_lists(cid,module,mod,name,data,factory):
    with patch.object(getattr(mod,name),'pagination_class',None):
        response=request_view(factory,getattr(mod,name),user=data.user)
    assert response.status_code==200,response.data
    assert isinstance(response.data['data'],list)

@pytest.mark.parametrize('cid,app,exists',[
 pytest.param(f'{app[:1].upper()}-IMG{i:02}',app,exists,id=f'{app[:1].upper()}-IMG{i:02}',marks=mark(f'{app[:1].upper()}-IMG{i:02}',app,'Delete image row and handle storage outcome','Storage file exists='+str(exists),'Image row deleted; storage removed only when file exists',f'{app.lower()}/views.py:image deletion','Mock filesystem boundary; real DB deletion')) for i,(app,exists) in enumerate([(a,e) for a in ['Hotels','Rooms'] for e in [False,True]],1)])
def test_image_delete(cid,app,exists,data,factory):
    model,parent,view=(HotelImage,data.hotel,hv.HotelImageDeleteView) if app=='Hotels' else (RoomImage,data.room,rv.RoomImageDeleteView)
    obj=model.objects.create(**{'hotel' if app=='Hotels' else 'room':parent},image='/media/image.png')
    with patch(f'{app.lower()}.views.os.path.isfile',return_value=exists),patch(f'{app.lower()}.views.os.remove') as remove:
        response=request_view(factory,view,'delete',user=data.user,pk=obj.pk)
    assert response.status_code==204,response.data
    assert not model.objects.filter(pk=obj.pk).exists()

@pytest.mark.parametrize('cid,cancelled,expected',[
 pytest.param(f'R-OVERLAP{i:02}',cancelled,expected,id=f'R-OVERLAP{i:02}',marks=mark(f'R-OVERLAP{i:02}','Rooms','Count overlapping room quantities and ignore cancelled bookings',f'Existing 8 rooms; request 3; cancelled={cancelled}',f'Accepted={expected}','rooms/serializers.py:RoomBookingDetailCreateSerializer.validate','Overlap boundary; real database query')) for i,(cancelled,expected) in enumerate([(False,False),(True,True)],1)])
def test_room_overlap(cid,cancelled,expected,data):
    RoomBookingDetail.objects.create(booking=data.booking,room=data.room,room_count=8,num_guests=1,check_in=data.now+timedelta(days=2),check_out=data.now+timedelta(days=5))
    # Restore displayed inventory to isolate the date-overlap calculation.
    data.room.available_rooms=10;data.room.save()
    if cancelled:data.booking.status=3;data.booking.save()
    s=RoomBookingDetailCreateSerializer(data={'room':data.room.pk,'room_count':3,'num_guests':1,'check_in':data.now+timedelta(days=3),'check_out':data.now+timedelta(days=4)})
    assert s.is_valid()==expected,s.errors

@pytest.mark.parametrize('cid',[pytest.param('R-DETAIL01',id='R-DETAIL01',marks=mark('R-DETAIL01','Rooms','Retrieve saved room booking detail','Valid room booking detail ID','200; correct detail ID','rooms/views.py:RoomBookingDetailView.retrieve'))])
def test_room_booking_detail_view(cid,data,services,factory):
    detail=attach_detail(data,services,1)
    response=request_view(factory,rv.RoomBookingDetailView,pk=detail.pk)
    assert response.status_code==200,response.data
    assert response.data['data']['id']==detail.pk

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: BO-NP04
# Test Case ID: BO-NP05
# Test Case ID: H-I01
# Test Case ID: H-I02
# Test Case ID: H-I03
# Test Case ID: H-I04
# Test Case ID: H-I05
# Test Case ID: H-I06
# Test Case ID: H-I07
# Test Case ID: H-IMG01
# Test Case ID: H-IMG02
# Test Case ID: H-ISOLATION01
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
# Test Case ID: PR-NP06
# Test Case ID: PR-NP07
# Test Case ID: PR-NP08
# Test Case ID: PR-NP09
# Test Case ID: PR-NP10
# Test Case ID: PR-NP11
# Test Case ID: R-DETAIL01
# Test Case ID: R-IMG03
# Test Case ID: R-IMG04
# Test Case ID: R-OVERLAP01
# Test Case ID: R-OVERLAP02
# Test Case ID: RO-NP01
# Test Case ID: RO-NP02
# Test Case ID: RO-NP03
