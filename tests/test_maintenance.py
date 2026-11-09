import os
import unittest
from io import BytesIO

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import app, _ensure_tracking_columns
from flask import Flask
from sqlalchemy import text
from models import db, Estimate, EstimateItem, FeatureMaster, PlanMaster, Inquiry, InquiryAttachment
from services.notification_context import estimate_lines
from services.lineworks_service import _notification_text
from services.mail_service import _admin_body, _customer_body


class MaintenanceTest(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = app.test_client()
        with app.app_context():
            self.old_active = db.session.get(PlanMaster, "full").is_active
            db.session.get(PlanMaster, "full").is_active = True
            option = FeatureMaster(name="full::サーバー保守/月", plan_key="full", unit_price=5000, is_active=True)
            db.session.add(option)
            db.session.commit()
            self.option_id = option.id

    def tearDown(self):
        with app.app_context():
            db.session.delete(db.session.get(FeatureMaster, self.option_id))
            db.session.get(PlanMaster, "full").is_active = self.old_active
            db.session.commit()

    def test_all_packages_toggle_monthly_without_changing_initial_cost(self):
        for package in ("基本パック", "運用パック", "カスタムパック"):
            self.client = app.test_client()
            self.client.post("/plan", data={"plan_key": "full"})
            self.client.post("/device", data={"device_type": "PC"})
            response = self.client.post("/package", data={"package_type": package})
            if package == "カスタムパック":
                page = self.client.get("/custom").data
                self.assertNotIn('value="サーバー保守/月"'.encode(), page)
                response = self.client.post("/custom", data={"custom_screens": "1", "features": "データ登録"})
            estimate_id = int(response.location.rsplit("/", 1)[1])
            with app.app_context():
                estimate = db.session.get(Estimate, estimate_id)
                initial = estimate.total_price
                self.assertEqual(estimate.maintenance_monthly_price, 5000)
            url = f"/estimate/{estimate_id}/maintenance"
            saved = self.client.post(url, data={"maintenance": "1"}, headers={"Accept": "application/json"})
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json, {
                "selected": True, "price_label": "5,000円／月", "available": True,
                "monthly_total_label": "8,000円～／月", "monthly_total_note": "",
            })
            with app.app_context():
                estimate = db.session.get(Estimate, estimate_id)
                self.assertEqual(estimate.total_price, initial)
                self.assertEqual(estimate.maintenance_monthly_price, 5000)
                inquiry = Inquiry(estimate=estimate, company_name="例", person_name="例", email="a@example.com")
                with db.session.no_autoflush:
                    self.assertIn("・サーバー保守: 5,000円", "\n".join(estimate_lines(inquiry)))
                    self.assertIn("月額費用: 8,000円～（税抜）", _notification_text(inquiry))
            page = self.client.get(f"/estimate/{estimate_id}").data
            self.assertLess(page.index("初期費用の合計".encode()), page.index(b'maintenance-option-form'))
            self.assertIn(b'full-plan-result-side', page)
            self.assertIn("サーバー保守（任意）".encode(), page)
            self.assertIn("サーバー保守の料金・条件・詳細を見る".encode(), page)
            self.assertIn("Google Cloud利用料（必須）".encode(), page)
            self.assertIn("3,000円～".encode(), page)
            self.assertLess(page.index("Google Cloud利用料（必須）".encode()), page.index("サーバー保守（任意）".encode()))
            self.assertIn('data-monthly-total role="status" aria-live="polite">8,000円～'.encode(), page)
            self.assertIn('class="monthly-total-tax">（税抜）'.encode(), page)
            self.assertLess(page.index("月額費用の合計".encode()), page.index('class="monthly-breakdown-title">内訳'.encode()))
            self.assertLess(page.index('class="monthly-breakdown-title">内訳'.encode()), page.index("Google Cloud利用料（必須）".encode()))
            self.assertLess(page.index("月額費用の合計".encode()), page.index("お見積りに含まれる作業".encode()))
            self.assertLess(page.index("お見積りに含まれる作業".encode()), page.index("別途かかる費用".encode()))
            self.assertIn("外部AIサービスを利用する場合、利用料が別途必要です。".encode(), page)
            maintenance_row = page.split("サーバー保守（任意）".encode(), 1)[1].split(b"</label>", 1)[0]
            self.assertNotIn("（税抜）".encode(), maintenance_row)
            monthly_panel = page.split(b'class="maintenance-option-panel"', 1)[1].split(b'class="included-work-note"', 1)[0]
            self.assertNotIn("／月".encode(), monthly_panel)
            inquiry_page = self.client.get(f"/inquiry/{estimate_id}").data
            self.assertIn('data-monthly-total>8,000円～'.encode(), inquiry_page)
            self.assertIn("Google Cloud利用料（必須）".encode(), inquiry_page)
            self.assertNotIn("／月".encode(), inquiry_page)
            pdf = self.client.get(f"/estimate/{estimate_id}/pdf")
            self.assertEqual(pdf.status_code, 200)
            self.assertIn(b"/FontFile2", pdf.data)
            removed = self.client.post(url, data={}, headers={"Accept": "application/json"})
            self.assertEqual(removed.status_code, 200)
            self.assertFalse(removed.json["selected"])
            self.assertEqual(removed.json["monthly_total_label"], "3,000円～／月")
            self.assertEqual(removed.json["monthly_total_note"], "")
            with app.app_context():
                self.assertIsNone(db.session.get(Estimate, estimate_id).maintenance_monthly_price)
                self.assertEqual(db.session.get(Estimate, estimate_id).total_price, initial)
            unchecked_page = self.client.get(f"/estimate/{estimate_id}").data
            self.assertIn("Google Cloud利用料（必須）".encode(), unchecked_page)
            self.assertIn('data-monthly-total role="status" aria-live="polite">3,000円～'.encode(), unchecked_page)

    def test_unchecked_choice_survives_recalculation_and_simple_has_no_default(self):
        self.client.post("/plan", data={"plan_key": "full"})
        self.client.post("/device", data={"device_type": "PC"})
        response = self.client.post("/package", data={"package_type": "基本パック"})
        estimate_id = int(response.location.rsplit("/", 1)[1])
        self.client.post(f"/estimate/{estimate_id}/maintenance", data={})
        self.client.post("/package", data={"package_type": "運用パック"})
        with app.app_context():
            self.assertIsNone(db.session.get(Estimate, estimate_id).maintenance_monthly_price)
        self.client.post("/plan", data={"plan_key": "simple"})
        self.client.post("/device", data={"device_type": "PC"})
        response = self.client.post("/package", data={"package_type": "基本パック"})
        simple_id = int(response.location.rsplit("/", 1)[1])
        with app.app_context():
            self.assertIsNone(db.session.get(Estimate, simple_id).maintenance_monthly_price)

    def test_monthly_total_shows_quote_required_maintenance_separately(self):
        with app.app_context():
            db.session.get(FeatureMaster, self.option_id).is_quote_required = True
            db.session.commit()
        self.client.post("/plan", data={"plan_key": "full"})
        self.client.post("/device", data={"device_type": "PC"})
        response = self.client.post("/package", data={"package_type": "基本パック"})
        estimate_id = int(response.location.rsplit("/", 1)[1])
        page = self.client.get(f"/estimate/{estimate_id}").data
        self.assertIn('data-monthly-total role="status" aria-live="polite">3,000円～'.encode(), page)
        self.assertIn("サーバー保守は要相談のため、合計に含みません。".encode(), page)
        selected = self.client.post(f"/estimate/{estimate_id}/maintenance", data={"maintenance": "1"}, headers={"Accept": "application/json"})
        self.assertEqual(selected.json["monthly_total_note"], "サーバー保守は要相談のため、合計に含みません。")
        removed = self.client.post(f"/estimate/{estimate_id}/maintenance", data={}, headers={"Accept": "application/json"})
        self.assertEqual(removed.json["monthly_total_label"], "3,000円～／月")
        self.assertEqual(removed.json["monthly_total_note"], "")

    def test_maintenance_condition_button_shows_master_condition(self):
        with app.app_context():
            option = db.session.get(FeatureMaster, self.option_id)
            option.condition = "本番環境1つの稼働確認を行います。"
            option.description = "稼働状況を確認します。"
            db.session.commit()
        self.client.post("/plan", data={"plan_key": "full"})
        self.client.post("/device", data={"device_type": "PC"})
        response = self.client.post("/package", data={"package_type": "基本パック"})
        estimate_id = int(response.location.rsplit("/", 1)[1])
        page = self.client.get(f"/estimate/{estimate_id}").data
        self.assertIn('data-maintenance-detail-trigger'.encode(), page)
        self.assertIn('class="feature-detail-popover" id="maintenanceDetailPopover"'.encode(), page)
        self.assertIn('data-maintenance-detail-price'.encode(), page)
        self.assertIn("本番環境1つの稼働確認を行います。".encode(), page)
        self.assertIn("稼働状況を確認します。".encode(), page)

    def test_admin_and_notifications_share_monthly_costs(self):
        cases = [
            ("full", 5000, False, "8,000円～"),
            ("full", None, False, "3,000円～"),
            ("full", 0, True, "3,000円～"),
            ("simple", None, False, None),
        ]
        with self.client.session_transaction() as browser_session:
            browser_session["admin_logged_in"] = True
        for plan, maintenance, quote, total in cases:
            with self.subTest(plan=plan, maintenance=maintenance, quote=quote):
                with app.test_request_context():
                    estimate = Estimate(plan_key=plan, device_type="PC", package_type="基本パック",
                                        total_price=165000, maintenance_monthly_price=maintenance,
                                        maintenance_quote_required=quote)
                    inquiry = Inquiry(estimate=estimate, company_name="費用表示確認", person_name="担当",
                                      email="cost@example.com")
                    db.session.add(inquiry)
                    db.session.commit()
                    inquiry_id = inquiry.id
                    estimate_id = estimate.id
                    admin_body = _admin_body(inquiry)
                    self.assertIn("初期費用：165,000円（税抜・概算）", admin_body)
                    self.assertNotIn("月額費用について", admin_body)
                    self.assertNotIn("Google Cloud利用料", admin_body)
                    if total is None:
                        self.assertNotIn("月額費用：", admin_body)
                    else:
                        self.assertIn(f"月額費用：{total}（税抜・概算）", admin_body)
                    self.assertEqual("※ 要相談の機能があります" in admin_body, quote)
                    customer = _customer_body(inquiry)
                    self.assertIn("初期費用：165,000円（税抜・概算）", customer)
                    self.assertIn("【お見積り内容】", customer)
                    self.assertIn("【費用】", customer)
                    self.assertIn("【見積項目】", customer)
                    self.assertIn("【お問い合わせ内容】", customer)
                    if total is None:
                        self.assertNotIn("月額費用：", customer)
                        self.assertNotIn("Google Cloud", customer)
                    else:
                        self.assertIn(f"月額費用：{total}（税抜・概算）", customer)
                        self.assertIn("・Google Cloud利用料：月額3,000円（税抜・概算）", customer)
                        if maintenance is None:
                            self.assertIn("※サーバー保守は含まれていません。", customer)
                            self.assertNotIn("・サーバー保守：", customer)
                        elif quote:
                            self.assertIn("・サーバー保守：要相談", customer)
                            self.assertIn("※サーバー保守は要相談のため、合計に含みません。", customer)
                            self.assertNotIn("月額0円", customer)
                        else:
                            self.assertIn("・サーバー保守：月額5,000円（税抜）", customer)
                    notification = _notification_text(inquiry)
                    expected_cost = "概算費用\n初期費用: 165,000円（税抜）"
                    if total is not None:
                        expected_cost += f"\n月額費用: {total}（税抜）"
                    if quote:
                        expected_cost += "\n※要相談の機能があります。"
                    self.assertIn(expected_cost + "\n\n問い合わせ内容:", notification)
                    self.assertNotIn("■概算費用", notification)
                    self.assertNotIn("月額費用について", notification)
                    self.assertNotIn("Google Cloud利用料", notification)
                    self.assertNotIn("為替", notification)
                    self.assertEqual("※要相談の機能があります。" in notification, quote)
                inquiry_pages = [
                    self.client.get(f"/inquiry/{estimate_id}"),
                    self.client.post(f"/inquiry/{estimate_id}", data={}),
                    self.client.post(f"/inquiry/{estimate_id}", data={
                        "company_name": "確認", "person_name": "担当", "email": "cost@example.com",
                        "privacy_consent": "1", "attachment": (BytesIO(b"invalid"), "invalid.exe"),
                    }),
                ]
                self.assertEqual([page.status_code for page in inquiry_pages], [200, 400, 400])
                for page in inquiry_pages:
                    if total is None:
                        self.assertNotIn("月額費用の合計".encode(), page.data)
                    else:
                        self.assertIn(f'data-monthly-total>{total}'.encode(), page.data)
                        self.assertIn("Google Cloud利用料（必須）".encode(), page.data)
                        if maintenance is None:
                            self.assertIn("サーバー保守は含まれていません。".encode(), page.data)
                            self.assertNotIn("サーバー保守（任意）".encode(), page.data)
                        elif quote:
                            self.assertIn("サーバー保守は要相談のため、合計に含みません。".encode(), page.data)
                history = self.client.get("/admin/estimates", query_string={"q": f"#{estimate_id}"})
                self.assertEqual(history.status_code, 200)
                if total is None:
                    self.assertNotIn(b'monthly-items-detail', history.data)
                else:
                    self.assertIn(b'<details class="estimate-items-detail monthly-items-detail mt-2">', history.data)
                    breakdown = history.data.split(b'monthly-items-detail', 1)[1].split(b'</details>', 1)[0]
                    self.assertIn("Google Cloud利用料".encode(), breakdown)
                    self.assertIn("3,000円～".encode(), breakdown)
                    if maintenance is None:
                        self.assertIn("サーバー保守は含まれていません。".encode(), breakdown)
                        self.assertNotIn("5,000円".encode(), breakdown)
                    elif quote:
                        self.assertIn("＋要相談".encode(), breakdown)
                        self.assertIn("サーバー保守は要相談のため、合計に含みません。".encode(), breakdown)
                    else:
                        self.assertIn("5,000円".encode(), breakdown)
                detail = self.client.get(f"/admin/inquiries/{inquiry_id}")
                self.assertEqual(detail.status_code, 200)
                if total is None:
                    self.assertNotIn("Google Cloud利用料".encode(), detail.data)
                else:
                    self.assertIn(total.encode(), detail.data)
                    self.assertIn("Google Cloud利用料：3,000円～".encode(), detail.data)
                    for path in ("/admin/estimates", "/admin/inquiries"):
                        listing = self.client.get(path)
                        self.assertEqual(listing.status_code, 200)
                        self.assertIn(f"月額費用：{total}（税抜）".encode(), listing.data)

    def test_admin_mail_matches_requested_format_and_keeps_attachment_links(self):
        with app.test_request_context(base_url="http://127.0.0.1:5000"):
            estimate = Estimate(id=133, plan_key="full", device_type="PC", package_type="カスタムパック",
                                total_price=10000, maintenance_monthly_price=5000,
                                maintenance_quote_required=False)
            estimate.items = [EstimateItem(item_name="PC 画面単価 x 1画面", price=10000, is_quote_required=False),
                              EstimateItem(item_name="ユーザー権限追加", price=0, is_quote_required=True)]
            inquiry = Inquiry(id=10, estimate=estimate, company_name="サンプル株式会社", person_name="test",
                              email="test@example.com", phone="12345678901")
            with db.session.no_autoflush:
                body = _admin_body(inquiry)
            expected = """お問い合わせ・詳細見積りの依頼を受け付けました。

管理画面：http://127.0.0.1:5000/admin/inquiries/10

【お客様情報】
会社名：サンプル株式会社
担当者名：test
メール：test@example.com
電話番号：12345678901

【お見積り内容】
受付番号：#10
見積ID：#133
プラン：しっかりアプリプラン
利用端末：PC
パック：カスタムパック

【費用】
初期費用：10,000円（税抜・概算）
月額費用：8,000円～（税抜・概算）
※ 要相談の機能があります

【見積項目】
・PC × 1画面：10,000円
・ユーザー権限追加：要相談

添付ファイル：なし"""
            self.assertEqual(body, expected)
            inquiry.attachments.append(InquiryAttachment(file_name="spec.pdf", box_url="https://example.com/spec"))
            with db.session.no_autoflush:
                attached_body = _admin_body(inquiry)
            self.assertIn("添付ファイル：\n- spec.pdf", attached_body)
            self.assertIn("https://example.com/spec", attached_body)

    def test_customer_mail_uses_inquiry_data_and_requested_sections(self):
        with app.test_request_context():
            estimate = Estimate(id=131, plan_key="full", device_type="PC", package_type="カスタムパック",
                                total_price=282000, maintenance_monthly_price=5000,
                                maintenance_quote_required=False)
            estimate.items = [EstimateItem(item_name="データ登録", price=10000, is_quote_required=False),
                              EstimateItem(item_name="外部連携", price=0, is_quote_required=True)]
            inquiry = Inquiry(id=9, estimate=estimate, company_name="確認", person_name="山田太郎",
                              email="cost@example.com", message="帳票の形式を相談したいです。")
            with db.session.no_autoflush:
                body = _customer_body(inquiry)
            self.assertTrue(body.startswith("山田太郎様\n\nお問い合わせ・詳細見積りをご依頼いただき、ありがとうございます。"))
            self.assertIn("受付番号：#9\n見積ID：#131", body)
            self.assertIn("プラン：しっかりアプリプラン\n利用端末：PC\nパック：カスタムパック", body)
            self.assertIn("初期費用：282,000円（税抜・概算）", body)
            self.assertIn("月額費用：8,000円～（税抜・概算）", body)
            self.assertIn("※要相談の機能は、初期費用に含まれていません。", body)
            self.assertIn("【見積項目】\n・データ登録：10,000円\n・外部連携：要相談", body)
            self.assertIn("【お問い合わせ内容】\n帳票の形式を相談したいです。", body)
            self.assertLess(body.index("【費用】"), body.index("【見積項目】"))
            self.assertLess(body.index("【見積項目】"), body.index("【お問い合わせ内容】"))
            self.assertTrue(body.endswith(f"{app.config['COMPANY_NAME']}\n電話番号: {app.config['COMPANY_PHONE']}\nメール: {app.config['COMPANY_EMAIL']}"))

    def test_lineworks_quote_feature_note_follows_costs(self):
        with app.test_request_context():
            estimate = Estimate(id=99999, plan_key="full", device_type="PC", package_type="基本パック",
                                total_price=10000, maintenance_monthly_price=5000,
                                maintenance_quote_required=False)
            estimate.items.append(EstimateItem(item_name="要相談機能", price=0, is_quote_required=True))
            inquiry = Inquiry(id=99999, estimate=estimate, company_name="確認", person_name="担当",
                              email="cost@example.com")
            with db.session.no_autoflush:
                body = _notification_text(inquiry)
            self.assertIn("概算費用\n初期費用: 10,000円（税抜）\n月額費用: 8,000円～（税抜）\n※要相談の機能があります。\n\n", body)
            self.assertNotIn("初期費用に含まれていません", body)

    def test_price_snapshot_ownership_and_sent_inquiry(self):
        self.client.post("/plan", data={"plan_key": "full"})
        self.client.post("/device", data={"device_type": "PC"})
        response = self.client.post("/package", data={"package_type": "基本パック"})
        estimate_id = int(response.location.rsplit("/", 1)[1])
        url = f"/estimate/{estimate_id}/maintenance"
        self.client.post(url, data={"maintenance": "1"})
        with app.app_context():
            db.session.get(FeatureMaster, self.option_id).unit_price = 9999
            db.session.commit()
        self.client.post(url, data={"maintenance": "1"})
        with app.app_context():
            self.assertEqual(db.session.get(Estimate, estimate_id).maintenance_monthly_price, 5000)
            db.session.add(Inquiry(estimate_id=estimate_id, company_name="例", person_name="例", email="a@example.com"))
            db.session.commit()
        self.assertEqual(self.client.post(url, data={}).status_code, 409)
        self.assertEqual(app.test_client().post(url, data={"maintenance": "1"}).status_code, 404)

    def test_legacy_transfer_runs_once(self):
        isolated = Flask("legacy-test")
        isolated.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        db.init_app(isolated)
        with isolated.app_context():
            db.session.execute(text("CREATE TABLE estimates (id INTEGER PRIMARY KEY, total_price INTEGER, plan_key VARCHAR(20))"))
            db.session.execute(text("CREATE TABLE estimate_items (id INTEGER PRIMARY KEY, estimate_id INTEGER, item_name TEXT, price INTEGER, is_quote_required BOOLEAN)"))
            db.session.execute(text("INSERT INTO estimates VALUES (1, 25000, 'full')"))
            db.session.execute(text("INSERT INTO estimate_items VALUES (1, 1, 'サーバー保守/月', 5000, FALSE)"))
            db.session.commit()
            _ensure_tracking_columns()
            _ensure_tracking_columns()
            row = db.session.execute(text("SELECT total_price, maintenance_monthly_price FROM estimates")).one()
            self.assertEqual(tuple(row), (20000, 5000))
            self.assertEqual(db.session.execute(text("SELECT COUNT(*) FROM estimate_items")).scalar(), 0)


if __name__ == "__main__":
    unittest.main()
