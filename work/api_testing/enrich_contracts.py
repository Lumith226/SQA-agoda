"""Add computed/domain DB fields to the declared case metadata before execution.

These formulas use fixture/input values, never observed API responses.
"""
import math

def table(delta=0, rows=None, absent=None):
    """Declare row-count, field-value and removal assertions for one table."""
    return {'delta':delta,'rows':rows or [],'absent':absent or [],'preserve':[]}

def record(record_id, **fields):
    """Describe persisted fields independently of application responses."""
    return {'id':record_id,'fields':fields}

def enrich(cases):
    """Complete derived-value and related-row contracts for stateful operations."""
    indexed={case['id']:case for case in cases}
    indexed['API-B-018']['steps'][0]['expect']['database']['tables']['bookings.GuestInfo']['rows'][0]['fields']['phone']='0908888888'
    indexed['API-B-028']['steps'][1]['expect']['database']['tables']['bookings.RefundPolicy']['rows'][0]['fields']['policy_type']=2
    # A zero-refund cancellation requires an actual future stay and a NO_REFUND
    # policy; without a service start time the source explicitly returns 100%.
    cancellation=indexed['API-B-021']
    cancellation['profile']={'room_booking':True,'updates':[{'model':'bookings.RefundPolicy','id':1,'values':{'policy_type':3}}]}
    cancellation['steps'][0]['expect']['root_fields']['final_price']=95
    cancellation['steps'][0]['expect']['database']['tables']['bookings.Booking']['rows'][0]['fields']['final_price']=95
    rebooking=indexed['API-B-025']
    rebooking['objective']='Rebook a cancelled stay, mark the old booking rebooked and preserve its prices'
    rebooking['steps'][0]['expect']['database']['tables']['bookings.Booking']['rows'] += [
        {'id':1,'fields':{'status':5,'payment_status':8,'total_price':100,'final_price':95}},
    ]
    for operation in indexed['API-P-015']['steps']:
        if operation['method']=='PUT':
            operation['body']['method']=1
    # A full campaign update explicitly supplies required dates and discounts.
    for operation in indexed['API-PR-009']['steps']:
        operation['expect']['database']['tables']['promotions.Promotion']['rows'][0]['fields'].update(
            discount_percent=15,start_date='2030-01-01T00:00:00Z',end_date='2030-02-01T00:00:00Z')
    operation=indexed['API-H-029']['steps'][0]
    operation['expect']['database']['tables']['hotels.UserHotelInteraction']['rows'][0]['fields']['weighted_score']=0.7*(2-1)/(2+1+0+1)+0.3*math.log(1+4)
    operation['expect']['database']['tables']['hotels.Hotel']={
        'delta':0,'rows':[{'id':1,'fields':{'total_click':4,'total_positive':2,'total_negative':1,'total_neutral':0,
            'total_weighted_score':0.6*4+0.3*math.log(5)+0.1*(2-1)/(2+1+0+1)}}], 'absent':[], 'preserve':[]}
    for case_id,status in [('API-P-023',6),('API-P-025',5)]:
        database=indexed[case_id]['steps'][0]['expect']['database']
        database['tables']['bookings.Booking']={'delta':0,'rows':[{'id':1,'fields':{'status':2,'payment_status':status}}], 'absent':[], 'preserve':[]}
    # create-details creates a fresh campaign together with its room link.
    indexed['API-PR-012']['steps'][0]['expect']['database']['tables']['promotions.Promotion']={
        'delta':1,'rows':[{'id':3,'fields':{'title':'API Campaign','discount_percent':15,'promotion_type':1}}], 'absent':[], 'preserve':[]}
    # Verify dependent rows as well as the directly addressed resource.
    def extend(case_id, step_index, tables):
        database=indexed[case_id]['steps'][step_index]['expect']['database']
        database['tables'].update(tables)
        database['allowed_models']=sorted(set(database['allowed_models']) | set(tables))

    extend('API-H-012',0,{'hotels.HotelImage':table(1,[record(3,hotel_id=3,image='/media/new-hotel.png')])})
    extend('API-H-020',0,{'hotels.HotelImage':table(0,[record(3,hotel_id=1,image='/media/replaced.png')],[1])})
    extend('API-H-020',1,{'hotels.HotelImage':table(-1,absent=[3])})
    for case_id in ['API-H-023','API-H-024']:
        extend(case_id,0,{label:table(-1,absent=[1]) for label in [
            'hotels.HotelImage','hotels.UserHotelInteraction','rooms.Room','rooms.RoomImage','rooms.RoomAmenity','promotions.RoomPromotion']})
    extend('API-R-014',0,{'hotels.Hotel':table(rows=[record(1,min_price=150)])})
    extend('API-R-019',0,{'rooms.RoomImage':table(-1,absent=[1]),'hotels.Hotel':table(rows=[record(1,min_price=100)])})
    extend('API-R-019',1,{'rooms.RoomImage':table(),'hotels.Hotel':table(rows=[record(1,min_price=125)])})
    extend('API-R-021',0,{**{label:table(-1,absent=[1]) for label in ['rooms.RoomImage','rooms.RoomAmenity','promotions.RoomPromotion']},
        'hotels.Hotel':table(rows=[record(1,min_price=0)])})
    for case_id,email,name in [('API-B-009','api@example.com','API Guest'),('API-B-010','anon@example.com','Anonymous Guest')]:
        extend(case_id,0,{'bookings.GuestInfo':table(1,[record(3,booking_id=4,full_name=name,email=email)])})
    extend('API-B-020',0,{label:table(-1,absent=[1]) for label in ['payments.Payment','bookings.GuestInfo']})
    extend('API-B-021',0,{'payments.Payment':table(rows=[record(1,status=4)])})
    extend('API-B-025',0,{
        'bookings.GuestInfo':table(1,[record(3,booking_id=4,full_name='Guest 1',email='guest1@example.com',phone='0900000001')]),
        'rooms.RoomBookingDetail':table(1,[record(2,booking_id=4,room_id=1,room_count=1,total_price=100,discount_amount=5,final_price=95)]),
        'rooms.Room':table(rows=[record(1,available_rooms=8)]),
        'payments.Payment':table(rows=[record(1,status=8)]),
    })
    extend('API-P-022',0,{'notifications.Notification':table(1,[record(1,user_id=1,email='owner1@example.com',is_error=True)])})
    extend('API-P-023',0,{'notifications.Notification':table(2,[
        record(1,user_id=1,email='owner1@example.com',link='/profile/hotel',is_error=False),
        record(2,user_id=1,email='owner1@example.com',link='/room-payment',is_error=False)])})
    extend('API-P-025',0,{'notifications.Notification':table(1,[record(1,user_id=1,email='owner1@example.com',link='/profile/hotel',is_error=False)])})
    for case_id in ['API-PR-010','API-PR-011']:
        extend(case_id,0,{label:table(-1,absent=[1]) for label in [
            'promotions.RoomPromotion','promotions.CarPromotion','promotions.FlightPromotion','promotions.ActivityPromotion']})
    # Every permitted model now has explicit checks. Unused permissions become
    # full non-mutation comparisons, preventing unverified dependent writes.
    for case in cases:
        for operation in case['steps']:
            database=operation['expect']['database']
            if not database['unchanged']:
                for label in database['allowed_models']:
                    database['tables'].setdefault(label,table())
    return cases
