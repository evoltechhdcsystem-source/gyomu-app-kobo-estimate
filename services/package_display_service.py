from __future__ import annotations

from flask import has_app_context

from models import (
    PackageDisplayItemMaster,
    PackageMaster,
    PackageScreenDefinitionMaster,
)
from services.estimate_service import package_screens

DEFAULT_PACKAGE_CARDS: list[dict[str, object]] = [
    {
        "name": "基本パック",
        "price_label": "3画面",
        "image_file": "img/package-basic-generated.png",
        "image_alt": "基本パックのイメージ",
        "summary": "まず小さく始めたい現場向け。",
        "detail_title": "入っている内容",
        "modal_target": "basicPackageFeaturesModal",
        "items": [
            {"text": "記録を入力する画面"},
            {"text": "入力した記録を一覧で見る画面"},
            {"text": "記録の詳しい内容を見る画面"},
        ],
        "example": "例: 作業日報、設備点検、検品記録など",
    },
    {
        "name": "運用パック",
        "price_label": "6画面",
        "image_file": "img/package-operation-generated.png",
        "image_alt": "運用パックのイメージ",
        "summary": "毎日の業務でしっかり使いたい現場向け。",
        "detail_title": "入っている内容",
        "modal_target": "operationPackageFeaturesModal",
        "items": [
            {"text": "通常利用", "section": True},
            {"text": "記録を入力する画面"},
            {"text": "入力した記録を一覧で見る画面"},
            {"text": "記録の詳しい内容を見る画面"},
            {"text": "管理者向け", "section": True},
            {"text": "管理用の情報を入力する画面"},
            {"text": "管理用の情報を一覧で見る画面"},
            {"text": "管理用の情報の詳しい内容を見る画面"},
        ],
        "example": "例: 在庫管理、不良記録、出荷確認、工程の進み具合確認など",
    },
    {
        "name": "カスタムパック",
        "price_label": "画面数・機能を指定",
        "image_file": "img/package-custom-generated.png",
        "image_alt": "カスタムパックのイメージ",
        "summary": "自社のやり方に合わせて作りたい現場向け。",
        "detail_title": "追加できる内容",
        "modal_target": "",
        "items": [
            {"text": "必要な画面数を指定"},
            {"text": "ログイン機能"},
            {"text": "外部サービスとの連携"},
            {"text": "App Store / Google Play公開申請代行など"},
        ],
        "example": "例: 承認が必要な申請、複数部署で使う管理表、既存システムとの連携など",
    },
]

DEFAULT_PACKAGE_SCREEN_DEFINITIONS: dict[str, list[dict[str, object]]] = {
    "基本パック": [
        {
            "screen_name": "記録を入力する画面",
            "features": [{"label": "データ登録機能", "css_class": "is-create"}],
        },
        {"screen_name": "入力した記録を一覧で見る画面", "features": []},
        {
            "screen_name": "記録の詳しい内容を見る画面",
            "features": [
                {"label": "データ編集機能", "css_class": "is-edit"},
                {"label": "データ削除機能", "css_class": "is-delete"},
            ],
        },
    ],
    "運用パック": [
        {
            "section_title": "通常利用",
            "screen_name": "記録を入力する画面",
            "features": [{"label": "データ登録機能", "css_class": "is-create"}],
        },
        {"screen_name": "入力した記録を一覧で見る画面", "features": []},
        {
            "screen_name": "入力した記録の検索画面",
            "features": [{"label": "データ検索機能", "css_class": "is-search"}],
        },
        {
            "screen_name": "記録の詳しい内容を見る画面",
            "features": [
                {"label": "データ編集機能", "css_class": "is-edit"},
                {"label": "データ削除機能", "css_class": "is-delete"},
            ],
        },
        {
            "section_title": "管理者向け",
            "screen_name": "管理用の情報を入力する画面",
            "features": [{"label": "データ登録機能", "css_class": "is-create"}],
        },
        {"screen_name": "管理用の情報を一覧で見る画面", "features": []},
        {
            "screen_name": "管理用の情報の詳しい内容を見る画面",
            "features": [
                {"label": "データ編集機能", "css_class": "is-edit"},
                {"label": "データ削除機能", "css_class": "is-delete"},
            ],
        },
    ],
}


