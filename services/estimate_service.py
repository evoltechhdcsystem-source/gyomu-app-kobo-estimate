from __future__ import annotations

DEVICE_PRICES = {
    "タブレット": 10000,
    "スマートフォン": 10000,
    "スマートフォン・タブレット・PCの3タイプ対応": 15000,
}

PACKAGE_SCREENS = {
    "基本パック": 3,
    "運用パック": 6,
    "カスタムパック": 0,
}

FEATURE_PRICES = {
    "データ登録": 20000,
    "データ編集": 15000,
    "データ検索": 15000,
    "データ削除": 10000,
    "メール送信": 10000,
    "マスターテーブル": 10000,
    "kintone連携": 10000,
    "決済機能": 10000,
    "AI API連携": 10000,
    "ストア申請代行": 30000,
    "操作マニュアル": 10000,
    "ユーザーログイン": 30000,
}

MULTIPLE_FEATURES = {
    "データ登録",
    "データ編集",
    "データ検索",
    "データ削除",
    "メール送信",
    "マスターテーブル",
    "kintone連携",
    "AI API連携",
}


def calculate_estimate(
    device_type: str,
    package_type: str,
    custom_screens: int = 0,
    selected_features: list[str] | None = None,
    feature_quantities: dict[str, int] | None = None,
) -> dict:
    selected_features = selected_features or []
    feature_quantities = feature_quantities or {}
    screen_unit_price = DEVICE_PRICES.get(device_type, 0)
    screen_count = (
        custom_screens if package_type == "カスタムパック" else PACKAGE_SCREENS.get(package_type, 0)
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
        if feature not in MULTIPLE_FEATURES:
            quantity = 1
        unit_price = FEATURE_PRICES.get(feature, 0)
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
