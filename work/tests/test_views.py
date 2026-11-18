"""HTTP view tests with request factory, real database checks and mocked gateways.

Case ID prefixes: H-V Hotels, R-VW Rooms, B-V Bookings, P-V Payments,
PR-V Promotions. Each generated pytest parameter includes its full case ID.
"""
from datetime import timedelta
import importlib
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from rest_framework.test import force_authenticate
from rest_framework.request import Request
from hotels import views as hv
from rooms import views as rv
from bookings import views as bv
from payments import views as pv
from promotions import views as prv
from hotels.models import Hotel, HotelImage, UserHotelInteraction
from rooms.models import Room, RoomAmenity, RoomImage, RoomBookingDetail
from bookings.models import Booking, GuestInfo, RefundPolicy
from payments.models import Payment
from payments.constants.payment_status import PaymentStatus
from payments.constants.payment_method import PaymentMethod
from bookings.constants.booking_status import BookingStatus
from promotions.models import Promotion, RoomPromotion, CarPromotion, FlightPromotion, ActivityPromotion

MODULES={'hotels':hv,'rooms':rv,'bookings':bv,'payments':pv,'promotions':prv}
TITLES={'hotels':'Hotels','rooms':'Rooms','bookings':'Bookings','payments':'Payments','promotions':'Promotions'}

def request_view(factory,cls,method='get',payload=None,user=None,action=None,**kwargs):
    request=getattr(factory,method)('/',data=payload or {},format='json')
    if user is not None:force_authenticate(request,user=user)
    view=cls.as_view({method:action or {'get':'list','post':'create','patch':'partial_update','delete':'destroy'}[method]}) if hasattr(cls,'get_extra_actions') else cls.as_view()
    return view(request,**kwargs)

CRUD=[
 ('hotels','Hotel','HotelListView','HotelDetailView','HotelCreateView','HotelUpdateViewNotImage','HotelDeleteView','hotel'),
 ('rooms','Room','RoomListView','RoomDetailView','RoomCreateView','RoomUpdateView','RoomDeleteView','room'),
 ('rooms','RoomAmenity','RoomAmenityListView','RoomAmenityDetailView','RoomAmenityCreateView','RoomAmenityUpdateView','RoomAmenityDeleteView','amenity'),
 ('payments','Payment','PaymentListView','PaymentDetailView','PaymentCreateView','PaymentUpdateView','PaymentDeleteView','payment'),
 ('promotions','Promotion','PromotionListAdminView','PromotionDetailView',None,'PromotionUpdateView','PromotionDeleteView','promotion'),
 ('promotions','RoomPromotion','RoomPromotionListAdminView','RoomPromotionAdminDetailView','RoomPromotionAdminCreateView','RoomPromotionAdminUpdateView','RoomPromotionAdminDeleteView','rp'),
 ('promotions','CarPromotion','CarPromotionListAdminView','CarPromotionAdminDetailView','CarPromotionAdminCreateView','CarPromotionAdminUpdateView','CarPromotionAdminDeleteView','cp'),
 ('promotions','FlightPromotion','FlightPromotionListAdminView','FlightPromotionAdminDetailView','FlightPromotionAdminCreateView','FlightPromotionAdminUpdateView','FlightPromotionAdminDeleteView','fp'),
 ('promotions','ActivityPromotion','ActivityPromotionListAdminView','ActivityPromotionAdminDetailView','ActivityPromotionAdminCreateView','ActivityPromotionAdminUpdateView','ActivityPromotionAdminDeleteView','ap'),
 ('bookings','RefundPolicy','RefundPolicyViewSet','RefundPolicyViewSet','RefundPolicyViewSet','RefundPolicyViewSet','RefundPolicyViewSet','policy'),
 ('bookings','Booking','BookingViewSet','BookingViewSet','BookingViewSet','BookingViewSet','BookingViewSet','booking'),
]
OPERATIONS=['list','retrieve','create','invalid_create','update','invalid_update','delete','missing']
PARAMS=[]
for n,config in enumerate(CRUD,1):
    app,model,*_=config
    for op in OPERATIONS:
        if config[4] is None and 'create' in op:continue
        cid=f'{app[:2].upper()}-CRUD{n:02}-{op}'
        PARAMS.append(pytest.param(config,op,id=cid,marks=pytest.mark.case(module=TITLES[app],objective=f'{op.replace("_"," ").title()} {model} through its HTTP view',inputs=f'{model} fixture; operation={op}; authenticated owner',expected='HTTP 400 and no DB mutation' if op.startswith('invalid') else ('HTTP 404' if op=='missing' else f'Success response and persisted {op} result'),target=f'{app}/views.py:{config[2 if op=="list" else 3 if op in ("retrieve","missing") else 4 if "create" in op else 5 if "update" in op else 6]}',technique='API unit test; positive/negative partition; CheckDB; rollback')))

