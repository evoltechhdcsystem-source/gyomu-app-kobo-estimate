from __future__ import annotations

from flask import has_app_context
from services.maintenance_service import MAINTENANCE_NAME

from models import (
    SIMPLE_PLAN, DevicePriceMaster, FeatureDevicePriceMaster, FeatureMaster,
    PackageFeatureMaster, PackageMaster, stored_master_name,
)

DEVICE_PRICES = {
    "スマートフォン": 10000,
    "PC": 10000,
    "スマートフォン・タブレット・PCの3タイプ対応": 15000,
}

PACKAGE_SCREENS = {
    "基本パック": 3,
    "運用パック": 6,
    "カスタムパック": 0,
}

FEATURE_PRICES = {
    "画面表示項目追加": 10000,
    "データ登録": 20000,
    "データ編集": 15000,
    "データ検索": 15000,
    "データ削除": 10000,
    "メール送信": 10000,
    "マスターテーブル": 10000,
    "kintone連携": 10000,
    "AI API連携": 10000,
    "App Store / Google Play公開申請代行": 50000,
    "ユーザー操作マニュアル": 5000,
    "ユーザーログイン": 30000,
    "アプリ作成相談": 2000,
}

MULTIPLE_FEATURES = {
    "画面表示項目追加",
    "データ登録",
    "データ編集",
    "データ検索",
    "データ削除",
    "メール送信",
    "マスターテーブル",
    "kintone連携",
    "AI API連携",
    "ユーザー操作マニュアル",
    "アプリ作成相談",
}

SCREEN_PARTS_CONDITION = "1画面内のパーツ20個まで"
FEATURE_CONDITIONS = {
    "画面表示項目追加": "1画面内のパーツ+20個",
    "データ登録": "実績テーブル作成とデータ追加機能",
    "データ編集": "データの更新機能",
    "データ検索": "複数条件でのデータ検索",
    "データ削除": "確認画面付き",
    "メール送信": "指定の1アドレスにメール送信",
    "マスターテーブル": "マスターデータを管理するテーブルを1つ作成",
    "kintone連携": "kintoneのデータベース1つと連携",
    "AI API連携": "AI API 1機能分の連携",
    "App Store / Google Play公開申請代行": "App StoreかGoogle Playのどちらかに公開",
    "ユーザー操作マニュアル": "1画面あたりの操作マニュアル作成",
    "ユーザーログイン": "ユーザー認証機能の追加",
    "アプリ作成相談": "アプリ作成の打ち合わせ2時間は基本の料金に含まれます",
}

PACKAGE_FEATURE_QUANTITIES = {
    "基本パック": {
        "データ登録": 1,
        "データ編集": 1,
        "データ削除": 1,
    },
    "運用パック": {
        "データ登録": 2,
        "データ編集": 2,
        "データ削除": 2,
        "データ検索": 1,
    },
}


def device_prices(plan_key: str = SIMPLE_PLAN) -> dict[str, int]:
    if not has_app_context():
        return dict(DEVICE_PRICES)
    rows = (
        DevicePriceMaster.query
        .filter_by(is_active=True, plan_key=plan_key)
        .order_by(DevicePriceMaster.sort_order, DevicePriceMaster.id)
        .all()
    )
    return {row.public_name: row.screen_unit_price for row in rows}


def package_screens(plan_key: str = SIMPLE_PLAN) -> dict[str, int]:
    if not has_app_context():
        return dict(PACKAGE_SCREENS)
    rows = (
        PackageMaster.query
        .filter_by(is_active=True, plan_key=plan_key)
        .order_by(PackageMaster.sort_order, PackageMaster.id)
        .all()
    )
    return {row.public_name: row.screen_count for row in rows}


def feature_prices(plan_key: str = SIMPLE_PLAN) -> dict[str, int]:
    if not has_app_context():
        return dict(FEATURE_PRICES)
    rows = (
        FeatureMaster.query
        .filter_by(is_active=True, plan_key=plan_key)
        .order_by(FeatureMaster.sort_order, FeatureMaster.id)
        .all()
    )
    return {row.public_name: row.unit_price for row in rows}


def quote_required_features(plan_key: str = SIMPLE_PLAN) -> set[str]:
    if not has_app_context():
        return set()
    rows = FeatureMaster.query.filter_by(
        is_active=True, is_quote_required=True, plan_key=plan_key,
    ).all()
    return {row.public_name for row in rows}


