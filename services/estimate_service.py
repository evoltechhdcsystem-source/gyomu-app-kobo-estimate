from __future__ import annotations

from flask import has_app_context

from models import DevicePriceMaster, FeatureMaster, PackageFeatureMaster, PackageMaster

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


def device_prices() -> dict[str, int]:
    if not has_app_context():
        return dict(DEVICE_PRICES)
    rows = (
        DevicePriceMaster.query
        .filter_by(is_active=True)
        .order_by(DevicePriceMaster.sort_order, DevicePriceMaster.id)
        .all()
    )
    if not rows:
        return dict(DEVICE_PRICES)
    return {row.name: row.screen_unit_price for row in rows}


def package_screens() -> dict[str, int]:
    if not has_app_context():
        return dict(PACKAGE_SCREENS)
    rows = (
        PackageMaster.query
        .filter_by(is_active=True)
        .order_by(PackageMaster.sort_order, PackageMaster.id)
        .all()
    )
    if not rows:
        return dict(PACKAGE_SCREENS)
    return {row.name: row.screen_count for row in rows}


def feature_prices() -> dict[str, int]:
    if not has_app_context():
        return dict(FEATURE_PRICES)
    rows = (
        FeatureMaster.query
        .filter_by(is_active=True)
        .order_by(FeatureMaster.sort_order, FeatureMaster.id)
        .all()
    )
    if not rows:
        return dict(FEATURE_PRICES)
    return {row.name: row.unit_price for row in rows}


def multiple_features() -> set[str]:
    if not has_app_context():
        return set(MULTIPLE_FEATURES)
    rows = (
        FeatureMaster.query
        .filter_by(is_active=True, allow_quantity=True)
        .order_by(FeatureMaster.sort_order, FeatureMaster.id)
        .all()
    )
    if not rows:
        return set(MULTIPLE_FEATURES)
    return {row.name for row in rows}


def package_feature_quantities(package_type: str) -> dict[str, int]:
    if not has_app_context():
        return dict(PACKAGE_FEATURE_QUANTITIES.get(package_type, {}))
    rows = (
        PackageFeatureMaster.query
        .join(PackageMaster)
        .join(FeatureMaster)
        .filter(PackageMaster.name == package_type)
        .filter(PackageMaster.is_active.is_(True))
        .filter(FeatureMaster.is_active.is_(True))
        .order_by(PackageFeatureMaster.sort_order, PackageFeatureMaster.id)
        .all()
    )
    if not rows:
        return dict(PACKAGE_FEATURE_QUANTITIES.get(package_type, {}))
    return {row.feature.name: row.quantity for row in rows}


def package_features(package_type: str) -> list[str]:
    return list(package_feature_quantities(package_type))


def package_feature_total(package_type: str, device_type: str) -> int:
    return sum(
        feature_unit_price(feature, device_type) * quantity
        for feature, quantity in package_feature_quantities(package_type).items()
    )


def feature_unit_price(feature: str, device_type: str) -> int:
    current_device_prices = device_prices()
    current_feature_prices = feature_prices()
    if feature == "画面表示項目追加":
        return current_device_prices.get(device_type, current_feature_prices.get(feature, 0))
    return current_feature_prices.get(feature, 0)


def feature_prices_for_device(device_type: str) -> dict[str, int]:
    prices = feature_prices()
    prices["画面表示項目追加"] = feature_unit_price("画面表示項目追加", device_type)
    return prices


def calculate_estimate(
    device_type: str,
    package_type: str,
    custom_screens: int = 0,
    selected_features: list[str] | None = None,
    feature_quantities: dict[str, int] | None = None,
) -> dict:
    if package_type == "カスタムパック":
        selected_features = selected_features or []
        feature_quantities = feature_quantities or {}
    else:
        feature_quantities = package_feature_quantities(package_type)
        selected_features = list(feature_quantities)
    current_device_prices = device_prices()
    current_package_screens = package_screens()
    current_feature_prices = feature_prices()
    current_multiple_features = multiple_features()
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
        quantity = max(int(feature_quantities.get(feature, 1) or 1), 1)
        if feature not in current_multiple_features:
            quantity = 1
        if feature not in current_feature_prices:
            continue
        unit_price = feature_unit_price(feature, device_type)
        name = f"{feature} x {quantity}" if quantity > 1 else feature
        items.append({"name": name, "price": unit_price * quantity})

    return {
        "device_type": device_type,
        "package_type": package_type,
        "screen_count": screen_count,
        "screen_unit_price": screen_unit_price,
        "items": items,
        "total_price": sum(item["price"] for item in items),
    }