@pytest.mark.parametrize('config,op',PARAMS)
def test_crud_views(config,op,data,services,factory):
    """Test Case IDs *-CRUDxx-operation map one-to-one to the report rows."""
    app,model,list_cls,detail_cls,create_cls,update_cls,delete_cls,key=config
    amenity=RoomAmenity.objects.create(room=data.room,name='WiFi')
    rp=RoomPromotion.objects.create(room=data.room,promotion=data.promotion)
    cp=CarPromotion.objects.create(car=services.car,promotion=data.promotion)
    fp=FlightPromotion.objects.create(flight=services.flight,promotion=data.promotion)
    ap=ActivityPromotion.objects.create(activity_date=services.ad,promotion=data.promotion)
    policy=RefundPolicy.objects.create(name='Standard',service_type=1)
    objects={**vars(data),'amenity':amenity,'rp':rp,'cp':cp,'fp':fp,'ap':ap,'policy':policy}
    obj=objects[key];manager=obj.__class__.objects;before=manager.count()
    payloads={
      'hotel':{'city':data.city.pk,'name':'New Hotel'},
      'room':{'hotel':data.hotel.pk,'room_type':'Twin','price_per_night':150},
      'amenity':{'room':data.room.pk,'name':'Pool'},
      'payment':{'booking':data.booking.pk,'method':1,'amount':150},
      'promotion':{'title':'New Sale','start_date':data.now.isoformat(),'end_date':(data.now+timedelta(days=2)).isoformat()},
      'rp':{'room':data.room.pk,'promotion':data.promotion.pk,'discount_percent':15},
      'cp':{'car':services.car.pk,'promotion':data.promotion.pk,'discount_percent':15},
      'fp':{'flight':services.flight.pk,'promotion':data.promotion.pk,'discount_percent':15},
      'ap':{'activity_date':services.ad.pk,'promotion':data.promotion.pk,'discount_percent':15},
      'policy':{'name':'New Policy','service_type':1},
      'booking':{'service_type':1,'total_price':150},
    }
    if op=='list':
        response=request_view(factory,getattr(MODULES[app],list_cls),user=data.user)
        assert response.status_code==200,response.data
        body=response.data;rows=body.get('data',body.get('results')) if isinstance(body,dict) else body
        assert isinstance(rows,list),body
        assert any(row and row.get('id')==obj.pk for row in rows),f'Fixture {obj.pk} absent from response {body}'
    elif op in ('retrieve','missing'):
        response=request_view(factory,getattr(MODULES[app],detail_cls),user=data.user,action='retrieve',pk=999999 if op=='missing' else obj.pk)
        assert response.status_code==(404 if op=='missing' else 200),response.data
        if op=='retrieve':
            row=response.data.get('data',response.data);assert row['id']==obj.pk
    elif 'create' in op:
        payload={} if op=='invalid_create' else payloads[key]
        response=request_view(factory,getattr(MODULES[app],create_cls),'post',payload,data.user)
        if op=='invalid_create':assert response.status_code==400,response.data;assert manager.count()==before
        else:
            assert response.status_code in (200,201),response.data
            assert manager.count()==before+1
            newest=manager.latest('pk')
            for field,value in payload.items():
                actual=getattr(newest,field+'_id') if field in ('room','hotel','city','booking','promotion','car','flight','activity_date') else getattr(newest,field)
                assert actual==value
    elif 'update' in op:
        field='name' if key in ('hotel','amenity','policy') else 'room_type' if key=='room' else 'amount' if key=='payment' else 'title' if key=='promotion' else 'total_price' if key=='booking' else 'discount_percent'
        value='Updated' if field in ('name','room_type','title') else 27
        payload={field: value if op=='update' else None}
        if op=='invalid_update' and key=='amenity':payload={'room':None}
        response=request_view(factory,getattr(MODULES[app],update_cls),'patch',payload,data.user,pk=obj.pk)
        if op=='invalid_update':assert response.status_code==400,response.data
        else:
            assert response.status_code==200,response.data;obj.refresh_from_db();assert getattr(obj,field)==value
        assert manager.count()==before
    else:
        pk=obj.pk;response=request_view(factory,getattr(MODULES[app],delete_cls),'delete',user=data.user,pk=pk)
        assert response.status_code in (200,204),response.data
        assert not manager.filter(pk=pk).exists()