def multiple_features(plan_key: str = SIMPLE_PLAN) -> set[str]:
    if not has_app_context():
        return set(MULTIPLE_FEATURES)
    rows = (
        FeatureMaster.query
        .filter_by(is_active=True, allow_quantity=True, plan_key=plan_key)
        .order_by(FeatureMaster.sort_order, FeatureMaster.id)
        .all()
    )
    return {row.public_name for row in rows}


def package_feature_quantities(package_type: str, plan_key: str = SIMPLE_PLAN) -> dict[str, int]:
    if not has_app_context():
        return dict(PACKAGE_FEATURE_QUANTITIES.get(package_type, {}))
    rows = (
        PackageFeatureMaster.query
        .join(PackageMaster)
        .join(FeatureMaster)
        .filter(PackageMaster.plan_key == plan_key)
        .filter(FeatureMaster.plan_key == plan_key)
        .filter(PackageMaster.is_active.is_(True))
        .filter(FeatureMaster.is_active.is_(True))
        .order_by(PackageFeatureMaster.sort_order, PackageFeatureMaster.id)
        .all()
    )
    return {row.feature.public_name: row.quantity for row in rows if row.package.public_name == package_type}


def package_features(package_type: str, plan_key: str = SIMPLE_PLAN) -> list[str]:
    return list(package_feature_quantities(package_type, plan_key))


def package_feature_total(package_type: str, device_type: str, plan_key: str = SIMPLE_PLAN) -> int:
    current_feature_prices = feature_prices(plan_key)
    return sum(
        current_feature_prices.get(feature, 0) * quantity
        for feature, quantity in package_feature_quantities(package_type, plan_key).items()
        if not (plan_key == "full" and feature == MAINTENANCE_NAME)
    )


def feature_unit_price(feature: str, device_type: str, plan_key: str = SIMPLE_PLAN) -> int:
    return feature_prices_for_device(device_type, plan_key).get(feature, 0)


def feature_prices_for_device(device_type: str, plan_key: str = SIMPLE_PLAN) -> dict[str, int]:
    prices = feature_prices(plan_key)
    if not has_app_context():
        return prices
    device = DevicePriceMaster.query.filter_by(
        plan_key=plan_key, name=stored_master_name(plan_key, device_type), is_active=True,
    ).first()
    if device is None:
        return prices
    overrides = (
        FeatureDevicePriceMaster.query
        .join(FeatureMaster)
        .filter(FeatureDevicePriceMaster.device_id == device.id)
        .filter(FeatureMaster.plan_key == plan_key, FeatureMaster.is_active.is_(True))
        .all()
    )
    for override in overrides:
        prices[override.feature.public_name] = override.unit_price
    return prices


def calculate_estimate(
    device_type: str,
    package_type: str,
    custom_screens: int = 0,
    selected_features: list[str] | None = None,
    feature_quantities: dict[str, int] | None = None,
    plan_key: str = SIMPLE_PLAN,
) -> dict:
    if package_type == "カスタムパック":
        selected_features = selected_features or []
        feature_quantities = feature_quantities or {}
    else:
        feature_quantities = package_feature_quantities(package_type, plan_key)
        selected_features = list(feature_quantities)
    current_device_prices = device_prices(plan_key)
    current_package_screens = package_screens(plan_key)
    current_feature_prices = (
        feature_prices_for_device(device_type, plan_key)
        if package_type == "カスタムパック" else feature_prices(plan_key)
    )
    current_multiple_features = multiple_features(plan_key)
    quote_names = quote_required_features(plan_key) if package_type == "カスタムパック" else set()
    screen_unit_price = current_device_prices.get(device_type, 0)
    screen_count = (
        custom_screens if package_type == "カスタムパック" else current_package_screens.get(package_type, 0)
    )
    screen_total = screen_unit_price * max(screen_count, 0)

    items = [
        {
            "name": f"{device_type} x {screen_count}画面",
            "price": screen_total,
        }
    ]
    for feature in selected_features:
        if plan_key == "full" and feature == MAINTENANCE_NAME:
            continue
        quantity = max(int(feature_quantities.get(feature, 1) or 1), 1)
        if package_type == "カスタムパック" and feature not in current_multiple_features:
            quantity = 1
        if feature not in current_feature_prices:
            continue
        unit_price = current_feature_prices[feature]
        name = f"{feature} x {quantity}" if quantity > 1 else feature
        if feature in quote_names:
            items.append({"name": name, "price": 0, "is_quote_required": True})
        else:
            items.append({"name": name, "price": unit_price * quantity})

    return {
        "device_type": device_type,
        "package_type": package_type,
        "screen_count": screen_count,
        "screen_unit_price": screen_unit_price,
        "items": items,
        "total_price": sum(item["price"] for item in items),
    }
