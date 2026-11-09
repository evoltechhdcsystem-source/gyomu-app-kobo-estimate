import os
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import app  # noqa: E402
from models import (  # noqa: E402
    FULL_PLAN, SIMPLE_PLAN, DevicePriceMaster, Estimate, FeatureDevicePriceMaster, FeatureMaster,
    Inquiry, PackageDisplayItemMaster, PackageFeatureMaster, PackageMaster, PlanMaster, db,
)
from services.estimate_service import (  # noqa: E402
    calculate_estimate, feature_prices_for_device, package_feature_total,
)
from services.estimate_pdf_service import _estimate_pdf_items, _included_work_and_notes  # noqa: E402
from services.notification_context import estimate_lines  # noqa: E402
from services.package_display_service import package_choice_cards  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.platypus import Paragraph, Table  # noqa: E402


class PlanFlowTest(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def test_pdf_click_terms_are_kept_only_for_simple_plan(self):
        style = ParagraphStyle("pdf-plan-test")
        for plan_key, has_click_terms in ((SIMPLE_PLAN, True), (FULL_PLAN, False)):
            flowables = _included_work_and_notes(style, style, plan_key)
            texts = []
            for flowable in flowables:
                if isinstance(flowable, Paragraph):
                    texts.append(flowable.getPlainText())
                elif isinstance(flowable, Table):
                    texts.extend(cell.getPlainText() for row in flowable._cellvalues for cell in row)
            content = " ".join(texts)
            self.assertEqual("開発環境 Click の契約サポート" in content, has_click_terms)
            self.assertEqual("開発ツールライセンス" in content, has_click_terms)
            self.assertEqual("Click Standardプラン以上" in content, has_click_terms)
            self.assertNotIn("Google Cloud利用料（月額）", content)

    def test_quote_required_custom_feature_is_excluded_and_saved(self):
        with app.app_context():
            feature = FeatureMaster.query.filter_by(plan_key=FULL_PLAN, name="full::データ登録").one()
            plan = db.session.get(PlanMaster, FULL_PLAN)
            original = (feature.unit_price, feature.is_quote_required, feature.is_active, plan.is_active)
            feature_fields = {
                "category_name": feature.category_name or "",
                "description": feature.description or "",
                "condition": feature.condition or "",
                "icon_file": feature.icon_file or "",
                "sort_order": str(feature.sort_order),
                "allow_quantity": "1" if feature.allow_quantity else "",
            }
            feature.is_active = True
            plan.is_active = True
            db.session.commit()
            feature_id = feature.id
            regular_package_total = calculate_estimate("PC", "基本パック", plan_key=FULL_PLAN)["total_price"]
            screen_price = DevicePriceMaster.query.filter_by(plan_key=FULL_PLAN, name="full::PC").one().screen_unit_price
        try:
            with self.client.session_transaction() as browser_session:
                browser_session["admin_logged_in"] = True
            response = self.client.post(f"/admin/masters/features/{feature_id}", data={
                "plan_key": FULL_PLAN, "name": "データ登録", "unit_price": str(original[0]),
                "is_quote_required": "1", "is_active": "1", **feature_fields,
            })
            self.assertEqual(response.status_code, 302)
            with app.app_context():
                self.assertEqual(calculate_estimate("PC", "基本パック", plan_key=FULL_PLAN)["total_price"], regular_package_total)
            self.client.post("/plan", data={"plan_key": FULL_PLAN})
            self.client.post("/device", data={"device_type": "PC"})
            self.client.post("/package", data={"package_type": "カスタムパック"})
            custom_page = self.client.get("/custom")
            self.assertIn('value="データ登録" data-price="0" data-quote-required="true"'.encode(), custom_page.data)
            self.assertIn("要相談".encode(), custom_page.data)
            response = self.client.post("/custom", data={
                "custom_screens": "1", "features": "データ登録",
                "feature_quantities[データ登録]": "2",
            })
            self.assertEqual(response.status_code, 302)
            estimate_id = int(response.location.rstrip("/").split("/")[-1])
            with app.app_context():
                estimate = db.session.get(Estimate, estimate_id)
                quote_item = next(item for item in estimate.items if item.is_quote_required)
                self.assertEqual(quote_item.item_name, "データ登録 x 2")
                self.assertEqual(quote_item.price_label, "要相談")
                self.assertEqual(estimate.total_price, screen_price)
                self.assertEqual(_estimate_pdf_items(estimate)[-1][-1], "要相談")
                inquiry = Inquiry(estimate=estimate, company_name="例", person_name="例", email="a@example.com")
                with db.session.no_autoflush:
                    self.assertIn("データ登録 x 2: 要相談", "\n".join(estimate_lines(inquiry)))
            result = self.client.get(response.location)
            self.assertIn("※要相談の機能は、この金額に含まれていません。".encode(), result.data)
            self.assertLess(
                result.data.index(b'class="initial-cost-quote-note"'),
                result.data.index(b'class="maintenance-option-panel"'),
            )
            self.assertIn("要相談".encode(), self.client.get(f"/inquiry/{estimate_id}").data)
            self.assertEqual(self.client.get(f"/estimate/{estimate_id}/pdf").status_code, 200)
        finally:
            with app.app_context():
                feature = db.session.get(FeatureMaster, feature_id)
                plan = db.session.get(PlanMaster, FULL_PLAN)
                feature.unit_price, feature.is_quote_required, feature.is_active, plan.is_active = original
                db.session.commit()
        with app.app_context():
            saved_estimate = db.session.get(Estimate, estimate_id)
            self.assertTrue(saved_estimate.has_quote_required_items)
            self.assertEqual(saved_estimate.total_price, screen_price)

    def test_plan_scoped_masters_and_prices(self):
        with app.app_context():
            simple = calculate_estimate("PC", "基本パック", plan_key=SIMPLE_PLAN)
            full_device = DevicePriceMaster.query.filter_by(plan_key=FULL_PLAN, name="full::PC").one()
            full_device.screen_unit_price = 30000
            db.session.commit()
            full = calculate_estimate("PC", "基本パック", plan_key=FULL_PLAN)
            self.assertEqual(full["total_price"] - simple["total_price"], 60000)
            self.assertEqual(simple["total_price"], 75000)
            self.assertEqual(
                {row.public_name for row in FeatureMaster.query.filter_by(plan_key=FULL_PLAN)},
                {row.public_name for row in FeatureMaster.query.filter_by(plan_key=SIMPLE_PLAN)},
            )

    def test_admin_can_edit_full_plan_without_changing_simple(self):
        with app.app_context():
            full_feature = FeatureMaster.query.filter_by(plan_key=FULL_PLAN, name="full::メール送信").one()
            feature_id = full_feature.id
            simple_price = FeatureMaster.query.filter_by(plan_key=SIMPLE_PLAN, name="メール送信").one().unit_price
        with self.client.session_transaction() as session:
            session["admin_logged_in"] = True
        response = self.client.post(f"/admin/masters/features/{feature_id}", data={
            "plan_key": FULL_PLAN, "name": "メール送信", "unit_price": "25000",
            "category_name": "基本機能", "is_active": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("plan=full", response.location)
        with app.app_context():
            self.assertEqual(db.session.get(FeatureMaster, feature_id).unit_price, 25000)
            self.assertEqual(FeatureMaster.query.filter_by(plan_key=SIMPLE_PLAN, name="メール送信").one().unit_price, simple_price)
        self.assertEqual(self.client.get("/admin/masters?plan=full").status_code, 200)

    def test_standard_package_name_remains_stable(self):
        with app.app_context():
            package_id = PackageMaster.query.filter_by(plan_key=FULL_PLAN, name="full::カスタムパック").one().id
        with self.client.session_transaction() as session:
            session["admin_logged_in"] = True
        response = self.client.post(f"/admin/masters/packages/{package_id}", data={
            "plan_key": FULL_PLAN, "name": "別の名前", "screen_count": "0", "is_active": "1",
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.get(PackageMaster, package_id).public_name, "カスタムパック")

    def test_custom_screen_count_accepts_only_one_to_fifty(self):
        self.client.post("/plan", data={"plan_key": SIMPLE_PLAN})
        self.client.post("/device", data={"device_type": "PC"})
        self.client.post("/package", data={"package_type": "カスタムパック"})
        for value in ("", "0", "-1", "51", "999", "1.5", "abc"):
            with self.subTest(value=value):
                response = self.client.post("/custom", data={"custom_screens": value, "features": "データ登録"})
                self.assertEqual(response.status_code, 400)
                self.assertIn("画面数は1～50の整数で入力してください。".encode(), response.data)
        for value in ("1", "50"):
            with self.subTest(value=value):
                response = self.client.post("/custom", data={"custom_screens": value, "features": "データ登録"})
                self.assertEqual(response.status_code, 302)
                estimate_id = int(response.location.rsplit("/", 1)[1])
                with app.app_context():
                    estimate = db.session.get(Estimate, estimate_id)
                    expected = calculate_estimate("PC", "カスタムパック", int(value), ["データ登録"], plan_key=SIMPLE_PLAN)
                    self.assertEqual(estimate.total_price, expected["total_price"])

    def test_feature_card_uses_its_own_master_price(self):
        with app.app_context():
            device = DevicePriceMaster.query.filter_by(plan_key=FULL_PLAN, name="full::PC").one()
            feature = FeatureMaster.query.filter_by(plan_key=FULL_PLAN, name="full::画面表示項目追加").one()
            plan = db.session.get(PlanMaster, FULL_PLAN)
            original = (device.screen_unit_price, feature.unit_price, plan.is_active)
            device.screen_unit_price = 14999
            feature.unit_price = 10001
            plan.is_active = True
            db.session.commit()
        try:
            self.client.post("/plan", data={"plan_key": FULL_PLAN})
            self.client.post("/device", data={"device_type": "PC"})
            self.client.post("/package", data={"package_type": "カスタムパック"})
            response = self.client.get("/custom")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data.count(b'class="selected-estimate-card"'), 3)
            self.assertIn(b'img/plan-full-generated.png', response.data)
            self.assertIn("<strong>しっかりアプリプラン</strong>".encode(), response.data)
            self.assertIn('value="画面表示項目追加" data-price="10001"'.encode(), response.data)
            invalid_response = self.client.post("/custom", data={"custom_screens": "0"})
            self.assertEqual(invalid_response.status_code, 400)
            self.assertIn("<strong>しっかりアプリプラン</strong>".encode(), invalid_response.data)
            with app.app_context():
                estimate = calculate_estimate("PC", "カスタムパック", 1,
                                              ["画面表示項目追加"], {"画面表示項目追加": 1}, plan_key=FULL_PLAN)
                self.assertEqual(estimate["items"][0]["price"], 14999)
                self.assertEqual(estimate["items"][1]["price"], 10001)
        finally:
            with app.app_context():
                device = DevicePriceMaster.query.filter_by(plan_key=FULL_PLAN, name="full::PC").one()
                feature = FeatureMaster.query.filter_by(plan_key=FULL_PLAN, name="full::画面表示項目追加").one()
                plan = db.session.get(PlanMaster, FULL_PLAN)
                device.screen_unit_price, feature.unit_price, plan.is_active = original
                db.session.commit()

    def test_screen_item_feature_price_can_vary_by_plan_and_device(self):
        with app.app_context():
            feature = FeatureMaster.query.filter_by(plan_key=SIMPLE_PLAN, name="画面表示項目追加").one()
            phone = DevicePriceMaster.query.filter_by(plan_key=SIMPLE_PLAN, name="スマートフォン").one()
            pc = DevicePriceMaster.query.filter_by(plan_key=SIMPLE_PLAN, name="PC").one()
            feature_id, phone_id, pc_id = feature.id, phone.id, pc.id
            common_price = feature.unit_price
            full_price = FeatureMaster.query.filter_by(plan_key=FULL_PLAN, name="full::画面表示項目追加").one().unit_price
            all_device_ids = [device.id for device in DevicePriceMaster.query.filter_by(plan_key=SIMPLE_PLAN)]
            feature_form = {
                "plan_key": SIMPLE_PLAN, "name": feature.public_name,
                "unit_price": str(common_price + 37), "sort_order": str(feature.sort_order),
                "category_name": feature.category_name or "", "description": feature.description or "",
                "condition": feature.condition or "", "icon_file": feature.icon_file or "",
                "allow_quantity": "1", "is_active": "1", "update_device_prices": "1",
                **{f"device_price[{device_id}]": "" for device_id in all_device_ids},
            }
            feature_form[f"device_price[{phone_id}]"] = "11111"
            feature_form[f"device_price[{pc_id}]"] = "22222"

        with self.client.session_transaction() as browser_session:
            browser_session["admin_logged_in"] = True
        response = self.client.post(f"/admin/masters/features/{feature_id}", data=feature_form)
        self.assertEqual(response.status_code, 302)
        try:
            admin_page = self.client.get("/admin/masters?plan=simple")
            self.assertEqual(admin_page.status_code, 200)
            self.assertIn("画面表示項目追加の端末別単価（カスタムパック）".encode(), admin_page.data)
            self.assertIn(f'data-device-price-toggle="feature-device-prices-{feature_id}"'.encode(), admin_page.data)
            self.assertIn(f'form="feature-form-{feature_id}" name="device_price[{phone_id}]"'.encode(), admin_page.data)
            self.assertIn(b'value="11111"', admin_page.data)
            with app.app_context():
                self.assertEqual(db.session.get(FeatureMaster, feature_id).unit_price, common_price + 37)
                self.assertEqual(feature_prices_for_device("スマートフォン")["画面表示項目追加"], 11111)
                self.assertEqual(feature_prices_for_device("PC")["画面表示項目追加"], 22222)
                self.assertEqual(feature_prices_for_device("スマートフォン・タブレット・PCの3タイプ対応")["画面表示項目追加"], common_price + 37)
                self.assertEqual(feature_prices_for_device("スマートフォン", FULL_PLAN)["画面表示項目追加"], full_price)
                result = calculate_estimate("スマートフォン", "カスタムパック", 1,
                                            ["画面表示項目追加"], {"画面表示項目追加": 2})
                self.assertEqual(result["items"][1], {"name": "画面表示項目追加 x 2", "price": 22222})

            self.client.post("/plan", data={"plan_key": SIMPLE_PLAN})
            self.client.post("/device", data={"device_type": "スマートフォン"})
            self.client.post("/package", data={"package_type": "カスタムパック"})
            response = self.client.get("/custom")
            self.assertEqual(response.data.count(b'class="selected-estimate-card"'), 3)
            self.assertIn(b'img/plan-simple-generated.png', response.data)
            self.assertIn("<strong>かんたんアプリプラン</strong>".encode(), response.data)
            self.assertIn('value="画面表示項目追加" data-price="11111"'.encode(), response.data)
            self.assertIn("11,111円".encode(), response.data)
            self.assertEqual(self.client.post("/custom", data={
                "custom_screens": "1", "features": "画面表示項目追加",
                "feature_quantities[画面表示項目追加]": "2",
            }).status_code, 302)
            with self.client.session_transaction() as browser_session:
                estimate_id = browser_session["estimate_flow"]["estimate_id"]
            with app.app_context():
                estimate = db.session.get(Estimate, estimate_id)
                self.assertEqual(estimate.total_price, 10000 + 22222)
                self.assertEqual(estimate.items[1].price, 22222)
            self.assertEqual(self.client.get(f"/estimate/{estimate_id}/pdf").status_code, 200)

            feature_form[f"device_price[{phone_id}]"] = ""
            response = self.client.post(f"/admin/masters/features/{feature_id}", data=feature_form)
            self.assertEqual(response.status_code, 302)
            with app.app_context():
                self.assertEqual(feature_prices_for_device("スマートフォン")["画面表示項目追加"], common_price + 37)
        finally:
            with app.app_context():
                FeatureDevicePriceMaster.query.filter_by(feature_id=feature_id).delete()
                db.session.get(FeatureMaster, feature_id).unit_price = common_price
                db.session.commit()

    def test_feature_guide_uses_selected_plan_master_price(self):
        with app.app_context():
            feature = FeatureMaster.query.filter_by(plan_key=FULL_PLAN, name="full::データ登録").one()
            plan = db.session.get(PlanMaster, FULL_PLAN)
            original = (feature.unit_price, plan.is_active)
            feature.unit_price = 23456
            plan.is_active = True
            db.session.commit()
        try:
            self.client.post("/plan", data={"plan_key": FULL_PLAN})
            self.client.post("/device", data={"device_type": "PC"})
            self.client.post("/package", data={"package_type": "カスタムパック"})
            response = self.client.get("/custom")
            self.assertIn(b'class="feature-guide-price">23,456', response.data)
        finally:
            with app.app_context():
                feature = FeatureMaster.query.filter_by(plan_key=FULL_PLAN, name="full::データ登録").one()
                plan = db.session.get(PlanMaster, FULL_PLAN)
                feature.unit_price, plan.is_active = original
                db.session.commit()

    def test_package_card_label_uses_master_screen_count(self):
        with app.app_context():
            package = PackageMaster.query.filter_by(plan_key=SIMPLE_PLAN, name="基本パック").one()
            original_count = package.screen_count
            package.screen_count = 4
            db.session.commit()
        try:
            with app.app_context():
                card = next(card for card in package_choice_cards(SIMPLE_PLAN) if card["name"] == "基本パック")
                self.assertEqual(card["price_label"], "4画面")
        finally:
            with app.app_context():
                package = PackageMaster.query.filter_by(plan_key=SIMPLE_PLAN, name="基本パック").one()
                package.screen_count = original_count
                db.session.commit()

    def test_disabled_package_display_items_do_not_reappear(self):
        with app.app_context():
            package = PackageMaster.query.filter_by(plan_key=FULL_PLAN, name="full::基本パック").one()
            items = PackageDisplayItemMaster.query.filter_by(package_id=package.id).all()
            original = [(item.id, item.is_active) for item in items]
            for item in items:
                item.is_active = False
            db.session.commit()
        try:
            with app.app_context():
                card = next(card for card in package_choice_cards(FULL_PLAN) if card["name"] == "基本パック")
                self.assertEqual(card["items"], [])
        finally:
            with app.app_context():
                for item_id, is_active in original:
                    db.session.get(PackageDisplayItemMaster, item_id).is_active = is_active
                db.session.commit()

    def test_package_feature_quantity_matches_preview_even_if_custom_quantity_disabled(self):
        with app.app_context():
            package = PackageMaster.query.filter_by(plan_key=FULL_PLAN, name="full::基本パック").one()
            feature = FeatureMaster.query.filter_by(plan_key=FULL_PLAN, name="full::データ登録").one()
            package_feature = PackageFeatureMaster.query.filter_by(package_id=package.id, feature_id=feature.id).one()
            package_id, feature_id = package.id, feature.id
            feature_price = feature.unit_price
            original = (feature.allow_quantity, package_feature.quantity)
            feature.allow_quantity = False
            package_feature.quantity = 2
            db.session.commit()
        try:
            with app.app_context():
                preview_total = package_feature_total("基本パック", "PC", FULL_PLAN)
                result = calculate_estimate("PC", "基本パック", plan_key=FULL_PLAN)
                self.assertEqual(sum(item["price"] for item in result["items"][1:]), preview_total)
                self.assertIn({"name": "データ登録 x 2", "price": feature_price * 2}, result["items"])
        finally:
            with app.app_context():
                feature = db.session.get(FeatureMaster, feature_id)
                package_feature = PackageFeatureMaster.query.filter_by(package_id=package_id, feature_id=feature_id).one()
                feature.allow_quantity, package_feature.quantity = original
                db.session.commit()

    def test_history_package_dropdown_includes_added_and_historical_packages(self):
        with app.app_context():
            package = PackageMaster(name="full::追加パック", plan_key=FULL_PLAN, screen_count=1)
            historical = Estimate(device_type="PC", package_type="廃止パック", total_price=0, plan_key=FULL_PLAN)
            db.session.add_all([package, historical])
            db.session.commit()
            package_id, historical_id = package.id, historical.id
        try:
            with self.client.session_transaction() as session:
                session["admin_logged_in"] = True
            response = self.client.get("/admin/estimates")
            self.assertIn(b'<select class="form-select" id="history-package" name="package">', response.data)
            self.assertIn('value="追加パック"'.encode(), response.data)
            self.assertIn('value="廃止パック"'.encode(), response.data)
            filtered = self.client.get("/admin/estimates", query_string={"plan": FULL_PLAN, "package": "廃止パック"})
            self.assertIn(f"#{historical_id}".encode(), filtered.data)
            self.assertIn('value="廃止パック" selected'.encode(), filtered.data)
        finally:
            with app.app_context():
                db.session.delete(db.session.get(Estimate, historical_id))
                db.session.delete(db.session.get(PackageMaster, package_id))
                db.session.commit()

    def test_public_flow_pdf_and_history_search(self):
        with app.app_context():
            db.session.get(PlanMaster, FULL_PLAN).is_active = True
            db.session.commit()
        self.assertEqual(self.client.get("/plan").status_code, 200)
        self.assertEqual(self.client.post("/plan", data={"plan_key": FULL_PLAN}).status_code, 302)
        self.client.post("/device", data={"device_type": "PC"})
        response = self.client.post("/package", data={"package_type": "基本パック"})
        self.assertEqual(response.status_code, 302)
        estimate_id = int(response.location.rstrip("/").split("/")[-1])
        result = self.client.get(response.location)
        self.assertIn("しっかりアプリプラン".encode(), result.data)
        full_inquiry = self.client.get(f"/inquiry/{estimate_id}")
        self.assertEqual(full_inquiry.status_code, 200)
        self.assertEqual(full_inquiry.data.count(b'class="inquiry-summary-card"'), 3)
        self.assertIn(b'img/plan-full-generated.png', full_inquiry.data)
        self.assertIn("<strong>しっかりアプリプラン</strong>".encode(), full_inquiry.data)
        self.assertNotIn("開発環境 Click の契約サポート".encode(), result.data)
        self.assertNotIn("開発ツールライセンス".encode(), result.data)
        self.assertEqual(self.client.get(f"/estimate/{estimate_id}/pdf").status_code, 200)
        with app.app_context():
            self.assertEqual(db.session.get(Estimate, estimate_id).plan_key, FULL_PLAN)
        self.assertEqual(self.client.post(f"/estimate/{estimate_id}/custom").status_code, 302)
        custom_response = self.client.post("/custom", data={
            "custom_screens": "1", "features": "メール送信",
            "feature_quantities[メール送信]": "1",
        })
        self.assertEqual(custom_response.status_code, 302)
        with app.app_context():
            expected = calculate_estimate("PC", "カスタムパック", 1, ["メール送信"],
                                          {"メール送信": 1}, plan_key=FULL_PLAN)
            self.assertEqual(db.session.get(Estimate, estimate_id).total_price, expected["total_price"])
        self.client.post("/plan", data={"plan_key": SIMPLE_PLAN})
        with self.client.session_transaction() as session:
            self.assertNotEqual(session["estimate_flow"]["estimate_id"], estimate_id)
        self.client.post("/device", data={"device_type": "PC"})
        simple_response = self.client.post("/package", data={"package_type": "基本パック"})
        simple_result = self.client.get(simple_response.location)
        self.assertIn("かんたんアプリプラン".encode(), simple_result.data)
        simple_id = int(simple_response.location.rstrip("/").split("/")[-1])
        simple_inquiry = self.client.get(f"/inquiry/{simple_id}")
        self.assertEqual(simple_inquiry.status_code, 200)
        self.assertEqual(simple_inquiry.data.count(b'class="inquiry-summary-card"'), 3)
        self.assertIn(b'img/plan-simple-generated.png', simple_inquiry.data)
        self.assertIn("<strong>かんたんアプリプラン</strong>".encode(), simple_inquiry.data)
        self.assertIn("開発環境 Click の契約サポート".encode(), simple_result.data)
        self.assertIn("開発ツールライセンス".encode(), simple_result.data)
        with app.app_context():
            self.assertEqual(db.session.get(Estimate, estimate_id).plan_key, FULL_PLAN)
        with self.client.session_transaction() as session:
            session["admin_logged_in"] = True
        self.assertNotIn("開発ツールライセンス".encode(), self.client.get("/admin/masters?plan=full").data)
        self.assertIn(f"#{estimate_id}".encode(), self.client.get("/admin/estimates?plan=full").data)
        self.assertIn(f"#{estimate_id}".encode(), self.client.get(f"/admin/estimates?q=%23{estimate_id}").data)
        self.assertNotIn(f"#{estimate_id}".encode(), self.client.get("/admin/estimates?plan=simple").data)


if __name__ == "__main__":
    unittest.main()
