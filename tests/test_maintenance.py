import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import app, _ensure_tracking_columns
from flask import Flask
from sqlalchemy import text
from models import db, Estimate, FeatureMaster, PlanMaster, Inquiry
from services.notification_context import estimate_lines
from services.lineworks_service import _notification_text


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
            self.assertEqual(saved.json, {"selected": True, "price_label": "5,000円／月", "available": True})
            with app.app_context():
                estimate = db.session.get(Estimate, estimate_id)
                self.assertEqual(estimate.total_price, initial)
                self.assertEqual(estimate.maintenance_monthly_price, 5000)
                inquiry = Inquiry(estimate=estimate, company_name="例", person_name="例", email="a@example.com")
                with db.session.no_autoflush:
                    self.assertIn("5,000円／月", "\n".join(estimate_lines(inquiry)))
                    self.assertIn("5,000円／月", _notification_text(inquiry))
            page = self.client.get(f"/estimate/{estimate_id}").data
            self.assertLess(page.index("初期費用の合計".encode()), page.index(b'maintenance-option-form'))
            self.assertIn("5,000円／月".encode(), self.client.get(f"/inquiry/{estimate_id}").data)
            pdf = self.client.get(f"/estimate/{estimate_id}/pdf")
            self.assertEqual(pdf.status_code, 200)
            self.assertIn(b"/FontFile2", pdf.data)
            removed = self.client.post(url, data={}, headers={"Accept": "application/json"})
            self.assertEqual(removed.status_code, 200)
            self.assertFalse(removed.json["selected"])
            with app.app_context():
                self.assertIsNone(db.session.get(Estimate, estimate_id).maintenance_monthly_price)
                self.assertEqual(db.session.get(Estimate, estimate_id).total_price, initial)

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