def package_choice_cards() -> list[dict[str, object]]:
    current_package_screens = package_screens()
    if not has_app_context():
        return _fallback_package_cards(current_package_screens)

    packages = (
        PackageMaster.query
        .filter_by(is_active=True)
        .order_by(PackageMaster.sort_order, PackageMaster.id)
        .all()
    )
    if not packages:
        return _fallback_package_cards(current_package_screens)

    fallback_cards = {card["name"]: card for card in DEFAULT_PACKAGE_CARDS}
    cards: list[dict[str, object]] = []
    for package in packages:
        fallback = fallback_cards.get(package.name, {})
        screen_count = current_package_screens.get(package.name, package.screen_count)
        items = [
            {"text": row.text, "section": row.is_section}
            for row in PackageDisplayItemMaster.query
            .filter_by(package_id=package.id, is_active=True)
            .order_by(PackageDisplayItemMaster.sort_order, PackageDisplayItemMaster.id)
            .all()
        ]
        cards.append(
            {
                "name": package.name,
                "data_screens": screen_count or 1,
                "price_label": package.price_label or fallback.get("price_label") or _screen_price_label(screen_count),
                "image_file": package.image_file or fallback.get("image_file") or "img/package-custom-generated.png",
                "image_alt": package.image_alt or fallback.get("image_alt") or f"{package.name}のイメージ",
                "summary": package.summary or fallback.get("summary") or "マスターに追加されたパックです。",
                "detail_title": package.detail_title or fallback.get("detail_title") or "入っている内容",
                "modal_target": package.modal_target if package.modal_target is not None else fallback.get("modal_target", ""),
                "items": items or fallback.get("items") or [{"text": "パック内容は管理マスターを確認してください"}],
                "example": package.example or fallback.get("example") or "例: 個別に定義した業務パック",
            }
        )
    return cards


def package_screen_definitions_by_package() -> dict[str, list[dict[str, object]]]:
    if not has_app_context():
        return DEFAULT_PACKAGE_SCREEN_DEFINITIONS
    rows = (
        PackageScreenDefinitionMaster.query
        .join(PackageMaster)
        .filter(PackageScreenDefinitionMaster.is_active.is_(True))
        .filter(PackageMaster.is_active.is_(True))
        .order_by(PackageMaster.sort_order, PackageScreenDefinitionMaster.sort_order, PackageScreenDefinitionMaster.id)
        .all()
    )
    if not rows:
        return DEFAULT_PACKAGE_SCREEN_DEFINITIONS

    definitions: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        definitions.setdefault(row.package.name, []).append(
            {
                "section_title": row.section_title or "",
                "screen_name": row.screen_name,
                "features": [
                    {
                        "label": feature.label,
                        "css_class": feature.css_class or "",
                    }
                    for feature in sorted(
                        (feature for feature in row.feature_definitions if feature.is_active),
                        key=lambda feature: (feature.sort_order, feature.id),
                    )
                ],
            }
        )
    return definitions or DEFAULT_PACKAGE_SCREEN_DEFINITIONS


def _fallback_package_cards(current_package_screens: dict[str, int]) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for card in DEFAULT_PACKAGE_CARDS:
        screen_count = current_package_screens.get(str(card["name"]), 0)
        cards.append({**card, "data_screens": screen_count or 1})
    known_names = {str(card["name"]) for card in cards}
    for name, screen_count in current_package_screens.items():
        if name in known_names:
            continue
        cards.append(
            {
                "name": name,
                "data_screens": screen_count,
                "price_label": _screen_price_label(screen_count),
                "image_file": "img/package-custom-generated.png",
                "image_alt": f"{name}のイメージ",
                "summary": "マスターに追加されたパックです。",
                "detail_title": "入っている内容",
                "modal_target": "",
                "items": [{"text": "パック内容は管理マスターを確認してください"}],
                "example": "例: 個別に定義した業務パック",
            }
        )
    return cards


def _screen_price_label(screen_count: int) -> str:
    return f"{screen_count}画面" if screen_count else "画面数・機能を指定"