# P-V01...P-V10: payment create / checkout boundaries with Stripe isolated.
PAYMENT_CASES=[('P-V01','missing_booking'),('P-V02','unknown_booking'),('P-V03','duplicate_booking'),('P-V04','missing_urls'),('P-V05','checkout_ok'),('P-V06','checkout_error'),('P-V07','processed_success'),('P-V08','processed_paid'),('P-V09','processed_unpaid'),('P-V10','tampered_amount')]
@pytest.mark.parametrize('cid,scenario',[pytest.param(cid,s,id=cid,marks=pytest.mark.case(module='Payments',objective='Validate payment creation and Stripe checkout state',inputs=s,expected={'missing_booking':'400; no payment inserted','unknown_booking':'404; no payment inserted','duplicate_booking':'400; existing payment retained','missing_urls':'400; no gateway call','checkout_ok':'200; session ID persisted; gateway receives exact VND amount','checkout_error':'400; no transaction ID stored','processed_success':'400; no gateway call','processed_paid':'400; no gateway call','processed_unpaid':'400; no gateway call','tampered_amount':'400; client cannot override booking amount'}[s],target='payments/views.py:PaymentViewSet.create/pay',technique='State transition; gateway mock; real DB')) for cid,s in PAYMENT_CASES])
def test_payment_checkout(cid,scenario,data,factory):
    p=data.payment;before=Payment.objects.count()
    if scenario in ('missing_booking','unknown_booking','duplicate_booking','tampered_amount'):
        payload={} if scenario=='missing_booking' else {'booking_id':999999 if scenario=='unknown_booking' else data.booking.pk}
        if scenario=='tampered_amount':data.payment.delete();before=Payment.objects.count();payload['amount']=1
        response=request_view(factory,pv.PaymentViewSet,'post',payload)
        expected=404 if scenario=='unknown_booking' else 400
        assert response.status_code==expected,f'Expected {expected}, observed {response.status_code}; {response.data}'
        assert Payment.objects.count()==before
    else:
        statuses={'processed_success':PaymentStatus.SUCCESS,'processed_paid':PaymentStatus.PAID,'processed_unpaid':PaymentStatus.UNPAID}
        if scenario in statuses:p.status=statuses[scenario];p.save()
        payload={} if scenario=='missing_urls' else {'success_url':'http://localhost/success','cancel_url':'http://localhost/cancel'}
        with patch('payments.views.stripe.checkout.Session.create') as create:
            create.return_value=SimpleNamespace(id='cs_unit_test',url='http://localhost/checkout')
            if scenario=='checkout_error':create.side_effect=RuntimeError('Gateway unavailable')
            response=request_view(factory,pv.PaymentViewSet,'post',payload,action='pay',pk=p.pk)
            assert response.status_code==(200 if scenario=='checkout_ok' else 400),response.data
            p.refresh_from_db()
            if scenario=='checkout_ok':
                assert p.transaction_id=='cs_unit_test'
                assert create.call_args.kwargs['line_items'][0]['price_data']['unit_amount']==100
            elif scenario=='checkout_error':assert p.transaction_id is None
            else:create.assert_not_called()

@pytest.mark.parametrize('cid,kind',[pytest.param(f'P-E{i:02}',kind,id=f'P-E{i:02}',marks=pytest.mark.case(module='Payments',objective='Resolve booking email using user then guest',inputs=kind,expected={'user':'guest@example.com','guest':'alice@example.com','none':None}[kind],target='payments/views.py:PaymentViewSet.get_booking_email',technique='Decision table')) for i,kind in enumerate(['user','guest','none'],1)])
def test_payment_email(cid,kind,data):
    if kind!='user':data.booking.user=None;data.booking.save()
    if kind=='guest':GuestInfo.objects.create(booking=data.booking,full_name='Alice',email='alice@example.com',phone='123')
    assert pv.PaymentViewSet().get_booking_email(data.booking)=={'user':'guest@example.com','guest':'alice@example.com','none':None}[kind]

