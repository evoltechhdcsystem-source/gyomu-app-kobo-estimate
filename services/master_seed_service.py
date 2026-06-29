from __future__ import annotations

from models import (
    DevicePriceMaster,
    FeatureMaster,
    PackageDisplayItemMaster,
    PackageFeatureMaster,
    PackageMaster,
    PackageScreenDefinitionMaster,
    PackageScreenFeatureDefinitionMaster,
    db,
)
from services.estimate_display_service import (
    FEATURE_DESCRIPTIONS,
    FEATURE_ICON_FILES,
    IMPLEMENTATION_SUPPORT_FEATURES,
    EXTERNAL_INTEGRATION_FEATURES,
)
from services.estimate_service import (
    DEVICE_PRICES,
    FEATURE_CONDITIONS,
    FEATURE_PRICES,
    MULTIPLE_FEATURES,
    PACKAGE_FEATURE_QUANTITIES,
    PACKAGE_SCREENS,
)
from services.package_display_service import DEFAULT_PACKAGE_CARDS, DEFAULT_PACKAGE_SCREEN_DEFINITIONS


def seed_estimate_masters() -> None:
    """Seed estimate master tables from the legacy constants when empty."""
    _seed_device_prices()
    _seed_packages()
    _seed_features()
    _seed_package_features()
    _seed_package_display_items()
    _seed_package_screen_definitions()
    db.session.commit()


def _seed_device_prices() -> None:
    if DevicePriceMaster.query.first():
        return
    for sort_order, (name, price) in enumerate(DEVICE_PRICES.items(), start=10):
        db.session.add(
            DevicePriceMaster(
                name=name,
                screen_unit_price=price,
                sort_order=sort_order,
            )
        )


def _seed_packages() -> None:
    if PackageMaster.query.first():
        _fill_package_display_values()
        return
    card_defaults = {str(card["name"]): card for card in DEFAULT_PACKAGE_CARDS}
    for sort_order, (name, screen_count) in enumerate(PACKAGE_SCREENS.items(), start=10):
        card = card_defaults.get(name, {})
        db.session.add(
            PackageMaster(
                name=name,
                screen_count=screen_count,
                price_label=card.get("price_label"),
                image_file=card.get("image_file"),
                image_alt=card.get("image_alt"),
                summary=card.get("summary"),
                detail_title=card.get("detail_title"),
                modal_target=card.get("modal_target"),
                example=card.get("example"),
                sort_order=sort_order,
            )
        )


def _seed_features() -> None:
    if FeatureMaster.query.first():
        _fill_feature_display_values()
        return
    for sort_order, (name, price) in enumerate(FEATURE_PRICES.items(), start=10):
        db.session.add(
            FeatureMaster(
                name=name,
                unit_price=price,
                allow_quantity=name in MULTIPLE_FEATURES,
                category_name=_default_feature_category(name),
                description=FEATURE_DESCRIPTIONS.get(name),
                condition=FEATURE_CONDITIONS.get(name),
                icon_file=FEATURE_ICON_FILES.get(name),
                sort_order=sort_order,
            )
        )


def _seed_package_features() -> None:
    if PackageFeatureMaster.query.first():
        return
    db.session.flush()
    packages = {package.name: package for package in PackageMaster.query.all()}
    features = {feature.name: feature for feature in FeatureMaster.query.all()}
    for package_name, feature_quantities in PACKAGE_FEATURE_QUANTITIES.items():
        package = packages.get(package_name)
        if package is None:
            continue
        for sort_order, (feature_name, quantity) in enumerate(feature_quantities.items(), start=10):
            feature = features.get(feature_name)
            if feature is None:
                continue
            db.session.add(
                PackageFeatureMaster(
                    package_id=package.id,
                    feature_id=feature.id,
                    quantity=quantity,
                    sort_order=sort_order,
                )
            )


def _seed_package_display_items() -> None:
    if PackageDisplayItemMaster.query.first():
        return
    db.session.flush()
    packages = {package.name: package for package in PackageMaster.query.all()}
    for card in DEFAULT_PACKAGE_CARDS:
        package = packages.get(str(card["name"]))
        if package is None:
            continue
        for sort_order, item in enumerate(card.get("items", []), start=10):
            db.session.add(
                PackageDisplayItemMaster(
                    package_id=package.id,
                    text=str(item["text"]),
                    is_section=bool(item.get("section")),
                    sort_order=sort_order,
                )
            )


def _seed_package_screen_definitions() -> None:
    if PackageScreenDefinitionMaster.query.first():
        return
    db.session.flush()
    packages = {package.name: package for package in PackageMaster.query.all()}
    for package_name, definitions in DEFAULT_PACKAGE_SCREEN_DEFINITIONS.items():
        package = packages.get(package_name)
        if package is None:
            continue
        for sort_order, definition in enumerate(definitions, start=10):
            screen_definition = PackageScreenDefinitionMaster(
                package_id=package.id,
                section_title=str(definition.get("section_title") or ""),
                screen_name=str(definition["screen_name"]),
                sort_order=sort_order,
            )
            db.session.add(screen_definition)
            db.session.flush()
            for feature_sort_order, feature in enumerate(definition.get("features", []), start=10):
                db.session.add(
                    PackageScreenFeatureDefinitionMaster(
                        screen_definition_id=screen_definition.id,
                        label=str(feature["label"]),
                        css_class=str(feature.get("css_class") or ""),
                        sort_order=feature_sort_order,
                    )
                )


def _fill_feature_display_values() -> None:
    features = FeatureMaster.query.all()
    if any(feature.category_name or feature.description or feature.condition or feature.icon_file for feature in features):
        return
    for feature in features:
        if not feature.category_name:
            feature.category_name = _default_feature_category(feature.name)
        if not feature.description:
            feature.description = FEATURE_DESCRIPTIONS.get(feature.name)
        if not feature.condition:
            feature.condition = FEATURE_CONDITIONS.get(feature.name)
        if not feature.icon_file:
            feature.icon_file = FEATURE_ICON_FILES.get(feature.name)


def _fill_package_display_values() -> None:
    packages = PackageMaster.query.all()
    if any(
        package.price_label
        or package.image_file
        or package.image_alt
        or package.summary
        or package.detail_title
        or package.modal_target
        or package.example
        for package in packages
    ):
        return
    card_defaults = {str(card["name"]): card for card in DEFAULT_PACKAGE_CARDS}
    for package in packages:
        card = card_defaults.get(package.name, {})
        package.price_label = package.price_label or card.get("price_label")
        package.image_file = package.image_file or card.get("image_file")
        package.image_alt = package.image_alt or card.get("image_alt")
        package.summary = package.summary or card.get("summary")
        package.detail_title = package.detail_title or card.get("detail_title")
        if package.modal_target is None:
            package.modal_target = card.get("modal_target")
        package.example = package.example or card.get("example")


def _default_feature_category(feature_name: str) -> str:
    if feature_name in EXTERNAL_INTEGRATION_FEATURES:
        return "外部連携"
    if feature_name in IMPLEMENTATION_SUPPORT_FEATURES:
        return "導入サポート"
    return "基本機能"
