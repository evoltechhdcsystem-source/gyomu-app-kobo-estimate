from __future__ import annotations

from models import (
    FULL_PLAN, SIMPLE_PLAN, DevicePriceMaster, FeatureMaster,
    PackageDisplayItemMaster, PackageFeatureMaster, PackageMaster,
    PackageScreenDefinitionMaster, PackageScreenFeatureDefinitionMaster,
    PlanMaster, db, stored_master_name,
)


def seed_plans() -> None:
    if db.session.get(PlanMaster, SIMPLE_PLAN) is None:
        db.session.add(PlanMaster(
            key=SIMPLE_PLAN, name="かんたんアプリプラン", is_active=True,
        ))
    if db.session.get(PlanMaster, FULL_PLAN) is None:
        db.session.add(PlanMaster(
            key=FULL_PLAN, name="しっかりアプリプラン", is_active=False,
        ))
    db.session.flush()
    full_plan = db.session.get(PlanMaster, FULL_PLAN)
    if full_plan.is_seeded:
        db.session.commit()
        return

    for row in DevicePriceMaster.query.filter_by(plan_key=SIMPLE_PLAN).all():
        db.session.add(DevicePriceMaster(
            name=stored_master_name(FULL_PLAN, row.public_name), plan_key=FULL_PLAN,
            screen_unit_price=row.screen_unit_price, sort_order=row.sort_order,
            is_active=row.is_active,
        ))

    package_ids: dict[int, int] = {}
    feature_ids: dict[int, int] = {}
    for row in PackageMaster.query.filter_by(plan_key=SIMPLE_PLAN).all():
        clone = PackageMaster(
            name=stored_master_name(FULL_PLAN, row.public_name), plan_key=FULL_PLAN,
            screen_count=row.screen_count, price_label=row.price_label,
            image_file=row.image_file, image_alt=row.image_alt, summary=row.summary,
            detail_title=row.detail_title, modal_target=row.modal_target,
            example=row.example, sort_order=row.sort_order, is_active=row.is_active,
        )
        db.session.add(clone)
        db.session.flush()
        package_ids[row.id] = clone.id
    for row in FeatureMaster.query.filter_by(plan_key=SIMPLE_PLAN).all():
        clone = FeatureMaster(
            name=stored_master_name(FULL_PLAN, row.public_name), plan_key=FULL_PLAN,
            unit_price=row.unit_price, is_quote_required=row.is_quote_required,
            allow_quantity=row.allow_quantity,
            category_name=row.category_name, description=row.description,
            condition=row.condition, icon_file=row.icon_file,
            sort_order=row.sort_order, is_active=row.is_active,
        )
        db.session.add(clone)
        db.session.flush()
        feature_ids[row.id] = clone.id
    for row in PackageFeatureMaster.query.all():
        if row.package_id in package_ids and row.feature_id in feature_ids:
            db.session.add(PackageFeatureMaster(
                package_id=package_ids[row.package_id], feature_id=feature_ids[row.feature_id],
                quantity=row.quantity, sort_order=row.sort_order,
            ))
    for row in PackageDisplayItemMaster.query.all():
        if row.package_id in package_ids:
            db.session.add(PackageDisplayItemMaster(
                package_id=package_ids[row.package_id], text=row.text,
                is_section=row.is_section, sort_order=row.sort_order, is_active=row.is_active,
            ))
    for row in PackageScreenDefinitionMaster.query.all():
        if row.package_id not in package_ids:
            continue
        clone = PackageScreenDefinitionMaster(
            package_id=package_ids[row.package_id], section_title=row.section_title,
            screen_name=row.screen_name, sort_order=row.sort_order, is_active=row.is_active,
        )
        db.session.add(clone)
        db.session.flush()
        for feature in row.feature_definitions:
            db.session.add(PackageScreenFeatureDefinitionMaster(
                screen_definition_id=clone.id, label=feature.label,
                css_class=feature.css_class, sort_order=feature.sort_order,
                is_active=feature.is_active,
            ))
    full_plan.is_seeded = True
    db.session.commit()
