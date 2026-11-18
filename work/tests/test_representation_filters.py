"""Isolated serializer filter contracts using explicit method input doubles.

Parent serialization is mocked because these tests exercise only filtering.
The actual ActivityPromotion model contract is tested separately below; its
missing `activity` attribute must not be hidden by these isolated unit tests.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from rest_framework.serializers import ModelSerializer
from promotions.serializers import ActivityPromotionSerializer,FlightPromotionSerializer
from promotions.models import ActivityPromotion,FlightPromotion
from test_lifecycle import mark

FLIGHT_FILTERS=[('origin_id','mismatch',True),('destination_id','mismatch',True),('airline_id','mismatch',True),('start_date','future',True),('start_date','invalid',False),('origin_id','match',False),('destination_id','match',False),('airline_id','match',False),('start_date','past',False),('legs','missing',True)]
@pytest.mark.parametrize('cid,key,mode,filtered',[
 pytest.param(f'PR-F{i:02}',key,mode,filtered,id=f'PR-F{i:02}',marks=mark(f'PR-F{i:02}','Promotions','Filter serialized flight promotion by route, airline and departure date',f'{key}={mode}',f'Filtered out={filtered}','promotions/serializers.py:FlightPromotionSerializer.to_representation','Decision table; parent serializer mocked; real flight query')) for i,(key,mode,filtered) in enumerate(FLIGHT_FILTERS,1)])
def test_flight_promotion_filters(cid,key,mode,filtered,data,services):
    if key=='legs':services.flight.legs.all().delete()
    obj=FlightPromotion(promotion=data.promotion,flight=services.flight)
    actual={'origin_id':services.a1.pk,'destination_id':services.a2.pk,'airline_id':services.airline.pk}
    if key in actual:context={key:str(actual[key] if mode=='match' else 99999)}
    elif key=='start_date':context={key:'invalid-date' if mode=='invalid' else (data.now+timedelta(days=5 if mode=='future' else 1)).date().isoformat()}
    else:context={}
    with patch.object(ModelSerializer,'to_representation',return_value={'id':9,'discount_percent':10,'discount_amount':20}):
        out=FlightPromotionSerializer(context=context).to_representation(obj)
    assert (out is None)==filtered
    if out is not None:assert out=={'id':9}

ACTIVITY_FILTERS=[('none','all',False),('city_id','mismatch',True),('category','mismatch',True),('min_rating','higher',True),('min_price','higher',True),('min_price','invalid',False),('max_price','lower',True),('max_price','invalid',False),('search','missing',True),('search','name',False),('search','description',False),('start_date','before',False),('start_date','after',True),('end_date','before',True),('end_date','after',False),('start_date','invalid',False),('start_date','missing_date',True),('start_date','second_package',False)]
@pytest.mark.parametrize('cid,key,mode,filtered',[
 pytest.param(f'PR-AF{i:02}',key,mode,filtered,id=f'PR-AF{i:02}',marks=mark(f'PR-AF{i:02}','Promotions','Apply isolated activity-promotion filter contract',f'{key}={mode}; explicit activity interface double',f'Filtered out={filtered}','promotions/serializers.py:ActivityPromotionSerializer.to_representation','Unit input double; parent representation mocked; decision table')) for i,(key,mode,filtered) in enumerate(ACTIVITY_FILTERS,1)])
def test_activity_promotion_filter_contract(cid,key,mode,filtered,data):
    """Test Case IDs PR-AF01...PR-AF18: isolates otherwise broken adapter path."""
    class Rows(list):
        def all(self):return self
        def prefetch_related(self,*args):return self
    dates=Rows([SimpleNamespace(date_launch=None if mode=='missing_date' else data.now+timedelta(days=3))])
    packages=Rows([SimpleNamespace(activitydate_set=dates)])
    if mode=='second_package':packages.insert(0,SimpleNamespace(activitydate_set=Rows([])))
    activity=SimpleNamespace(city_id=1,category='journey',avg_star=4,avg_price=100,name='Museum visit',short_description='Historic collection',activitypackage_set=packages)
    obj=SimpleNamespace(activity=activity)
    values={'city_id':'999','category':'food','min_rating':'5','min_price':'bad' if mode=='invalid' else '200','max_price':'bad' if mode=='invalid' else '50','search':{'missing':'beach','name':'MUSEUM','description':'collection'}.get(mode,'beach')}
    if key in ('start_date','end_date'):
        offset=2 if mode in ('before','second_package') else 4
        context={key:'invalid-date' if mode=='invalid' else (data.now+timedelta(days=offset)).date().isoformat()}
    else:context={} if key=='none' else {key:values[key]}
    with patch.object(ModelSerializer,'to_representation',return_value={'id':9,'some_internal_field':'hidden'}):
        out=ActivityPromotionSerializer(context=context).to_representation(obj)
    assert (out is None)==filtered
    if out is not None:assert 'some_internal_field' not in out

@pytest.mark.parametrize('cid',[pytest.param('PR-ACTUAL01',id='PR-ACTUAL01',marks=mark('PR-ACTUAL01','Promotions','Serialize an actual activity promotion without extra attributes','Persisted ActivityPromotion with valid ActivityDate','Non-null promotion data','promotions/serializers.py:ActivityPromotionSerializer.to_representation','Real model contract regression'))])
def test_actual_activity_promotion_contract(cid,data,services):
    obj=ActivityPromotion.objects.create(promotion=data.promotion,activity_date=services.ad)
    assert ActivityPromotionSerializer().to_representation(obj) is not None,'Valid activity promotion is discarded because model has activity_date but serializer reads activity'

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: PR-ACTUAL01
# Test Case ID: PR-AF01
# Test Case ID: PR-AF02
# Test Case ID: PR-AF03
# Test Case ID: PR-AF04
# Test Case ID: PR-AF05
# Test Case ID: PR-AF06
# Test Case ID: PR-AF07
# Test Case ID: PR-AF08
# Test Case ID: PR-AF09
# Test Case ID: PR-AF10
# Test Case ID: PR-AF11
# Test Case ID: PR-AF12
# Test Case ID: PR-AF13
# Test Case ID: PR-AF14
# Test Case ID: PR-AF15
# Test Case ID: PR-AF16
# Test Case ID: PR-AF17
# Test Case ID: PR-AF18
# Test Case ID: PR-F01
# Test Case ID: PR-F02
# Test Case ID: PR-F03
# Test Case ID: PR-F04
# Test Case ID: PR-F05
# Test Case ID: PR-F06
# Test Case ID: PR-F07
# Test Case ID: PR-F08
# Test Case ID: PR-F09
# Test Case ID: PR-F10
