from __future__ import annotations

from flask import has_app_context

from models import FeatureMaster
from services.estimate_service import (
    FEATURE_CONDITIONS,
    SCREEN_PARTS_CONDITION,
    feature_prices_for_device,
)

EXTERNAL_INTEGRATION_FEATURES = {"kintone連携", "AI API連携"}
IMPLEMENTATION_SUPPORT_FEATURES = {
    "App Store / Google Play公開申請代行",
    "ユーザー操作マニュアル",
    "アプリ作成相談",
}
FEATURE_DESCRIPTIONS = {
    "画面表示項目追加": "1画面内に表示・入力できる項目数を増やします。",
    "データ登録": "新しい情報を入力フォームから追加できます。",
    "データ編集": "登録済みの情報をあとから修正できます。",
    "データ検索": "条件を指定して必要な情報を探せます。",
    "データ削除": "不要な情報を削除できます。",
    "メール送信": "通知や受付内容をメールで送信できます。",
    "マスターテーブル": "商品・顧客・分類などの基本データを管理できます。",
    "kintone連携": "別途kintone Standard以上のライセンスが必要です。",
    "AI API連携": "AIによる文章作成、要約、判定などを追加できます。外部AIサービスの利用料は別途必要です。",
    "App Store / Google Play公開申請代行": "アプリ公開に必要な申請作業を代行します。",
    "ユーザー操作マニュアル": "利用者向けの操作説明書を作成します。1画面あたりの料金です。",
    "ユーザーログイン": "利用者ごとにログインして使えるようにします。",
    "アプリ作成相談": "どんなアプリを作ればいいかなどのご相談を承ります。",
}
FEATURE_ICON_FILES = {
    "画面表示項目追加": "feature-table.svg",
    "データ登録": "feature-add.svg",
    "データ編集": "feature-edit.svg",
    "データ検索": "feature-search.svg",
    "データ削除": "feature-delete.svg",
    "メール送信": "feature-mail.svg",
    "マスターテーブル": "feature-table.svg",
    "kintone連携": "feature-link.svg",
    "AI API連携": "feature-ai.svg",
    "App Store / Google Play公開申請代行": "feature-store.svg",
    "ユーザー操作マニュアル": "feature-manual.svg",
    "ユーザーログイン": "feature-login.svg",
    "アプリ作成相談": "feature-manual.svg",
}
SCREEN_DESCRIPTIONS = {
    "データ登録画面": "新しい情報を入力して保存するための画面です。",
    "データ一覧画面": "登録した情報をまとめて確認し、必要なデータを探しやすくします。",
    "データ詳細画面": "1件ごとの内容を詳しく確認するための画面です。",
    "検索・絞り込み機能": "条件を指定して、必要な情報だけをすばやく見つけられます。",
    "データ修正画面": "登録済みの情報をあとから変更・更新できます。",
    "集計・状況確認画面": "件数や状態を集計し、業務の状況を把握しやすくします。",
    "データ登録機能": "業務データを入力して保存できます。",
    "データ検索機能": "条件を指定して必要なデータを検索できます。",
    "データ編集機能": "登録済みの業務データを更新できます。",
    "データ削除機能": "不要になった業務データを削除できます。",
    "データ登録機能（マスター）": "マスターデータを入力して保存できます。",
    "データ編集機能（マスター）": "登録済みのマスターデータを更新できます。",
    "データ削除機能（マスター）": "不要になったマスターデータを削除できます。",
}
INCLUDED_WORK_ITEMS = [
    "画面・機能確認のお打ち合わせ 2時間まで",
    "アプリの設計・制作",
    "開発環境 Click の契約サポート",
    "仮納品後の微調整",
    "納品・操作説明 1時間まで",
]


