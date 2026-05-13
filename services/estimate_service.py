from __future__ import annotations

DEVICE_PRICES = {
    "Mobile / PC": 10000,
    "レスポンシブ": 15000,
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


def calculate_estimate(
    device_type: str,
    package_type: str,
    custom_screens: int = 0,
    selected_features: list[str] | None = None,
) -> dict:
    selected_features = selected_features or []
    screen_unit_price = DEVICE_PRICES.get(device_type, 0)
    screen_count = (
        custom_screens if package_type == "カスタムパック" else PACKAGE_SCREENS.get(package_type, 0)
    )
    screen_total = screen_unit_price * max(screen_count, 0)

    items = [
        {
            "name": f"{device_type} 画面単価 x {screen_count}画面",
            "price": screen_total,
        }
    ]
    for feature in selected_features:
        price = FEATURE_PRICES.get(feature, 0)
        items.append({"name": feature, "price": price})

    return {
        "device_type": device_type,
        "package_type": package_type,
        "screen_count": screen_count,
        "screen_unit_price": screen_unit_price,
        "items": items,
        "total_price": sum(item["price"] for item in items),
    }

