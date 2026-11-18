"""Case-specific expected outputs declared before execution, in English.

HTTP/read helpers can further specialize these descriptions with concrete
fixture IDs and field dictionaries. No expectation is copied from actual output.
"""

import json


def expected_output_for(case_item):
    """Return a checkable output description for every parameterized test family."""
    marker = case_item.get_closest_marker("case")
    if marker is None:
        return None
    arguments = getattr(case_item, "callspec", None)
    values = arguments.params if arguments else {}
    case_id = arguments.id if arguments else case_item.name
    function_name = case_item.originalname or case_item.name.split("[")[0]
    original = marker.kwargs.get("expected")
    value = lambda key, default=None: values.get(key, default)
    if function_name == "test_hotel_persistence_and_recommendation_rules":
        outputs = {
            "H-M01": 'Reloaded Hotel.name and str(hotel) both equal "Lotus Hotel"; the saved hotel ID exists in the database.',
            "H-M02": "Return sentiment_score=0.0 when all sentiment counts are zero; evaluation does not write any hotel field.",
            "H-M03": "Return sentiment_score=(5-2)/(5+2+2+1)=0.3; the calculation does not change stored counters.",
            "H-M04": "Return click_score=ln(1+9)=2.302585092994046, within floating-point tolerance; no database field is changed.",
            "H-M05": "Persist total_weighted_score=0.6*4+0.3*ln(10)+0.1*0.3=3.120775527898214; refresh_from_db returns the same score.",
            "H-M06": "Persist total_weighted_score=0.6*3+0.3*ln(10)+0.1*0.3=2.520775527898214 after explicit refresh; the other hotel fields are preserved.",
            "H-M07": "After the sole room has available_rooms=0, reloading its hotel returns min_price=0; the room is persisted as unavailable.",
            "H-M08": "Exclude the unavailable room priced at 500; the hotel reloaded from DB has min_price=100 from its available room.",
            "H-M09": "Available nightly prices 100 and 300 produce persisted min_price=100, the minimum rather than the average. This minimum-price interpretation requires product confirmation.",
            "H-M10": 'Return the exact label "Image for Lotus Hotel" for a persisted HotelImage linked to the fixture hotel.',
            "H-M11": "Persist UserHotelInteraction.weighted_score=0.7*(2/5)+0.3*ln(5)=0.762831373730230; reload confirms the same user/hotel relation and score.",
            "H-M12": 'The interaction label contains both "tester" and "Lotus Hotel"; rendering the label does not create or update any row.',
            "H-M13": "If score calculation raises ValueError, hotel.save() persists total_weighted_score=0.0; reloading confirms the fallback.",
            "H-M14": "Duplicate (user, hotel) insertion raises IntegrityError; exactly one original interaction remains after the inner savepoint rollback.",
        }
        return outputs[case_id]
    if function_name == "test_room_inventory_availability_and_promotions":
        outputs = {
            "R-M01": "Return capacity=2 adults+1 child=3; computing this property leaves all room database fields unchanged.",
            "R-M02": "Persist available_rooms=0 and available=False; refresh_from_db confirms both inventory and availability.",
            "R-M03": "An end_date before today persists available=False; no unrelated room field changes.",
            "R-M04": "With end_date=today and available_rooms=10, persist available=True; the end date is inclusive.",
            "R-M05": "Decreasing inventory 10 by 20 persists available_rooms=0 rather than a negative number, and available=False.",
            "R-M06": "Calling decrease_available_rooms() without a quantity persists available_rooms=9 from the original 10.",
            "R-M07": "The deleted room ID no longer exists; its hotel remains and refresh_from_db returns min_price=0.",
            "R-M08": "A room with hotel=None can be persisted, then deleted; a fresh query finds no row for its saved ID.",
            "R-M09": 'Return exact labels "Lotus Hotel - Deluxe", "Image for Deluxe in Lotus Hotel", and "WiFi (Deluxe)" without additional DB writes.',
            "R-M10": "Return None because the room has no linked campaign; the room and campaign tables remain unchanged.",
            "R-M11": "Return None for the linked inactive campaign; do not change campaign status or room inventory.",
            "R-M12": "Return None when the linked campaign starts tomorrow; the future campaign must not apply today.",
            "R-M13": "Return None when the linked campaign ended yesterday; the expired campaign must not apply today.",
            "R-M14": "Return a promotion dictionary with the fixture campaign ID/title, discount_percent=10, discount_amount=0 and its start/end timestamps; child override 0 falls back to campaign values.",
            "R-M15": "Return the linked campaign dictionary with effective discount_percent=20 from the room override; preserve the campaign-level 10% value in DB.",
            "R-M16": "Select the campaign whose effective fallback discount is 40%, not the competing 20% override; returned campaign ID and title identify the 40% campaign.",
        }
        return outputs[case_id]
    if function_name == "test_room_price_and_booking_sync":
        total = value("total")
        discount = value("discount")
        count = value("count")
        return f'Persist detail.total_price={total}, discount_amount={discount}, final_price={total-discount}; parent Booking stores the same three values. room_type="Deluxe" and owner_hotel=fixture owner. Room inventory changes 10 -> {10-count} on insertion and remains {10-count} after saving the same detail again.'
    if function_name == "test_booking_identifiers_and_referential_integrity":
        return {
            "B-M01": "Persist a nonempty booking_code matching ^AGD[0-9A-F]{6}$; the new Booking row can be retrieved using its generated code.",
            "B-M02": 'Two successive saves preserve the explicit booking_code="CUSTOM"; refresh_from_db returns "CUSTOM".',
            "B-M03": 'The saved GuestInfo is linked to the fixture booking; str(guest)="Alice" and str(booking) contains its booking_code.',
            "B-M04": "Deleting the booking removes the Booking, its GuestInfo and associated Payment rows; queries for those booking-linked records return no rows.",
            "B-M05": "Deleting the referenced user preserves the booking and sets its persisted user_id to NULL.",
            "B-M06": 'Return the exact policy label "Standard - Hotel" for service_type=1; formatting the policy does not write to DB.',
            "B-M07": "A second Booking with the same booking_code raises IntegrityError; exactly one original booking retains that code.",
        }[case_id]
    if function_name == "test_payment_amount_and_booking_persistence":
        return "Reloaded Payment.amount=125.5, method=1 and booking_id=fixture Booking.id; changing amount must preserve the original booking foreign key."
    if function_name == "test_promotion_model_labels":
        return 'Return campaign title "Summer" with its type label; room link="Summer -> Room: Deluxe"; null flight/car links end in "N/A"; flight ID 8 and car "Sedan" appear when supplied; activity-date ID 9 appears in its label.'
    if function_name == "test_room_booking_validation":
        if value("valid"):
            return f'Validation succeeds with errors={{}}. validated_data contains the selected Room, num_guests={value("guests")}, room_count={value("count")} and the supplied future check-in/check-out. Validation alone inserts/updates no DB rows.'
        messages = {
            "R-V02": "Check-out must be after check-in",
            "R-V03": "Check-out must be after check-in",
            "R-V04": "Check-in cannot be in the past",
            "R-V05": "Number of guests (4) exceeds room capacity (3)",
            "R-V06": "Only 10 rooms available",
            "R-V07": "Guest count must be positive",
            "R-V08": "Guest count must be positive",
            "R-V09": "Room count must be positive",
        }
        return f'Validation fails with a non_field_errors validation message describing "{messages[case_id]}"; no RoomBookingDetail is created and all persisted data remains unchanged.'
    if function_name == "test_hotel_serializers":
        return {
            "H-S01": "Serialized hotel.thumbnail is JSON null when no image row exists; other persisted hotel fields are preserved.",
            "H-S02": 'Serialized hotel.thumbnail equals the exact first stored image string "first.png".',
            "H-S03": "Serialized hotel.owner is JSON null when the supplied hotel instance has no owner.",
            "H-S04": 'Serialized owner is an object with username="tester" and id=fixture owner ID; the owner relation is not changed.',
            "H-S05": 'Serializer validation has errors={}; saving creates a Hotel named "New Hotel" with city_id=fixture city ID, and a fresh DB query confirms both values.',
        }[case_id]
    if function_name == "test_room_creation_serializers":
        return {
            "R-S01": 'Persist a Twin room linked to the fixture hotel, start_date=today and end_date=today+365 days. Exactly the two amenities "WiFi" and "Pool" are linked to the new room; promotion=null and has_promotion=False.',
            "R-S02": 'Persist the supplied start_date=today+1 and end_date=today+8 without substituting defaults; the new room has exactly amenities {"WiFi","Pool"}.',
            "R-S03": "Serialized Room.promotion is JSON null and has_promotion=False for a room with no linked campaign; no DB write occurs.",
            "R-S04": "Serialized Room.promotion contains the linked campaign ID and discount_percent=10; has_promotion=True and the underlying DB rows remain unchanged.",
        }[case_id]
    if function_name == "test_booking_serializers":
        return {
            "B-S01": 'Create one Booking with user_id=NULL and one linked GuestInfo: full_name="Alice", email="alice@example.com", phone="123".',
            "B-S02": "Create one Booking whose persisted user_id equals the authenticated fixture user ID; no guest row is inserted unless supplied.",
            "B-S03": "Create one Booking with service_type=1 and user_id=NULL; no GuestInfo is created.",
            "B-S04": 'Persist total_price=250 on the original booking; update the existing guest to "Updated Alice" while preserving its guest ID and booking FK.',
            "B-S05": 'Persist total_price=250; create exactly one missing GuestInfo linked to that booking with full_name="Updated Alice".',
            "B-S06": "Persist total_price=250 on the same booking ID; leave GuestInfo absent and retain all other booking values.",
        }[case_id]
    if function_name == "test_booking_representation":
        field = value("field")
        return (
            f'Return the booking dictionary with id=fixture booking ID and service_type={value("service")}. '
            + (
                f'Keep only detail field "{field}" and remove the three unrelated service detail fields; empty references yield null and nonexistent references yield [].'
                if field
                else "For service type 5, keep all four detail fields with null values; do not write any database rows."
            )
        )
    if function_name == "test_payment_serializers":
        return "Serialized payment.booking.id equals the fixture booking ID. Valid input creates one additional Payment with amount=150, method=1 and booking_id equal to that same existing booking; reloading confirms the values."
    if function_name == "test_promotion_create_validation":
        kind = value("kind")
        key = value("key")
        return (
            f'Validation succeeds with errors={{}}; validated_data.type="{kind}" and {key}=[{{"id":1}}]; no campaign or link is inserted by validation alone.'
            if value("present")
            else f'Validation fails with non_field_errors containing "{key} is required for {kind} promotion"; no campaign or link rows are inserted.'
        )
    if function_name == "test_promotion_representation":
        field = value("field")
        return (
            f'Return id=fixture campaign ID, title="Summer", discount_percent=10 and promotion_type={value("kind")}. '
            + (
                f'Keep only the "{field}" link collection; remove the other three service link collections.'
                if field
                else "For the unknown type 99, retain all four service link collections."
            )
            + " No persisted values change."
        )
    if function_name == "test_effective_discounts":
        return "For Room, Car, Flight and Activity promotion serializers: child values 0 use campaign fallback percent=10 and amount=30; explicit child values 25 yield percent=25 and amount=25. These methods perform no writes."
    if function_name == "test_refund_policy_decisions":
        return f'Return refund_amount={value("expected")} for final_price=100, policy_type={value("kind")}, refund_percentage={value("percent")} and fixed refund_amount={value("amount")}; no payment or booking row is updated by calculation.'
    if function_name == "test_datetime_conversion":
        return f'Return {value("expected")!r} with the corresponding None/date-converted-datetime/unchanged-value type. A date becomes midnight 00:00:00; an existing datetime keeps its time; the helper writes no DB rows.'
    if function_name == "test_refund_gateway":
        return {
            "online_ok": 'Return gateway refund object id="re_unit". Call Stripe once with payment_intent="pi_unit" and amount=20 VND, not 2000; no booking/payment field is changed.',
            "online_error": "Return None after the mocked gateway raises RuntimeError; the existing successful payment and booking remain unchanged.",
            "unpaid": "Return None and call Stripe zero times because the payment is pending; all persisted fields remain unchanged.",
            "cash": "Return None and call Stripe zero times because method=CASH; all persisted payment and booking fields remain unchanged.",
        }[value("scenario")]
    if function_name == "test_cancel_booking":
        if value("expected_code") != 200:
            return f'HTTP 400 with a cancellation-not-allowed error. Booking.status remains {value("status")}; every payment, booking field and related row equals its pre-request value.'
        refund = 100 if value("policy") == 1 else 0
        return f'HTTP 200 with booking_id=fixture ID, status="Cancelled", refund_amount={refund} and unchanged final_price=100. Persist Booking.status=3; payment_status={7 if refund else 4}; related payments have the same refund/cancelled state.'
    if function_name == "test_payment_lifecycle":
        mode = value("mode")
        if mode == "unpaid":
            return "HTTP 400 with a payment-not-completed error; persist Payment.status=3 (FAILED), preserve Booking.status/payment_status as pending and send the failure notification through the isolated notification boundary."
        return (
            f'HTTP 200. Persist Payment.status={5 if mode=="cash" else 2} ({"UNPAID" if mode=="cash" else "SUCCESS"}), Booking.status=2 (CONFIRMED), Booking.payment_status={5 if mode=="cash" else 6}; preserve amounts and service links. '
            + (
                "Notification calls=0 when neither user nor guest has an email."
                if mode == "no_email"
                else 'Notifications reference the fixture booking/service; online confirmation returns detail="Payment completed successfully".'
            )
        )
    if function_name == "test_reject_cash_on_online":
        return 'HTTP 400 with detail="This payment is not a cash payment." Payment.status stays 1 (PENDING); booking fields, amount and transaction ID remain unchanged.'
    if function_name == "test_payment_overview_totals":
        return f'HTTP 200. For statistic_by="{value("period")}", return exactly two period labels with revenues=[100,200], total_revenue=300 and equal label/revenue/customer/order series lengths. The GET operation changes no DB field.'
    if function_name == "test_create_service_booking":
        return f'HTTP 201 with booking_id and a new AGD booking_code. Persist one Booking with service_type={value("kind")}, user_id=fixture user and one linked service-detail row; service_ref_ids=[that detail ID]. Return the same detail ID and submitted room/car/flight/activity values in data.'
    if function_name == "test_invalid_service_booking_atomicity":
        return f'HTTP 400 with a validation message for {value("scenario")}. Booking count is unchanged; no orphan Booking or service-detail row remains; existing service capacity, driver status and every original field are preserved.'
    if function_name == "test_rebook_service":
        return f'HTTP 201. Return distinct old_booking_id/new_booking_id and booking codes. Persist a new pending Booking for service_type={value("kind")}, cloned service-detail values and guest name="Alice"; mark the old booking and its payment REBOOKED without duplicating the original guest row.'
    if function_name == "test_rebook_pending_rejected":
        return "HTTP 400 indicating that only cancelled bookings can be rebooked. No new Booking, GuestInfo or service-detail row is inserted; all original fields remain unchanged."
    if function_name == "test_create_campaign":
        if value("scenario") == "missing_target":
            return "HTTP 400 with an error identifying target ID 999999. No campaign or service-link row is retained; every original DB row and field remains unchanged."
        percent = (
            25
            if value("scenario") == "override"
            else 0 if value("scenario") == "optional_discounts" else 10
        )
        amount = (
            40
            if value("scenario") == "override"
            else 0 if value("scenario") == "optional_discounts" else 30
        )
        return f'HTTP 201. Persist one campaign titled "Campaign created by test" with type="{value("kind")}" and one link to the selected real service ID. Effective link discount_percent={percent}, discount_amount={amount}; omitted optional discounts default to 0. Return the saved campaign ID and exact link values.'
    if function_name == "test_bulk_activity_promotions":
        scenario = value("scenario")
        if scenario == "create":
            return "HTTP 201 with data.created_count=1. Persist one ActivityPromotion linked to the supplied promotion_id/activity_date_id with discount_percent=15; no other rows change."
        if scenario == "delete":
            return "HTTP 200 with data.deleted_count=1. The selected ActivityPromotion ID is absent from a new DB query; its campaign and activity date remain unchanged."
        return f"HTTP 400 with a nonempty-list or missing-field error for {scenario}. No ActivityPromotion is inserted/deleted, and the complete pre-request DB snapshot is preserved."
    if function_name == "test_campaign_grouping":
        return (
            "HTTP 200. data.hotels=[] because the city filter does not match; parent campaign data is still returned."
            if value("city_filter") == "other"
            else "HTTP 200. Group duplicate links into exactly one parent hotel/activity object; its ID equals the fixture parent ID and max_discount/discount=20, the greater linked discount."
        ) + " All campaign, link and service rows remain unchanged."
    if function_name == "test_hotel_interactions":
        scenario = value("scenario")
        if scenario in ("create", "update"):
            return "HTTP 200. Exactly one user/hotel interaction stores clicks=4, positive=2, negative=1, neutral=1 and weighted_score=0.7*(1/5)+0.3*ln(5). Persist matching hotel aggregate counters; updating preserves the interaction ID."
        if scenario == "detail":
            return "HTTP 200. Return the persisted interaction for the fixture user/hotel, including click_count=1 and the same relation IDs; no DB writes occur."
        return f'HTTP {401 if "anonymous" in scenario else 404 if scenario=="detail_missing" else 400} with an authentication/missing-hotel/not-found error appropriate to {scenario}; create no interaction and change no hotel counters.'
    if function_name == "test_hotel_pagination_request_isolation":
        return "After request 1 uses cityId=99999 and request 2 supplies no filter, the second paginator.filters dictionary contains no city_id entry. Request-specific filters must not leak between instances."
    if function_name == "test_image_delete":
        return (
            "HTTP 204 with no response body. Delete the selected image row; preserve its parent hotel/room. "
            + (
                "The mocked filesystem remove operation is called once because the file exists."
                if value("exists")
                else "The filesystem remove operation is never called because the file does not exist."
            )
        )
    if function_name == "test_room_overlap":
        return (
            "Validation succeeds with errors={}; the cancelled 8-room booking is ignored, so requesting 3 of 10 rooms is permitted."
            if value("cancelled")
            else 'Validation fails with non_field_errors="Room not available for selected dates" because existing quantity 8 + requested quantity 3 exceeds total_rooms=10.'
        ) + " Validation inserts no detail row and changes no inventory."
    if function_name == "test_hotel_image_updates":
        return (
            'HTTP 400 with a name validation error; image rows remain exactly ["old.png"] and every hotel field is unchanged.'
            if value("scenario") == "invalid_update"
            else 'HTTP 200. The created/updated hotel has name="New Hotel", the selected city ID and exactly image strings {"new1.png","new2.png"}; replacement removes the old image row.'
        )
    if function_name == "test_cancel_service_resources":
        return (
            f"HTTP 200. Persist Booking.status=3 (CANCELLED); keep the original final price. "
            + (
                'Restore driver_status="idle" on the referenced user.'
                if value("kind") == 2
                else (
                    "Restore ActivityDate.participants_available=20."
                    if value("kind") == 4
                    else "Persist Booking.payment_status=7 (REFUNDED), refund_amount=100 and mark its payment REFUNDED."
                )
            )
        )
    if function_name == "test_flight_payment_itineraries":
        return f'HTTP 200 with a confirmation response for itinerary="{value("graph")}". Persist Payment.status={5 if value("mode")=="cash" else 2}, Booking.status=2 and matching payment state; preserve booking/service IDs. Missing itinerary data is handled without an exception or None response.'
    if function_name == "test_flight_promotion_filters":
        return (
            "Return None and omit the flight because its route/airline/date does not satisfy the supplied filter."
            if value("filtered")
            else 'Return exactly {"id":9}; remove internal discount_percent and discount_amount fields after the route/airline/date filter matches.'
        ) + " No flight or promotion DB fields change."
    if function_name == "test_activity_promotion_filter_contract":
        return (
            (
                "Return None for the activity interface that fails the supplied city/category/rating/price/date/search filter."
                if value("filtered")
                else 'Return exactly {"id":9}; the activity interface matches the filter and the internal some_internal_field key is removed.'
            )
            + " Parent representation is mocked; this is separate from the real-model contract case."
        )
    if function_name == "test_actual_activity_promotion_contract":
        return "Return a non-null dictionary for the real persisted ActivityPromotion, including its id, campaign ID and activity_date ID. A valid activity_date relation must not be silently discarded by looking for an unrelated activity attribute."
    if function_name == "test_campaign_partial_success":
        return "HTTP 201. Return one successful room link plus exactly one per-item error for unknown room ID 999999; persist exactly one RoomPromotion linked to the returned campaign_id."
    if function_name == "test_refund_missing_time":
        return "Return refund_amount=100, equal to final_price, when the booking start timestamp is absent even though a 25% partial-refund policy exists. Calculation alone changes no persisted row."
    if function_name == "test_payment_checkout":
        scenario = value("scenario")
        if scenario == "checkout_ok":
            return 'HTTP 200 with checkout_session_id="cs_unit_test" and checkout_url="http://localhost/checkout". Stripe receives currency="vnd", unit_amount=100 and the supplied redirect URLs; persisted transaction_id="cs_unit_test" and the payment amount is unchanged.'
        if scenario == "checkout_error":
            return 'HTTP 400 with detail="Gateway unavailable"; the mocked Stripe exception leaves persisted transaction_id=NULL and preserves the payment amount, status and booking fields.'
        if scenario == "missing_urls":
            return 'HTTP 400 with detail="Both success_url and cancel_url are required." Call Stripe zero times; preserve every payment and booking field.'
        if scenario.startswith("processed"):
            return 'HTTP 400 with detail="Payment already processed". No Stripe session is created; the existing processed payment status and transaction ID remain unchanged.'
        return {
            "missing_booking": 'HTTP 400 with detail="booking_id is required"; insert no payment and preserve all original DB fields.',
            "unknown_booking": 'HTTP 404 with detail="Booking not found" for ID 999999; insert no payment or booking.',
            "duplicate_booking": 'HTTP 400 with detail="Payment already exists for this booking"; retain exactly the original payment and its fields.',
            "tampered_amount": "HTTP 400 rejecting amount=1 for a booking priced at 100; create no payment and preserve the booking amount/state.",
        }[scenario]
    if function_name == "test_payment_email":
        return f'Return email={ {"user":"guest@example.com","guest":"alice@example.com","none":None}[value("kind")]!r}; prefer the stored user email, then guest email, and return None only if neither is available. Resolution writes no DB rows.'
    # GET/CRUD cases specialize this before their actual HTTP call. This fallback
    # is retained only if arranging the fixtures itself fails before that call.
    return f"Expected unit result: {original!s}. Output fields and any affected row identities must match the stated fixture values; a read must preserve all stored fields. The HTTP helper declares exact IDs/values before dispatch."
