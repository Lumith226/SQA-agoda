"""Declare 150 API cases before execution, with independent response/DB contracts.

Thirty business cases per module are explicit below. A case may have several
HTTP steps to test persistence and alternate exposed routes in one transaction.
Expected results are never learned from a response or from a prior run.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))

CASES = []
PREFIXES = {'Hotels':'API-H','Rooms':'API-R','Bookings':'API-B','Payments':'API-P','Promotions':'API-PR'}

def change(model, *, delta=0, rows=None, absent=None, allowed=None, preserve=None):
    """Describe exact persisted counts/values plus the allowed change boundary."""
    return {'unchanged':False,'allowed_models':[model]+(allowed or []),
            'tables':{model:{'delta':delta,'rows':rows or [],'absent':absent or [],'preserve':preserve or []}}}

def row(record_id, **fields):
    """Identify a persisted row without deriving its values from the API result."""
    return {'id':record_id,'fields':fields}

def step(method, path, *, status=200, body=None, obj=None, rows=None, db=None,
         error=None, fields=None, auth='owner_token', row_path=None, raw=None, external=None):
    """One real HTTP operation with concrete response and database assertions."""
    expected = {'status':status,'database':db or {'unchanged':True}}
    if obj is not None: expected['object'] = obj
    if rows is not None: expected['rows'] = rows
    if row_path: expected['row_path'] = row_path
    if error: expected['error_contains'] = error
    if fields: expected['root_fields'] = fields
    if status == 204: expected['empty_body'] = True
    if external: expected['external'] = external
    return {'method':method,'path':path,'body':body,'raw':raw,'auth':auth,'expect':expected}

def add(module, objective, *steps, profile=None, stripe=None, oracle_note=None):
    """Register a named Test Case ID and its complete Arrange/Act/Assert/Cleanup plan."""
    number = 1 + sum(case['module']==module for case in CASES)
    case_id = f'{PREFIXES[module]}-{number:03}'
    for index, operation in enumerate(steps,1):
        operation['id'] = f'{case_id}-S{index:02}'
    CASES.append({'id':case_id,'module':module,'objective':objective,'steps':list(steps),
        'profile':profile or {},'stripe':stripe or {},'oracle_note':oracle_note or 'Source-defined serializer/view contract; prepared fixtures are independent of responses.'})

def profile(model, **values):
    """Select a precondition; this is arranged before DB observations begin."""
    return {'updates':[{'model':model,'id':1,'values':values}]}

HOTEL='/api/hotels/hotels/'
ROOM='/api/rooms/rooms/'
BOOK='/api/bookings/'
PAY='/api/payments/'
PROMO='/api/promotions/'
HOTEL_ROW={'id':1,'name':'Lotus Hotel','city.id':1,'min_price':100}
ROOM_ROW={'id':1,'room_type':'Deluxe','price_per_night':100,'available_rooms':10}
BOOK_ROW={'id':1,'booking_code':'AGDAPI1','service_type':1,'total_price':100,'final_price':100}
PAY_ROW={'id':1,'amount':100,'method':1,'status':1,'booking.id':1}
NEW_HOTEL={'city':1,'owner':1,'name':'API New Hotel','avg_star':3}
NEW_ROOM={'hotel':1,'room_type':'API Suite','price_per_night':200,'price_per_day':90,
          'adults_capacity':2,'children_capacity':1,'total_rooms':5,'available_rooms':5}
NEW_PROMO={'title':'API Campaign','discount_percent':15,'discount_amount':0,
           'start_date':'2030-01-01T00:00:00Z','end_date':'2030-02-01T00:00:00Z','promotion_type':1}

# Hotels: filters, HTTP authentication, field validation, image/row changes and interaction state.
add('Hotels','List hotels with exact IDs and stored prices',step('GET',HOTEL,rows=[HOTEL_ROW,{'id':2,'name':'Harbor Hotel','min_price':300}]))
add('Hotels','Select hotel by matching name',step('GET',HOTEL+'?name=Lotus',rows=[HOTEL_ROW]))
add('Hotels','Exclude hotels for unmatched name',step('GET',HOTEL+'?name=NoSuchHotel',rows=[]))
add('Hotels','Filter by city foreign key',step('GET',HOTEL+'?cityId=1',rows=[HOTEL_ROW]))
add('Hotels','Filter by owner foreign key',step('GET',HOTEL+'?ownerId=2',rows=[{'id':2,'name':'Harbor Hotel'}]))
add('Hotels','Sort by descending hotel name',step('GET',HOTEL+'?sort=name-desc',rows=[HOTEL_ROW,{'id':2,'name':'Harbor Hotel'}]))
add('Hotels','Paginate with one record per page',step('GET',HOTEL+'?pageSize=1&current=1',rows=[HOTEL_ROW],fields={'meta.totalItems':2,'meta.itemsPerPage':1}))
add('Hotels','Return the second page without duplicating the first',step('GET',HOTEL+'?pageSize=1&current=2',rows=[{'id':2,'name':'Harbor Hotel'}],fields={'meta.currentPage':2}))
add('Hotels','Retrieve an existing hotel and its city',step('GET',HOTEL+'1/',obj=HOTEL_ROW))
add('Hotels','Reject a missing hotel ID',step('GET',HOTEL+'9999/',status=404,error='No Hotel matches'))
add('Hotels','Read public hotel details without authentication',step('GET',HOTEL+'1/',auth=None,obj=HOTEL_ROW))
add('Hotels','Create hotel with an image and verify both rows',step('POST',HOTEL+'create/',body={**NEW_HOTEL,'images':['/media/new-hotel.png']},obj={'name':'API New Hotel','city':1},db=change('hotels.Hotel',delta=1,rows=[row(3,name='API New Hotel',city_id=1,owner_id=1)],allowed=['hotels.HotelImage'])),step('GET',HOTEL+'3/',obj={'id':3,'name':'API New Hotel'}))
add('Hotels','Reject hotel creation without name',step('POST',HOTEL+'create/',body={'city':1},status=400,error='This field is required.'))
add('Hotels','Reject hotel creation without city',step('POST',HOTEL+'create/',body={'name':'No city'},status=400,error='This field is required.'))
add('Hotels','Reject nonexistent city foreign key',step('POST',HOTEL+'create/',body={**NEW_HOTEL,'city':9999},status=400,error='does not exist'))
add('Hotels','Reject a name above its 255-character boundary',step('POST',HOTEL+'create/',body={**NEW_HOTEL,'name':'X'*256},status=400,error='255 characters'))
add('Hotels','Require authentication for hotel creation',step('POST',HOTEL+'create/',body=NEW_HOTEL,auth=None,status=401,error='Authentication credentials were not provided'))
add('Hotels','Reject a malformed JWT without inserting a hotel',step('POST',HOTEL+'create/',body=NEW_HOTEL,auth='invalid',status=401,error='token'))
add('Hotels','Persist PATCH and PUT on the exposed detail route',step('PATCH',HOTEL+'1/',body={'name':'Detail PATCH'},obj={'name':'Detail PATCH'},db=change('hotels.Hotel',rows=[row(1,name='Detail PATCH')])),step('PUT',HOTEL+'1/',body={'name':'Detail PUT'},obj={'name':'Detail PUT'},db=change('hotels.Hotel',rows=[row(1,name='Detail PUT')])),step('GET',HOTEL+'1/',obj={'name':'Detail PUT'}))
add('Hotels','Persist PUT and PATCH on the dedicated update route',step('PUT',HOTEL+'1/update/',body={'name':'Updated Hotel','images':['/media/replaced.png']},obj={'name':'Updated Hotel'},db=change('hotels.Hotel',rows=[row(1,name='Updated Hotel')],allowed=['hotels.HotelImage'])),step('PATCH',HOTEL+'1/update/',body={'description':'Updated description'},obj={'description':'Updated description'},db=change('hotels.Hotel',rows=[row(1,description='Updated description')],allowed=['hotels.HotelImage'])))
add('Hotels','Update without replacing the existing hotel image',step('PATCH',HOTEL+'1/update/not-image/',body={'name':'Preserved image'},obj={'name':'Preserved image'},db=change('hotels.Hotel',rows=[row(1,name='Preserved image')])),step('PUT',HOTEL+'1/update/not-image/',body={'description':'PUT without image'},obj={'description':'PUT without image'},db=change('hotels.Hotel',rows=[row(1,description='PUT without image')])) )
add('Hotels','Reject invalid city update without partial changes',step('PATCH',HOTEL+'1/update/not-image/',body={'city':9999,'name':'Must not persist'},status=400,error='does not exist'))
add('Hotels','Delete hotel and dependent rooms through dedicated route',step('DELETE',HOTEL+'1/delete/',status=204,db=change('hotels.Hotel',delta=-1,absent=[1],allowed=['hotels.HotelImage','hotels.UserHotelInteraction','rooms.Room','rooms.RoomImage','rooms.RoomAmenity','promotions.RoomPromotion'])),step('GET',HOTEL+'1/',status=404,error='No Hotel matches'))
add('Hotels','Delete through the exposed detail route',step('DELETE',HOTEL+'1/',status=204,db=change('hotels.Hotel',delta=-1,absent=[1],allowed=['hotels.HotelImage','hotels.UserHotelInteraction','rooms.Room','rooms.RoomImage','rooms.RoomAmenity','promotions.RoomPromotion'])))
add('Hotels','Delete one image while preserving its hotel',step('DELETE','/api/hotels/hotel-images/1/delete/',status=204,db=change('hotels.HotelImage',delta=-1,absent=[1])))
add('Hotels','Select hotels within a requested city',step('GET','/api/hotels/by-city/1/',rows=[HOTEL_ROW]))
add('Hotels','Search hotels and return an empty set for a miss',step('GET','/api/hotels/search/?hotel_name=Lotus',rows=[{'id':1,'name':'Lotus Hotel'}],row_path='results.data'),step('GET','/api/hotels/search/?hotel_name=NoSuchHotel',rows=[],row_path='results.data'))
add('Hotels','Retrieve the authenticated user interaction',step('GET','/api/hotels/user-hotel-interaction/1/',obj={'id':1,'click_count':1,'hotel.name':'Lotus Hotel'}))
add('Hotels','Upsert interaction counters and update aggregate hotel counters',step('POST','/api/hotels/user-hotel-interaction/upsert/',body={'hotel_id':1,'click_count':4,'positive_count':2,'negative_count':1,'neutral_count':0},obj={'click_count':4,'positive_count':2},db=change('hotels.UserHotelInteraction',rows=[row(1,click_count=4,positive_count=2,negative_count=1)],allowed=['hotels.Hotel'])),step('GET','/api/hotels/user-hotel-interaction/1/',obj={'click_count':4,'positive_count':2}))
add('Hotels','Reject missing upsert input and unroutable direct update methods',step('POST','/api/hotels/user-hotel-interaction/upsert/',body={},status=400,error='Missing hotel_id'),step('PUT','/api/hotels/user-hotel-interaction/upsert/',body={'hotel_id':1},status=405,error='not allowed'),step('PATCH','/api/hotels/user-hotel-interaction/upsert/',body={'hotel_id':1},status=405,error='not allowed'),oracle_note='POST validation follows source. PUT/PATCH have no object lookup on this collection route and should reject the method instead of returning a server error.')

# Rooms: inventory filtering, room/amenity CRUD, booking details and atomic rejects.
add('Rooms','List rooms with exact inventory and nightly prices',step('GET',ROOM,rows=[ROOM_ROW,{'id':2,'room_type':'Family','price_per_night':300,'available_rooms':10}]))
add('Rooms','Filter rooms by hotel',step('GET',ROOM+'?hotel_id=1',rows=[ROOM_ROW]))
add('Rooms','Filter rooms by hotel owner',step('GET',ROOM+'?owner_id=2',rows=[{'id':2,'room_type':'Family'}]))
add('Rooms','Filter overnight rooms at the exact lower price boundary',step('GET','/api/rooms/rooms-admin/?min_price_per_night=100',rows=[ROOM_ROW]))
add('Rooms','Filter day-use rooms by daily price',step('GET','/api/rooms/rooms-admin/?max_price_per_day=80',rows=[{'id':2,'room_type':'Family','price_per_day':80}]))
add('Rooms','Exclude rooms without sufficient adult capacity',step('GET',ROOM+'?adults=3',rows=[{'id':2,'adults_capacity':3}]))
add('Rooms','Exclude zero-inventory rooms from the public list',step('GET',ROOM,rows=[{'id':2,'available_rooms':10}]),profile=profile('rooms.Room',available_rooms=0,available=False))
add('Rooms','Return both available and unavailable rooms to the admin list',step('GET','/api/rooms/rooms-admin/',rows=[{'id':1,'available_rooms':0},{'id':2,'available_rooms':10}]),profile=profile('rooms.Room',available_rooms=0,available=False))
add('Rooms','Paginate the room list without changing inventory',step('GET',ROOM+'?pageSize=1&current=2',rows=[{'id':2,'room_type':'Family'}],fields={'meta.totalItems':2}))
add('Rooms','Retrieve room with nested hotel identity',step('GET',ROOM+'1/',obj={**ROOM_ROW,'hotel.id':1,'hotel.name':'Lotus Hotel'}))
add('Rooms','Return the implemented missing-room error without DB changes',step('GET',ROOM+'9999/',status=400,error='No Room matches'))
add('Rooms','Search available rooms by hotel name',step('GET',ROOM+'search/?hotel_name=Lotus',obj={'id':1,'name':'Lotus Hotel'},rows=[{'id':1,'name':'Deluxe','price':100}],row_path='data.rooms'))
add('Rooms','Reject room search without hotel_name',step('GET',ROOM+'search/',status=400,error='hotel_name'))
add('Rooms','Create room and verify persisted hotel/price/inventory',step('POST',ROOM+'create/',body=NEW_ROOM,obj={'room_type':'API Suite','hotel':1,'price_per_night':200},db=change('rooms.Room',delta=1,rows=[row(3,hotel_id=1,room_type='API Suite',price_per_night=200,available_rooms=5)],allowed=['hotels.Hotel'])),step('GET',ROOM+'3/',obj={'id':3,'room_type':'API Suite','available_rooms':5}))
add('Rooms','Reject room creation with nonexistent hotel',step('POST',ROOM+'create/',body={**NEW_ROOM,'hotel':9999},status=400,error='does not exist'))
add('Rooms','Reject room creation without room_type',step('POST',ROOM+'create/',body={key:value for key,value in NEW_ROOM.items() if key!='room_type'},status=400,error='This field is required.'))
add('Rooms','Reject negative room inventory',step('POST',ROOM+'create/',body={**NEW_ROOM,'available_rooms':-1},status=400,error='greater than or equal to 0'),oracle_note='Inventory is a nonnegative domain quantity; the API must reject negative stock without a partial insert.')
add('Rooms','Reject nonnumeric nightly price',step('POST',ROOM+'create/',body={**NEW_ROOM,'price_per_night':'expensive'},status=400,error='valid number'))
add('Rooms','Persist room PATCH and PUT and verify subsequent reads',step('PATCH',ROOM+'1/update/',body={'room_type':'Updated Suite'},obj={'room_type':'Updated Suite'},db=change('rooms.Room',rows=[row(1,room_type='Updated Suite')],allowed=['rooms.RoomImage','hotels.Hotel'])),step('PUT',ROOM+'1/update/',body={'price_per_night':125},obj={'price_per_night':125},db=change('rooms.Room',rows=[row(1,price_per_night=125)],allowed=['rooms.RoomImage','hotels.Hotel'])),step('GET',ROOM+'1/',obj={'room_type':'Updated Suite','price_per_night':125}))
add('Rooms','Reject an invalid hotel update atomically',step('PATCH',ROOM+'1/update/',body={'hotel':9999,'room_type':'Must not persist'},status=400,error='does not exist'))
add('Rooms','Delete a room and its image/amenity/promotion dependents',step('DELETE',ROOM+'1/delete/',status=204,db=change('rooms.Room',delta=-1,absent=[1],allowed=['rooms.RoomImage','rooms.RoomAmenity','promotions.RoomPromotion','hotels.Hotel'])))
add('Rooms','Delete room image without deleting the room',step('DELETE','/api/rooms/room-images/1/delete/',status=204,db=change('rooms.RoomImage',delta=-1,absent=[1])))
add('Rooms','Filter amenities by room',step('GET','/api/rooms/amenities/?room_id=1',rows=[{'id':1,'name':'WiFi','room.id':1}]))
add('Rooms','Create amenity and verify its foreign key',step('POST','/api/rooms/amenities/create/',body={'room':1,'name':'Breakfast'},obj={'name':'Breakfast','room':1},db=change('rooms.RoomAmenity',delta=1,rows=[row(3,room_id=1,name='Breakfast')])),step('GET','/api/rooms/amenities/3/',obj={'id':3,'name':'Breakfast','room.id':1}))
add('Rooms','Reject an amenity without its room',step('POST','/api/rooms/amenities/create/',body={'name':'No room'},status=400,error='This field is required.'))
add('Rooms','Update an amenity through detail and dedicated routes',*[step(method,path,body={'name':name},obj={'name':name},db=change('rooms.RoomAmenity',rows=[row(1,name=name)])) for method,path,name in [('PATCH','/api/rooms/amenities/1/','Detail PATCH'),('PUT','/api/rooms/amenities/1/','Detail PUT'),('PATCH','/api/rooms/amenities/1/update/','Alias PATCH'),('PUT','/api/rooms/amenities/1/update/','Alias PUT')]])
add('Rooms','Delete amenities through both exposed delete routes',step('DELETE','/api/rooms/amenities/1/',status=204,db=change('rooms.RoomAmenity',delta=-1,absent=[1])),step('DELETE','/api/rooms/amenities/2/delete/',status=200,fields={'isSuccess':True},db=change('rooms.RoomAmenity',delta=-1,absent=[2])))
add('Rooms','Reject an unknown amenity foreign key',step('PATCH','/api/rooms/amenities/1/update/',body={'room':9999},status=400,error='does not exist'))
add('Rooms','Retrieve a real booking detail with computed price',step('GET','/api/rooms/rooms-booking/1/',obj={'id':1,'room.id':1,'room_count':1,'total_price':100,'final_price':95}),profile={'room_booking':True})
add('Rooms','Reject an expired JWT before serving the room list',step('GET',ROOM,auth='expired_token',status=401,error='expired'))

# Bookings: CRUD, guest identity, service validation, cancellation and rebooking.
add('Bookings','List bookings in descending ID order',step('GET',BOOK,rows=[{'id':3,'booking_code':'AGDAPI3'},{'id':2,'booking_code':'AGDAPI2'},BOOK_ROW]))
add('Bookings','Filter bookings by authenticated owner email',step('GET',BOOK+'?email=owner1@example.com',rows=[{'id':3},BOOK_ROW]))
add('Bookings','Filter bookings by guest email',step('GET',BOOK+'?email=guest2@example.com',rows=[{'id':2,'service_type':2}]))
add('Bookings','Return no bookings for unmatched email',step('GET',BOOK+'?email=absent@example.com',rows=[]))
add('Bookings','Filter by service type',step('GET',BOOK+'?service_type=2',rows=[{'id':2,'service_type':2}]))
add('Bookings','Paginate booking list with exact item totals',step('GET',BOOK+'?pageSize=1&current=2',rows=[{'id':2}],fields={'meta.totalItems':3,'meta.currentPage':2}))
add('Bookings','Retrieve booking prices and guest identity',step('GET',BOOK+'1/',obj={**BOOK_ROW,'guest_info.email':'guest1@example.com'}))
add('Bookings','Reject missing booking ID',step('GET',BOOK+'9999/',status=404,error='No Booking matches'))
add('Bookings','Create booking with persisted guest information',step('POST',BOOK,status=201,body={'service_type':1,'total_price':150,'final_price':150,'guest_info':{'full_name':'API Guest','email':'api@example.com','phone':'0901234567'}},fields={'booking_id':4,'isSuccess':True},db=change('bookings.Booking',delta=1,rows=[row(4,service_type=1,user_id=1,total_price=150,final_price=150)],allowed=['bookings.GuestInfo'])),step('GET',BOOK+'4/',obj={'id':4,'guest_info.full_name':'API Guest','guest_info.email':'api@example.com'}))
add('Bookings','Create an anonymous guest booking without assigning an owner',step('POST',BOOK,status=201,auth=None,body={'service_type':1,'total_price':100,'final_price':100,'guest_info':{'full_name':'Anonymous Guest','email':'anon@example.com','phone':'0900000000'}},fields={'booking_id':4},db=change('bookings.Booking',delta=1,rows=[row(4,user_id=None,service_type=1)],allowed=['bookings.GuestInfo'])))
add('Bookings','Reject missing service type',step('POST',BOOK,status=400,body={'total_price':100},error='This field is required.'))
add('Bookings','Reject an unsupported service-type choice',step('POST',BOOK,status=400,body={'service_type':99},error='not a valid choice'))
add('Bookings','Reject an invalid guest email atomically',step('POST',BOOK,status=400,body={'service_type':1,'guest_info':{'full_name':'Bad email','email':'wrong','phone':'0900'}},error='valid email'))
add('Bookings','Reject invalid room detail without leaving a booking row',step('POST',BOOK,status=400,body={'service_type':1,'room_details':{'room':9999,'check_in':'2030-01-01T12:00:00Z','check_out':'2030-01-02T12:00:00Z','num_guests':1,'room_count':1}},error='does not exist'))
add('Bookings','Reject nonexistent car without a partial booking insert',step('POST',BOOK,status=400,body={'service_type':2,'car_detail':{'car':9999}},error='Car not found'))
add('Bookings','Reject nonexistent activity date atomically',step('POST',BOOK,status=400,body={'service_type':4,'activity_date_detail':{'activity_date':9999,'adult_quantity_booking':1,'child_quantity_booking':0}},error='Activity date not found'))
add('Bookings','Persist PATCH and PUT prices on an existing booking',step('PATCH',BOOK+'1/',body={'total_price':120,'final_price':110},obj={'total_price':120,'final_price':110},db=change('bookings.Booking',rows=[row(1,total_price=120,final_price=110)])),step('PUT',BOOK+'1/',body={'service_type':1,'total_price':200,'final_price':180},obj={'final_price':180},db=change('bookings.Booking',rows=[row(1,total_price=200,final_price=180)])))
add('Bookings','Update guest fields while preserving the same guest row',step('PATCH',BOOK+'1/',body={'guest_info':{'full_name':'Updated Guest','email':'changed@example.com','phone':'0908888888'}},obj={'guest_info.email':'changed@example.com'},db=change('bookings.GuestInfo',rows=[row(1,booking_id=1,email='changed@example.com',full_name='Updated Guest')],allowed=['bookings.Booking'])))
add('Bookings','Ignore client attempts to overwrite read-only booking status',step('PATCH',BOOK+'1/',body={'status':4,'payment_status':2},obj={'status':1,'payment_status':1}))
add('Bookings','Delete booking and cascade its payment and guest',step('DELETE',BOOK+'1/',status=204,db=change('bookings.Booking',delta=-1,absent=[1],allowed=['payments.Payment','bookings.GuestInfo'])),step('GET',BOOK+'1/',status=404,error='No Booking matches'))
add('Bookings','Cancel pending booking with no completed payment',step('POST',BOOK+'1/cancel/',body={},fields={'booking_id':1,'status':'Cancelled','final_price':100},db=change('bookings.Booking',rows=[row(1,status=3,payment_status=4,final_price=100)],allowed=['payments.Payment'])))
add('Bookings','Reject cancellation of an already cancelled booking',step('POST',BOOK+'1/cancel/',body={},status=400,error='bị hủy'),profile=profile('bookings.Booking',status=3))
add('Bookings','Reject cancellation of a completed booking',step('POST',BOOK+'1/cancel/',body={},status=400,error='hoàn thành'),profile=profile('bookings.Booking',status=4))
add('Bookings','Reject rebooking before the old booking is cancelled',step('POST',BOOK+'1/rebook/',body={},status=400,error='đã hủy'))
add('Bookings','Rebook cancelled room stay and preserve original booking',step('POST',BOOK+'1/rebook/',status=201,body={'num_rooms':1},fields={'isSuccess':True},db=change('bookings.Booking',delta=1,rows=[row(4,status=1,payment_status=1)],allowed=['bookings.GuestInfo','rooms.RoomBookingDetail','rooms.Room','hotels.Hotel','payments.Payment'])),profile={'room_booking':True,'updates':[{'model':'bookings.Booking','id':1,'values':{'status':3}}]})
add('Bookings','List and filter refund policies',step('GET',BOOK+'refund-policies/',rows=[{'id':2,'name':'Policy 2'},{'id':1,'name':'Policy 1'}]),step('GET',BOOK+'refund-policies/?service_type=1',rows=[{'id':1,'service_type':1}]))
add('Bookings','Create and retrieve a refund policy',step('POST',BOOK+'refund-policies/',status=201,body={'service_type':1,'name':'API Policy','policy_type':2,'refund_percentage':50},obj={'name':'API Policy','refund_percentage':50},db=change('bookings.RefundPolicy',delta=1,rows=[row(3,name='API Policy',service_type=1,refund_percentage=50)])),step('GET',BOOK+'refund-policies/3/',obj={'id':3,'name':'API Policy'}))
add('Bookings','Persist PUT and PATCH refund-policy updates',step('PATCH',BOOK+'refund-policies/1/',body={'refund_percentage':25},obj={'refund_percentage':25},db=change('bookings.RefundPolicy',rows=[row(1,refund_percentage=25)])),step('PUT',BOOK+'refund-policies/1/',body={'service_type':1,'name':'Updated Policy','policy_type':2,'refund_percentage':30},obj={'name':'Updated Policy','refund_percentage':30},db=change('bookings.RefundPolicy',rows=[row(1,name='Updated Policy',refund_percentage=30)])))
add('Bookings','Delete refund policy without deleting its bookings',step('DELETE',BOOK+'refund-policies/1/',status=200,fields={'isSuccess':True},db=change('bookings.RefundPolicy',delta=-1,absent=[1])))
add('Bookings','Reject malformed JSON before creating a booking',step('POST',BOOK,status=400,raw='{"service_type":',error='JSON parse error'))

# Payments: list/detail/CRUD, checkout transport, capture and cash-state transitions.
add('Payments','List payment amounts and booking identities',step('GET',PAY+'payments/',rows=[{'id':2,'amount':200},PAY_ROW]))
add('Payments','Select payments by booking ID',step('GET',PAY+'?booking_id=1',rows=[PAY_ROW]))
add('Payments','Return no payment for a booking without payment',step('GET',PAY+'?booking_id=3',rows=[]))
add('Payments','Filter administrative payments by method',step('GET',PAY+'payments/?method=2',rows=[{'id':2,'method':2,'amount':200}]))
add('Payments','Paginate administrative payment list',step('GET',PAY+'payments/?pageSize=1&current=2',rows=[PAY_ROW],fields={'meta.totalItems':2}))
add('Payments','Retrieve payment via both detail routes',step('GET',PAY+'1/',obj=PAY_ROW),step('GET',PAY+'payments/1/',obj=PAY_ROW))
add('Payments','Reject missing payment ID',step('GET',PAY+'9999/',status=404,error='No Payment matches'))
add('Payments','Create online payment using the booking total by default',step('POST',PAY,status=201,body={'booking_id':3},obj={'booking.id':3,'amount':150,'method':1,'status':1},db=change('payments.Payment',delta=1,rows=[row(3,booking_id=3,amount=150,method=1,status=1)])))
add('Payments','Create cash payment with an explicit amount',step('POST',PAY,status=201,body={'booking_id':3,'amount':80,'method':2},obj={'amount':80,'method':2,'booking.id':3},db=change('payments.Payment',delta=1,rows=[row(3,amount=80,method=2,booking_id=3)])))
add('Payments','Reject payment creation without booking_id',step('POST',PAY,status=400,body={},error='booking_id is required'))
add('Payments','Reject a payment with nonexistent booking',step('POST',PAY,status=404,body={'booking_id':9999},error='Booking not found'))
add('Payments','Reject a duplicate payment for an already paid-linked booking',step('POST',PAY,status=400,body={'booking_id':1},error='Payment already exists'))
add('Payments','Create payment through the administrative serializer route',step('POST',PAY+'payments/create/',body={'booking':3,'amount':125.5,'method':1},obj={'booking':3,'amount':125.5},db=change('payments.Payment',delta=1,rows=[row(3,booking_id=3,amount=125.5,method=1)])))
add('Payments','Reject nonexistent administrative booking foreign key',step('POST',PAY+'payments/create/',status=400,body={'booking':9999,'amount':100,'method':1},error='does not exist'))
add('Payments','Persist payment updates through router and administrative routes',*[step(method,path,body={'amount':amount},obj={'amount':amount},db=change('payments.Payment',rows=[row(1,amount=amount)])) for method,path,amount in [('PATCH',PAY+'1/',125),('PUT',PAY+'1/',130),('PATCH',PAY+'payments/1/',135),('PUT',PAY+'payments/1/',140),('PATCH',PAY+'payments/1/update/',145),('PUT',PAY+'payments/1/update/',150)]])
add('Payments','Reject nonnumeric amount without overwriting payment',step('PATCH',PAY+'payments/1/update/',status=400,body={'amount':'bad'},error='valid number'))
add('Payments','Delete payment through router and both administrative routes',step('DELETE',PAY+'1/',status=204,db=change('payments.Payment',delta=-1,absent=[1])),step('DELETE',PAY+'payments/2/',status=204,db=change('payments.Payment',delta=-1,absent=[2])),step('POST',PAY+'payments/create/',body={'booking':3,'amount':20,'method':1},obj={'amount':20},db=change('payments.Payment',delta=1,rows=[row(3,amount=20)])),step('DELETE',PAY+'payments/3/delete/',status=200,fields={'isSuccess':True},db=change('payments.Payment',delta=-1,absent=[3])))
add('Payments','Require both checkout redirect URLs',step('POST',PAY+'1/pay/',status=400,body={},error='Both success_url and cancel_url are required.'))
add('Payments','Create checkout and persist only its transaction ID',step('POST',PAY+'1/pay/',body={'success_url':'https://example.test/success','cancel_url':'https://example.test/cancel'},fields={'checkout_session_id':'cs_api_test','checkout_url':'https://checkout.example.test/cs_api_test'},db=change('payments.Payment',rows=[row(1,transaction_id='cs_api_test',status=1)]),external={'operation':'checkout.create','argument_path':'line_items.0.price_data.unit_amount','value':100}))
add('Payments','Reject checkout for an already processed payment',step('POST',PAY+'1/pay/',status=400,body={'success_url':'https://example.test/success','cancel_url':'https://example.test/cancel'},error='Payment already processed'),profile=profile('payments.Payment',status=2))
add('Payments','Handle checkout transport failure without a transaction ID change',step('POST',PAY+'1/pay/',status=400,body={'success_url':'https://example.test/success','cancel_url':'https://example.test/cancel'},error='Test gateway unavailable'),stripe={'create_error':True})
add('Payments','Capture an unpaid gateway session with a failed payment transition',step('POST',PAY+'1/capture/',status=400,body={},error='not',db=change('payments.Payment',rows=[row(1,status=3)])),stripe={'payment_status':'unpaid'},profile={'room_booking':True})
add('Payments','Capture a paid session and persist the booking/payment states',step('POST',PAY+'1/capture/',body={},fields={'detail':'Payment completed successfully'},db=change('payments.Payment',rows=[row(1,status=2)],allowed=['bookings.Booking','notifications.Notification','rooms.Room','hotels.Hotel'])),stripe={'payment_status':'paid'},profile={'room_booking':True})
add('Payments','Reject cash confirmation for online payment',step('POST',PAY+'1/confirm_cash/',status=400,body={},error='This payment is not a cash payment.'))
add('Payments','Confirm cash booking while retaining its unpaid-on-arrival state',step('POST',PAY+'1/confirm_cash/',body={},fields={'success':True},db=change('payments.Payment',rows=[row(1,status=5)],allowed=['bookings.Booking','notifications.Notification'])),profile={'room_booking':True,'updates':[{'model':'payments.Payment','id':1,'values':{'method':2,'status':5}}]})
add('Payments','Reject cash confirmation for a missing payment',step('POST',PAY+'9999/confirm_cash/',status=404,body={},error='No Payment matches'))
add('Payments','Return overview totals without altering payment data',step('GET',PAY+'payments/overview/',fields={'isSuccess':True},obj={'total_revenue':300,'revenues':[300],'orders':[2],'customers':[2]}),oracle_note='Overview monetary totals must equal the independently seeded payment amounts (100 + 200).')
add('Payments','Reject malformed JWT on payment list',step('GET',PAY+'payments/',auth='invalid',status=401,error='token'))
add('Payments','Exclude unrelated services for flight-departure time filter',step('GET',PAY+'payments/?min_flight_leg_departure=2030-01-01',rows=[]))
add('Payments','Reject malformed administrative payment JSON',step('POST',PAY+'payments/create/',status=400,raw='{"booking":',error='JSON parse error'))

# Promotions: each service family has one multi-step persisted CRUD flow.
add('Promotions','List public campaigns with their exact campaign IDs',step('GET',PROMO,rows=[{'id':1,'title':'Summer'},{'id':2,'title':'Winter'}]))
add('Promotions','Filter public promotions by hotel type',step('GET',PROMO+'?promotion_type=1',rows=[{'id':1,'promotion_type':1}]))
add('Promotions','Retrieve a campaign with nested service promotions',step('GET',PROMO+'1/',obj={'id':1,'title':'Summer','discount_percent':10}))
add('Promotions','Create a public campaign and verify persisted dates/percent',step('POST',PROMO,status=201,body=NEW_PROMO,obj={'title':'API Campaign','discount_percent':15},db=change('promotions.Promotion',delta=1,rows=[row(3,title='API Campaign',discount_percent=15,promotion_type=1)])))
add('Promotions','Reject public campaign without title',step('POST',PROMO,status=400,body={key:value for key,value in NEW_PROMO.items() if key!='title'},error='This field is required.'))
add('Promotions','Filter administrative campaigns by title',step('GET',PROMO+'promotions-admin/?title=Summer',rows=[{'id':1,'title':'Summer'}]))
add('Promotions','Create a campaign through the administrative route',step('POST',PROMO+'promotions-admin/',status=201,body=NEW_PROMO,obj={'title':'API Campaign'},db=change('promotions.Promotion',delta=1,rows=[row(3,title='API Campaign',discount_percent=15)])))
add('Promotions','Reject a 256-character campaign title',step('POST',PROMO+'promotions-admin/',status=400,body={**NEW_PROMO,'title':'X'*256},error='255 characters'))
add('Promotions','Update campaign through detail and dedicated PUT/PATCH routes',*[step(method,path,body={**NEW_PROMO,'title':title},obj={'title':title},db=change('promotions.Promotion',rows=[row(1,title=title)])) for method,path,title in [('PATCH',PROMO+'1/','Detail PATCH'),('PUT',PROMO+'1/','Detail PUT'),('PATCH',PROMO+'promotions/1/update/','Alias PATCH'),('PUT',PROMO+'promotions/1/update/','Alias PUT')]])
PROMO_CASCADES=['promotions.RoomPromotion','promotions.CarPromotion','promotions.FlightPromotion','promotions.ActivityPromotion']
add('Promotions','Delete a campaign and all service links through dedicated route',step('DELETE',PROMO+'promotions/1/delete/',status=200,fields={'isSuccess':True},db=change('promotions.Promotion',delta=-1,absent=[1],allowed=PROMO_CASCADES)))
add('Promotions','Delete a campaign through its detail route',step('DELETE',PROMO+'1/',status=204,db=change('promotions.Promotion',delta=-1,absent=[1],allowed=PROMO_CASCADES)))
add('Promotions','Create hotel campaign details with an explicit room discount',step('POST',PROMO+'create-details/',status=201,body={**NEW_PROMO,'type':'hotel','rooms':[{'id':1,'discount_percent':25,'discount_amount':0}]},fields={'data.promotion_id':3,'data.type':'hotel','data.rooms.0.id':1},db=change('promotions.RoomPromotion',delta=1,rows=[row(3,promotion_id=3,room_id=1,discount_percent=25)],allowed=['promotions.Promotion'])))
add('Promotions','Reject invalid room in campaign details without partial links',step('POST',PROMO+'create-details/',status=400,body={**NEW_PROMO,'type':'hotel','rooms':[{'id':9999}]},error='9999'))

def service_crud(service, model_name, foreign_key, *, base_id):
    """Exercise create aliases, both update aliases, reads and both delete aliases."""
    base = PROMO+service+'-promotions/'
    model = 'promotions.'+model_name
    payload = {'promotion':1,foreign_key:1,'discount_percent':12,'discount_amount':0}
    operations = [
        step('POST',base+'create/',status=200,body=payload,obj={'discount_percent':12},db=change(model,delta=1,rows=[row(3,promotion_id=1,**{foreign_key+'_id':1},discount_percent=12)])),
        step('GET',base+'3/',obj={'id':3,'discount_percent':12}),
    ]
    for method, suffix, percent in [('PATCH','',16),('PUT','',18),('PATCH','update/',20),('PUT','update/',22)]:
        operations.append(step(method,base+'3/'+suffix,body={'discount_percent':percent},obj={'discount_percent':percent},db=change(model,rows=[row(3,discount_percent=percent)])))
    operations += [step('DELETE',base+'3/',status=204,db=change(model,delta=-1,absent=[3])),
                   step('DELETE',base+'2/delete/',status=200,fields={'isSuccess':True},db=change(model,delta=-1,absent=[2])),
                   step('POST',base,status=201,body=payload,obj={'discount_percent':12},db=change(model,delta=1,rows=[row(4,promotion_id=1,**{foreign_key+'_id':1},discount_percent=12)]))]
    return operations

for service, model_name, foreign_key in [('room','RoomPromotion','room'),('car','CarPromotion','car'),('flight','FlightPromotion','flight'),('activity','ActivityPromotion','activity_date')]:
    base = PROMO+service+'-promotions/'
    add('Promotions',f'List {service} campaign links with exact discount values',step('GET',base,rows=[{'id':1,'discount_percent':5},{'id':2,'discount_percent':10}]))
    add('Promotions',f'Persist full {service} campaign-link lifecycle across exposed routes',*service_crud(service,model_name,foreign_key,base_id=1))
    add('Promotions',f'Reject nonexistent {service} foreign key before link insertion',step('POST',base+'create/',status=400,body={'promotion':1,foreign_key:9999},error='does not exist'))

add('Promotions','Bulk create activity links with exact related IDs and discount',step('POST',PROMO+'activity-promotions/create/bulk/',status=201,body={'items':[{'promotion_id':1,'activity_date_id':1,'discount_percent':30,'discount_amount':0},{'promotion_id':1,'activity_date_id':2,'discount_percent':30,'discount_amount':0}]},fields={'isSuccess':True},db=change('promotions.ActivityPromotion',delta=2,rows=[row(3,promotion_id=1,activity_date_id=1,discount_percent=30),row(4,promotion_id=1,activity_date_id=2,discount_percent=30)])))
add('Promotions','Bulk delete selected activity links only',step('DELETE',PROMO+'activity-promotions/bulk-delete/',body={'ids':[1,2]},fields={'isSuccess':True},db=change('promotions.ActivityPromotion',delta=-2,absent=[1,2])))
add('Promotions','Reject unknown promotion type before campaign insertion',step('POST',PROMO+'promotions-admin/',status=400,body={**NEW_PROMO,'promotion_type':99},error='not a valid choice'))
add('Promotions','Exclude campaigns with an end date before requested minimum',step('GET',PROMO+'promotions-admin/?min_date=2040-01-01',rows=[]))
add('Promotions','Reject a missing campaign resource',step('GET',PROMO+'9999/',status=404,error='No Promotion matches'))

if __name__ == '__main__':
    from collections import Counter
    from enrich_contracts import enrich
    enrich(CASES)
    counts = Counter(case['module'] for case in CASES)
    assert counts == {module:30 for module in PREFIXES}, counts
    assert len({case['id'] for case in CASES}) == 150
    target = Path(__file__).parent/'cases.json'
    target.write_text(json.dumps(CASES,indent=2,ensure_ascii=True),encoding='utf8')
    print(json.dumps({'cases':len(CASES),'module_counts':counts,'API_steps':sum(len(case['steps']) for case in CASES)},indent=2))
