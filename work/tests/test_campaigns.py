"""Promotion campaign creation and bulk operations on real related records."""

from datetime import timedelta
import pytest
from promotions import views as promotion_views
from promotions.models import (
    Promotion,
    RoomPromotion,
    CarPromotion,
    FlightPromotion,
    ActivityPromotion,
)
from test_views import request_view
from test_lifecycle import mark


@pytest.mark.parametrize(
    "case_id,kind,scenario",
    [
        pytest.param(
            f"PR-C{case_index:02}",
            kind,
            scenario,
            id=f"PR-C{case_index:02}",
            marks=mark(
                f"PR-C{case_index:02}",
                "Promotions",
                "Create campaign and its service-specific discount links",
                f"type={kind}; scenario={scenario}",
                "Valid campaign persists exact link and discount; invalid links rejected without orphan campaign",
                "promotions/views.py:PromotionCreateView.create",
            ),
        )
        for case_index, (kind, scenario) in enumerate(
            [
                (field_name, scenario)
                for field_name in ["hotel", "flight", "activity", "car"]
                for scenario in [
                    "fallback",
                    "override",
                    "missing_target",
                    "optional_discounts",
                ]
            ],
            1,
        )
    ],
)
def test_create_campaign(
    case_id, kind, scenario, sample_data, related_services, request_factory
):
    """Verify create campaign.

    Arrange: Choose the service type and valid/unknown target; set campaign defaults or explicit overrides.
    Act: Create the campaign through PromotionCreateView.
    Assert and CheckDB: Check campaign/link rows and exact discounts; rejected targets must leave the pre-request database unchanged.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    key, model, target, field = {
        "hotel": ("rooms", RoomPromotion, sample_data.room, "room_id"),
        "flight": ("flights", FlightPromotion, related_services.flight, "flight_id"),
        "activity": (
            "actDates",
            ActivityPromotion,
            related_services.activity_date,
            "activity_date_id",
        ),
        "car": ("cars", CarPromotion, related_services.car, "car_id"),
    }[kind]
    item = {"id": 999999 if scenario == "missing_target" else target.pk}
    if scenario == "override":
        item.update(discount_percent=25, discount_amount=40)
    payload = {
        "type": kind,
        "title": "Campaign created by test",
        "start_date": sample_data.now.isoformat(),
        "end_date": (sample_data.now + timedelta(days=2)).isoformat(),
        key: [item],
    }
    if scenario != "optional_discounts":
        payload.update(discount_percent=10, discount_amount=30)
    state_before_operation = Promotion.objects.count()
    response = request_view(
        request_factory,
        promotion_views.PromotionCreateView,
        "post",
        payload,
        sample_data.user,
    )
    if scenario == "missing_target":
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert response.status_code == 400, response.data
        assert (
            Promotion.objects.count() == state_before_operation
        ), "Rejected request left an orphan promotion row"
    else:
        assert response.status_code == 201, response.data
        promotion = Promotion.objects.get(title=payload["title"])
        link = model.objects.get(promotion=promotion)
        assert getattr(link, field) == target.pk
        assert link.discount_percent == (
            25
            if scenario == "override"
            else 0 if scenario == "optional_discounts" else 10
        )
        assert link.discount_amount == (
            40
            if scenario == "override"
            else 0 if scenario == "optional_discounts" else 30
        )
        assert promotion.title == payload["title"]
        assert (
            promotion.promotion_type
            == {"hotel": 1, "flight": 2, "activity": 3, "car": 4}[kind]
        )
        assert response.data["data"]["promotion_id"] == promotion.pk
        returned_link = response.data["data"][key][0]
        assert returned_link["id"] == target.pk
        assert float(returned_link["discount_percent"] or 0) == link.discount_percent
        assert float(returned_link["discount_amount"] or 0) == link.discount_amount


@pytest.mark.parametrize(
    "case_id,scenario",
    [
        pytest.param(
            f"PR-B{case_index:02}",
            scenario,
            id=f"PR-B{case_index:02}",
            marks=mark(
                f"PR-B{case_index:02}",
                "Promotions",
                "Validate bulk activity promotion operations",
                scenario,
                "Valid bulk operation persists requested rows; empty/malformed lists return 400",
                "promotions/views.py:ActivityPromotionAdminBulkCreateView/ActivityPromotionAdminBulkDeleteView",
            ),
        )
        for case_index, scenario in enumerate(
            [
                "create",
                "create_empty",
                "create_wrong_type",
                "missing_field",
                "delete",
                "delete_empty",
                "delete_wrong_type",
            ],
            1,
        )
    ],
)
def test_bulk_activity_promotions(
    case_id, scenario, sample_data, related_services, request_factory
):
    """Verify bulk activity promotions.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    if scenario.startswith("delete"):
        resource = ActivityPromotion.objects.create(
            promotion=sample_data.promotion,
            activity_date=related_services.activity_date,
        )
        payload = {
            "ids": (
                [resource.pk]
                if scenario == "delete"
                else [] if scenario == "delete_empty" else "invalid"
            )
        }
        response = request_view(
            request_factory,
            promotion_views.ActivityPromotionAdminBulkDeleteView,
            "delete",
            payload,
        )
        # Assert / CheckDB: compare the actual result with the independent expected value.
        assert response.status_code == (200 if scenario == "delete" else 400)
        assert ActivityPromotion.objects.filter(pk=resource.pk).exists() == (
            scenario != "delete"
        )
    else:
        item = {
            "promotion_id": sample_data.promotion.pk,
            "activity_date_id": related_services.activity_date.pk,
            "discount_percent": 15,
        }
        payload = {
            "items": (
                [item]
                if scenario == "create"
                else (
                    []
                    if scenario == "create_empty"
                    else "invalid" if scenario == "create_wrong_type" else [{}]
                )
            )
        }
        response = request_view(
            request_factory,
            promotion_views.ActivityPromotionAdminBulkCreateView,
            "post",
            payload,
        )
        assert response.status_code == (201 if scenario == "create" else 400)
        assert ActivityPromotion.objects.count() == (1 if scenario == "create" else 0)
        if scenario == "create":
            persisted_link = ActivityPromotion.objects.get()
            assert persisted_link.promotion_id == sample_data.promotion.pk
            assert persisted_link.activity_date_id == related_services.activity_date.pk
            assert persisted_link.discount_percent == 15
            assert response.data["data"]["created_count"] == 1


