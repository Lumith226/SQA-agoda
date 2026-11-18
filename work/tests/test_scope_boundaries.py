"""Final independent semantic and branch boundaries across the selected scope."""
from datetime import timedelta
from unittest.mock import patch
import pytest
from promotions import views as pv
from promotions.models import Promotion,RoomPromotion
from hotels import views as hv
from bookings.models import RefundPolicy
from bookings.views import BookingViewSet
from test_views import request_view
from test_lifecycle import mark

LISTS=['PromotionListCreateView','PromotionListAdminView','RoomPromotionListAdminView','CarPromotionListAdminView','FlightPromotionListAdminView','ActivityPromotionListAdminView']
@pytest.mark.parametrize('cid,name,sort',[
 pytest.param(f'PR-SORT{i:02}',name,sort,id=f'PR-SORT{i:02}',marks=mark(f'PR-SORT{i:02}','Promotions','Handle ascending and malformed sort expressions',f'{name}; sort={sort}','200; JSON list response','promotions/views.py:'+name,'Sort input boundary')) for i,(name,sort) in enumerate([(n,s) for n in LISTS for s in ['id-asc','invalid']],1)])
def test_campaign_sort_boundaries(cid,name,sort,data,factory):
    response=request_view(factory,getattr(pv,name),payload={'sort':sort})
    assert response.status_code==200,response.data
    assert isinstance(response.data['data'],list)

@pytest.mark.parametrize('cid,city,user',[
 pytest.param(f'H-CITY{i:02}',city,user,id=f'H-CITY{i:02}',marks=mark(f'H-CITY{i:02}','Hotels','Handle absent or invalid city and anonymous recommendations',f'city={city}; authenticated={user}','200; empty for missing/invalid city','hotels/views.py:HotelByCityView','Argument boundary')) for i,(city,user) in enumerate([(None,False),('bad',False),('valid',False)],1)])
def test_hotel_city_boundary(cid,city,user,data,factory):
    kwargs={} if city is None else {'city_id':data.city.pk if city=='valid' else city}
    response=request_view(factory,hv.HotelByCityView,payload={'recommended':'true'} if city=='valid' else {},**kwargs)
    assert response.status_code==200,response.data
    if city!='valid':assert response.data['data']==[]

@pytest.mark.parametrize('cid',[pytest.param('PR-PARTIAL01',id='PR-PARTIAL01',marks=mark('PR-PARTIAL01','Promotions','Report per-item errors when valid and unknown rooms are mixed','One real room and one unknown room','201; one link persisted; errors returned for unknown room','promotions/views.py:PromotionCreateView','Mixed batch decision'))])
def test_campaign_partial_success(cid,data,factory):
    payload={'type':'hotel','title':'Mixed Sale','start_date':data.now.isoformat(),'end_date':(data.now+timedelta(days=2)).isoformat(),'discount_percent':10,'discount_amount':20,'rooms':[{'id':data.room.pk},{'id':999999}]}
    response=request_view(factory,pv.PromotionCreateView,'post',payload)
    assert response.status_code==201,response.data
    result=response.data['data'];assert len(result['rooms'])==1;assert len(result['errors'])==1
    assert RoomPromotion.objects.filter(promotion_id=result['promotion_id']).count()==1

@pytest.mark.parametrize('cid',[pytest.param('B-NULLTIME01',id='B-NULLTIME01',marks=mark('B-NULLTIME01','Bookings','Fallback to final price when start time is absent','Policy exists; unsaved booking created_at=None','Full final price returned','bookings/views.py:calculate_refund_amount','Helper boundary'))])
def test_refund_missing_time(cid,data):
    RefundPolicy.objects.create(name='Standard',service_type=1,policy_type=2,refund_percentage=25)
    data.booking.created_at=None
    assert BookingViewSet().calculate_refund_amount(data.booking)==100

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: B-NULLTIME01
# Test Case ID: H-CITY01
# Test Case ID: H-CITY02
# Test Case ID: H-CITY03
# Test Case ID: PR-PARTIAL01
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