def estimate_item_label(item_name: str) -> str:
    return (
        item_name
        .replace(" 画面単価 x ", " x ")
        .replace("kintoneのデータベースと連携する(1DB)", "kintone連携")
        .replace("ストア申請代行", "App Store / Google Play公開申請代行")
        .replace("アプリ作成コンサル", "アプリ作成相談")
        .replace("操作マニュアル", "ユーザー操作マニュアル")
    )


def estimate_feature_name(item_name: str) -> str:
    feature_name = item_name.split(" x ", 1)[0]
    if feature_name == "kintoneのデータベースと連携する(1DB)":
        return "kintone連携"
    if feature_name == "アプリ作成コンサル":
        return "アプリ作成相談"
    if feature_name == "ストア申請代行":
        return "App Store / Google Play公開申請代行"
    if feature_name == "操作マニュアル":
        return "ユーザー操作マニュアル"
    return feature_name


def estimate_screen_count(item_name: str) -> int:
    try:
        return int(item_name.rsplit(" x ", 1)[-1].replace("画面", ""))
    except (ValueError, IndexError):
        return 0


def is_screen_count_item(item_name: str, device_type: str) -> bool:
    return item_name.startswith(device_type) and "画面" in item_name


def estimate_item_condition(item_name: str, device_type: str) -> str:
    if is_screen_count_item(item_name, device_type):
        return SCREEN_PARTS_CONDITION
    return feature_conditions().get(estimate_feature_name(item_name), "")


def custom_feature_categories(device_type: str) -> list[dict[str, object]]:
    feature_prices = feature_prices_for_device(device_type)
    category_rules = _category_rules()
    categories: list[dict[str, object]] = []
    categorized_features = {
        feature_name
        for _, feature_names in category_rules
        if feature_names is not None
        for feature_name in feature_names
    }
    for category_name, feature_names in category_rules:
        items = [
            (name, price)
            for name, price in feature_prices.items()
            if (name not in categorized_features if feature_names is None else name in feature_names)
        ]
        categories.append({"name": category_name, "features": items})
    return categories


def feature_descriptions() -> dict[str, str]:
    if not has_app_context():
        return dict(FEATURE_DESCRIPTIONS)
    rows = FeatureMaster.query.filter_by(is_active=True).all()
    values = {row.name: row.description for row in rows if row.description}
    return values or dict(FEATURE_DESCRIPTIONS)


def feature_conditions() -> dict[str, str]:
    if not has_app_context():
        return dict(FEATURE_CONDITIONS)
    rows = FeatureMaster.query.filter_by(is_active=True).all()
    values = {row.name: row.condition for row in rows if row.condition}
    return values or dict(FEATURE_CONDITIONS)


def feature_icon_files() -> dict[str, str]:
    if not has_app_context():
        return dict(FEATURE_ICON_FILES)
    rows = FeatureMaster.query.filter_by(is_active=True).all()
    values = {row.name: row.icon_file for row in rows if row.icon_file}
    return values or dict(FEATURE_ICON_FILES)


def screen_descriptions() -> dict[str, str]:
    return dict(SCREEN_DESCRIPTIONS)


def _category_rules() -> list[tuple[str, set[str] | None]]:
    if not has_app_context():
        return [
            ("基本機能", None),
            ("外部連携", EXTERNAL_INTEGRATION_FEATURES),
            ("導入サポート", IMPLEMENTATION_SUPPORT_FEATURES),
        ]

    rows = (
        FeatureMaster.query
        .filter_by(is_active=True)
        .order_by(FeatureMaster.sort_order, FeatureMaster.id)
        .all()
    )
    categories: list[tuple[str, set[str] | None]] = []
    for row in rows:
        category_name = row.category_name or "基本機能"
        existing = next((item for item in categories if item[0] == category_name), None)
        if existing is None:
            categories.append((category_name, {row.name}))
        elif existing[1] is not None:
            existing[1].add(row.name)
    return categories or [
        ("基本機能", None),
        ("外部連携", EXTERNAL_INTEGRATION_FEATURES),
        ("導入サポート", IMPLEMENTATION_SUPPORT_FEATURES),
    ]