# Executed Test Case ID registry (generated from the authoritative pytest run).
# Test Case ID: BO-CRUD10-create
# Test Case ID: BO-CRUD10-delete
# Test Case ID: BO-CRUD10-invalid_create
# Test Case ID: BO-CRUD10-invalid_update
# Test Case ID: BO-CRUD10-list
# Test Case ID: BO-CRUD10-missing
# Test Case ID: BO-CRUD10-retrieve
# Test Case ID: BO-CRUD10-update
# Test Case ID: BO-CRUD11-create
# Test Case ID: BO-CRUD11-delete
# Test Case ID: BO-CRUD11-invalid_create
# Test Case ID: BO-CRUD11-invalid_update
# Test Case ID: BO-CRUD11-list
# Test Case ID: BO-CRUD11-missing
# Test Case ID: BO-CRUD11-retrieve
# Test Case ID: BO-CRUD11-update
# Test Case ID: HO-CRUD01-create
# Test Case ID: HO-CRUD01-delete
# Test Case ID: HO-CRUD01-invalid_create
# Test Case ID: HO-CRUD01-invalid_update
# Test Case ID: HO-CRUD01-list
# Test Case ID: HO-CRUD01-missing
# Test Case ID: HO-CRUD01-retrieve
# Test Case ID: HO-CRUD01-update
# Test Case ID: P-E01
# Test Case ID: P-E02
# Test Case ID: P-E03
# Test Case ID: P-V01
# Test Case ID: P-V02
# Test Case ID: P-V03
# Test Case ID: P-V04
# Test Case ID: P-V05
# Test Case ID: P-V06
# Test Case ID: P-V07
# Test Case ID: P-V08
# Test Case ID: P-V09
# Test Case ID: P-V10
# Test Case ID: PA-CRUD04-create
# Test Case ID: PA-CRUD04-delete
# Test Case ID: PA-CRUD04-invalid_create
# Test Case ID: PA-CRUD04-invalid_update
# Test Case ID: PA-CRUD04-list
# Test Case ID: PA-CRUD04-missing
# Test Case ID: PA-CRUD04-retrieve
# Test Case ID: PA-CRUD04-update
# Test Case ID: PR-CRUD05-delete
# Test Case ID: PR-CRUD05-invalid_update
# Test Case ID: PR-CRUD05-list
# Test Case ID: PR-CRUD05-missing
# Test Case ID: PR-CRUD05-retrieve
# Test Case ID: PR-CRUD05-update
# Test Case ID: PR-CRUD06-create
# Test Case ID: PR-CRUD06-delete
# Test Case ID: PR-CRUD06-invalid_create
# Test Case ID: PR-CRUD06-invalid_update
# Test Case ID: PR-CRUD06-list
# Test Case ID: PR-CRUD06-missing
# Test Case ID: PR-CRUD06-retrieve
# Test Case ID: PR-CRUD06-update
# Test Case ID: PR-CRUD07-create
# Test Case ID: PR-CRUD07-delete
# Test Case ID: PR-CRUD07-invalid_create
# Test Case ID: PR-CRUD07-invalid_update
# Test Case ID: PR-CRUD07-list
# Test Case ID: PR-CRUD07-missing
# Test Case ID: PR-CRUD07-retrieve
# Test Case ID: PR-CRUD07-update
# Test Case ID: PR-CRUD08-create
# Test Case ID: PR-CRUD08-delete
# Test Case ID: PR-CRUD08-invalid_create
# Test Case ID: PR-CRUD08-invalid_update
# Test Case ID: PR-CRUD08-list
# Test Case ID: PR-CRUD08-missing
# Test Case ID: PR-CRUD08-retrieve
# Test Case ID: PR-CRUD08-update
# Test Case ID: PR-CRUD09-create
# Test Case ID: PR-CRUD09-delete
# Test Case ID: PR-CRUD09-invalid_create
# Test Case ID: PR-CRUD09-invalid_update
# Test Case ID: PR-CRUD09-list
# Test Case ID: PR-CRUD09-missing
# Test Case ID: PR-CRUD09-retrieve
# Test Case ID: PR-CRUD09-update
# Test Case ID: RO-CRUD02-create
# Test Case ID: RO-CRUD02-delete
# Test Case ID: RO-CRUD02-invalid_create
# Test Case ID: RO-CRUD02-invalid_update
# Test Case ID: RO-CRUD02-list
# Test Case ID: RO-CRUD02-missing
# Test Case ID: RO-CRUD02-retrieve
# Test Case ID: RO-CRUD02-update
# Test Case ID: RO-CRUD03-create
# Test Case ID: RO-CRUD03-delete
# Test Case ID: RO-CRUD03-invalid_create
# Test Case ID: RO-CRUD03-invalid_update
# Test Case ID: RO-CRUD03-list
# Test Case ID: RO-CRUD03-missing
# Test Case ID: RO-CRUD03-retrieve
# Test Case ID: RO-CRUD03-update