@pytest.mark.parametrize(
    "case_id,kind,city_filter",
    [
        pytest.param(
            f"PR-G{case_index:02}",
            kind,
            filter_value,
            id=f"PR-G{case_index:02}",
            marks=mark(
                f"PR-G{case_index:02}",
                "Promotions",
                "Group promotion detail by hotel or activity",
                f"type={kind}; city filter={filter_value}",
                "Matching parent grouped once; nonmatching city removes hotel",
                "promotions/views.py:PromotionDetailView.retrieve",
            ),
        )
        for case_index, (kind, filter_value) in enumerate(
            [(1, "none"), (1, "match"), (1, "other"), (3, "none")], 1
        )
    ],
)
def test_campaign_grouping(
    case_id, kind, city_filter, sample_data, related_services, request_factory
):
    """Verify campaign grouping.

    Arrange: Prepare the parameter-specific values and persisted fixtures described in the case table.
    Act: Invoke the real target model, serializer or HTTP view with the stated inputs.
    Assert and CheckDB: Assert the explicit return value and the relevant persisted values, relationships or unchanged-row snapshot.
    Rollback: the autouse fixture restores all registered model and M2M rows and compares them with the pre-test snapshot.
    """
    # Arrange: use the values selected by this Test Case ID and isolated fixtures.
    promotion = sample_data.promotion
    promotion.promotion_type = kind
    promotion.save()
    if kind == 1:
        RoomPromotion.objects.create(
            promotion=promotion, room=sample_data.room, discount_percent=10
        )
        RoomPromotion.objects.create(
            promotion=promotion, room=sample_data.room, discount_percent=20
        )
    else:
        ActivityPromotion.objects.create(
            promotion=promotion,
            activity_date=related_services.activity_date,
            discount_percent=10,
        )
        ActivityPromotion.objects.create(
            promotion=promotion,
            activity_date=related_services.activity_date,
            discount_percent=20,
        )
    query = (
        {}
        if city_filter == "none"
        else {"city_id": sample_data.city.pk if city_filter == "match" else 99999}
    )
    response = request_view(
        request_factory,
        promotion_views.PromotionDetailView,
        payload=query,
        pk=promotion.pk,
    )
    # Assert / CheckDB: compare the actual result with the independent expected value.
    assert response.status_code == 200
    grouped = response.data["data"]["hotels" if kind == 1 else "activitys"]
    assert len(grouped) == (0 if city_filter == "other" else 1)
    if grouped:
        assert grouped[0]["max_discount" if kind == 1 else "discount"] == 20


# Executed Test Case ID registry, grouped by the corresponding test function.
# Function: test_create_campaign
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
# Function: test_bulk_activity_promotions
# Test Case ID: PR-B01
# Test Case ID: PR-B02
# Test Case ID: PR-B03
# Test Case ID: PR-B04
# Test Case ID: PR-B05
# Test Case ID: PR-B06
# Test Case ID: PR-B07
# Function: test_campaign_grouping
# Test Case ID: PR-G01
# Test Case ID: PR-G02
# Test Case ID: PR-G03
# Test Case ID: PR-G04
