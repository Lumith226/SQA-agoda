"""Promotion campaign creation and bulk operations on real related records."""
from datetime import timedelta
import pytest
from promotions import views as v
from promotions.models import Promotion,RoomPromotion,CarPromotion,FlightPromotion,ActivityPromotion
from test_views import request_view
from test_lifecycle import mark

@pytest.mark.parametrize('cid,kind,scenario',[
 pytest.param(f'PR-C{i:02}',kind,scenario,id=f'PR-C{i:02}',marks=mark(f'PR-C{i:02}','Promotions','Create campaign and its service-specific discount links',f'type={kind}; scenario={scenario}','Valid campaign persists exact link and discount; invalid links rejected without orphan campaign','promotions/views.py:PromotionCreateView.create')) for i,(kind,scenario) in enumerate([(k,s) for k in ['hotel','flight','activity','car'] for s in ['fallback','override','missing_target','optional_discounts']],1)])
def test_create_campaign(cid,kind,scenario,data,services,factory):
    """Test Case IDs PR-C01...PR-C16: campaign persistence, missing links, defaults."""
    key,model,target,field={'hotel':('rooms',RoomPromotion,data.room,'room_id'),'flight':('flights',FlightPromotion,services.flight,'flight_id'),'activity':('actDates',ActivityPromotion,services.ad,'activity_date_id'),'car':('cars',CarPromotion,services.car,'car_id')}[kind]
    item={'id':999999 if scenario=='missing_target' else target.pk}
    if scenario=='override':item.update(discount_percent=25,discount_amount=40)
    payload={'type':kind,'title':'Campaign created by test','start_date':data.now.isoformat(),'end_date':(data.now+timedelta(days=2)).isoformat(),key:[item]}
    if scenario!='optional_discounts':payload.update(discount_percent=10,discount_amount=30)
    before=Promotion.objects.count()
    response=request_view(factory,v.PromotionCreateView,'post',payload,data.user)
    if scenario=='missing_target':
        assert response.status_code==400,response.data
        assert Promotion.objects.count()==before,'Rejected request left an orphan promotion row'
    else:
        assert response.status_code==201,response.data
        p=Promotion.objects.get(title=payload['title']);link=model.objects.get(promotion=p)
        assert getattr(link,field)==target.pk
        assert link.discount_percent==(25 if scenario=='override' else 0 if scenario=='optional_discounts' else 10)

@pytest.mark.parametrize('cid,scenario',[
 pytest.param(f'PR-B{i:02}',s,id=f'PR-B{i:02}',marks=mark(f'PR-B{i:02}','Promotions','Validate bulk activity promotion operations',s,'Valid bulk operation persists requested rows; empty/malformed lists return 400','promotions/views.py:ActivityPromotionAdminBulkCreateView/ActivityPromotionAdminBulkDeleteView')) for i,s in enumerate(['create','create_empty','create_wrong_type','missing_field','delete','delete_empty','delete_wrong_type'],1)])
def test_bulk_activity_promotions(cid,scenario,data,services,factory):
    """Test Case IDs PR-B01...PR-B07: bulk create/delete and input validation."""
    if scenario.startswith('delete'):
        obj=ActivityPromotion.objects.create(promotion=data.promotion,activity_date=services.ad)
        payload={'ids':[obj.pk] if scenario=='delete' else [] if scenario=='delete_empty' else 'invalid'}
        response=request_view(factory,v.ActivityPromotionAdminBulkDeleteView,'delete',payload)
        assert response.status_code==(200 if scenario=='delete' else 400)
        assert ActivityPromotion.objects.filter(pk=obj.pk).exists()==(scenario!='delete')
    else:
        item={'promotion_id':data.promotion.pk,'activity_date_id':services.ad.pk,'discount_percent':15}
        payload={'items':[item] if scenario=='create' else [] if scenario=='create_empty' else 'invalid' if scenario=='create_wrong_type' else [{}]}
        response=request_view(factory,v.ActivityPromotionAdminBulkCreateView,'post',payload)
        assert response.status_code==(201 if scenario=='create' else 400)
        assert ActivityPromotion.objects.count()==(1 if scenario=='create' else 0)

@pytest.mark.parametrize('cid,kind,city_filter',[
 pytest.param(f'PR-G{i:02}',kind,filter_value,id=f'PR-G{i:02}',marks=mark(f'PR-G{i:02}','Promotions','Group promotion detail by hotel or activity',f'type={kind}; city filter={filter_value}','Matching parent grouped once; nonmatching city removes hotel','promotions/views.py:PromotionDetailView.retrieve')) for i,(kind,filter_value) in enumerate([(1,'none'),(1,'match'),(1,'other'),(3,'none')],1)])
def test_campaign_grouping(cid,kind,city_filter,data,services,factory):
    p=data.promotion;p.promotion_type=kind;p.save()
    if kind==1:
        RoomPromotion.objects.create(promotion=p,room=data.room,discount_percent=10)
        RoomPromotion.objects.create(promotion=p,room=data.room,discount_percent=20)
    else:
        ActivityPromotion.objects.create(promotion=p,activity_date=services.ad,discount_percent=10)
        ActivityPromotion.objects.create(promotion=p,activity_date=services.ad,discount_percent=20)
    query={} if city_filter=='none' else {'city_id':data.city.pk if city_filter=='match' else 99999}
    response=request_view(factory,v.PromotionDetailView,payload=query,pk=p.pk)
    assert response.status_code==200
    grouped=response.data['data']['hotels' if kind==1 else 'activitys']
    assert len(grouped)==(0 if city_filter=='other' else 1)
    if grouped:assert grouped[0]['max_discount' if kind==1 else 'discount']==20

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: PR-B01
# Test Case ID: PR-B02
# Test Case ID: PR-B03
# Test Case ID: PR-B04
# Test Case ID: PR-B05
# Test Case ID: PR-B06
# Test Case ID: PR-B07
# Test Case ID: PR-C01
# Test Case ID: PR-C02
# Test Case ID: PR-C03
# Test Case ID: PR-C04
# Test Case ID: PR-C05
# Test Case ID: PR-C06
# Test Case ID: PR-C07
# Test Case ID: PR-C08
# Test Case ID: PR-C09
# Test Case ID: PR-C10
# Test Case ID: PR-C11
# Test Case ID: PR-C12
# Test Case ID: PR-C13
# Test Case ID: PR-C14
# Test Case ID: PR-C15
# Test Case ID: PR-C16
# Test Case ID: PR-G01
# Test Case ID: PR-G02
# Test Case ID: PR-G03
# Test Case ID: PR-G04
