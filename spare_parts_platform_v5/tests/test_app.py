from __future__ import annotations

import importlib
import os
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


class UserFacingTextParser(HTMLParser):
    translated_attributes = {
        "placeholder", "aria-label", "title", "alt", "data-confirm",
        "data-show-label", "data-hide-label",
    }

    def __init__(self):
        super().__init__()
        self.fragments = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored_depth += 1
            return
        if not self.ignored_depth:
            self.fragments.extend(value for name, value in attrs if name in self.translated_attributes and value)

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data):
        if not self.ignored_depth and data.strip():
            self.fragments.append(data)


class PlatformFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        db_path = (Path(cls.temp_dir.name) / "test.db").as_posix()
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["SECRET_KEY"] = "test-secret"
        project_root = str(Path(__file__).resolve().parents[1])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        cls.module = importlib.import_module("app")
        cls.app = cls.module.app
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.module.db.session.remove()
            cls.module.db.engine.dispose()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.client.get("/login")
        self.login()

    def token(self, client=None):
        client = client or self.client
        with client.session_transaction() as sess:
            return sess["csrf_token"]

    def login(self, username="admin", password="Admin123!", client=None):
        client = client or self.client
        response = client.post(
            "/login",
            data={"username": username, "password": password, "csrf_token": self.token(client)},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("数据驾驶舱", response.get_data(as_text=True))

    def test_all_main_pages_render(self):
        for route in ["/", "/parts", "/equipment", "/suppliers", "/procurement", "/inbound", "/stock", "/faults", "/lifecycle", "/disposals", "/users", "/fault-report", "/fault-report/qr.png"]:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
        response = self.client.get("/parts?q=YEJ8024")
        self.assertEqual(response.status_code, 200)
        self.assertIn("YEJ8024", response.get_data(as_text=True))
        faults = self.client.get("/faults").get_data(as_text=True)
        self.assertIn("本月损管比", faults)
        self.assertIn("本年度损管比", faults)

    def test_qr_code_uses_public_https_scan_entry(self):
        previous_base_url = self.module.PUBLIC_BASE_URL
        try:
            self.module.PUBLIC_BASE_URL = "https://lwqgraduationproject.cn"
            response = self.client.get("/fault-report/qr.png?lang=en")
        finally:
            self.module.PUBLIC_BASE_URL = previous_base_url
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(
            response.headers["X-QR-Target"],
            "https://lwqgraduationproject.cn/scan/fault?lang=en",
        )
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertGreater(len(response.data), 500)

    def test_scan_entry_opens_public_form_and_tracks_submission(self):
        public_client = self.app.test_client()
        response = public_client.get("/scan/fault?lang=en", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Mobile Equipment Fault Reporting", response.get_data(as_text=True))
        self.assertIn('name="source" value="qr"', response.get_data(as_text=True))
        with public_client.session_transaction() as sess:
            token = sess["csrf_token"]
        with self.app.app_context():
            equipment_id = self.module.Equipment.query.first().id
        response = public_client.post(
            "/fault-report?source=qr",
            data={
                "csrf_token": token,
                "source": "qr",
                "equipment_id": equipment_id,
                "reporter": "QR Test",
                "contact": "10086",
                "description": "QR end-to-end test",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Work Order No.", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertIsNotNone(
                self.module.FaultReport.query.filter_by(reporter="QR Test").first()
            )
            audit_item = self.module.AuditLog.query.order_by(
                self.module.AuditLog.id.desc()
            ).first()
            self.assertIn("扫码入口", audit_item.detail)

    def test_language_switch(self):
        response = self.client.get("/language/en", follow_redirects=True)
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dashboard", body)
        self.assertIn("Spare Parts Hub", body)
        self.assertIn('<div class="brand-mark">S</div>', body)
        for initial in ["E", "P", "S", "I", "F", "D", "L", "U"]:
            self.assertIn(f'<span class="nav-icon">{initial}</span>', body)
        self.assertIn('<span class="metric-icon">P</span>', body)
        self.assertNotIn('<span class="metric-icon">库</span>', body)
        self.assertEqual(self.module.EN_TRANSLATIONS["备件"], "Spare Part")
        self.assertEqual(self.module.EN_TRANSLATIONS["设备故障移动提报"], "Mobile Equipment Fault Reporting")
        self.assertEqual(self.module.EN_TRANSLATIONS["密码须至少 8 位，并同时包含大写字母、小写字母、数字和特殊字符。"], "Password must contain at least 8 characters, including uppercase and lowercase letters, a number and a special character.")
        app_js = (Path(__file__).resolve().parents[1] / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("orderedTranslations", app_js)
        self.assertIn("[placeholder], [aria-label], [title], [alt], [data-confirm]", app_js)
        response = self.client.get("/language/zh", follow_redirects=True)
        self.assertIn("数据驾驶舱", response.get_data(as_text=True))

    def assert_no_user_facing_chinese(self, response, route):
        parser = UserFacingTextParser()
        parser.feed(response.get_data(as_text=True))
        residue = sorted({fragment.strip() for fragment in parser.fragments if re.search(r"[\u3400-\u9fff]", fragment)})
        self.assertEqual(residue, [], f"Chinese residue at {route}: {residue}")

    def test_00_server_side_english_is_complete_without_javascript(self):
        self.client.get("/language/en", follow_redirects=True)
        protected_routes = [
            "/", "/parts", "/equipment", "/suppliers", "/procurement", "/inbound",
            "/stock", "/faults", "/lifecycle", "/disposals", "/users", "/fault-report",
        ]
        for route in protected_routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assert_no_user_facing_chinese(response, route)
                self.assertEqual(response.headers.get("Cache-Control"), "no-store, no-cache, must-revalidate, max-age=0")

        public_client = self.app.test_client()
        public_client.get("/language/en", follow_redirects=True)
        for route in ["/login", "/register", "/fault-report", "/not-a-real-page"]:
            with self.subTest(route=route):
                response = public_client.get(route)
                self.assert_no_user_facing_chinese(response, route)
        self.client.get("/language/zh", follow_redirects=True)

    def test_login_v3_controls_and_demo_input_normalization(self):
        client = self.app.test_client()
        login_page = client.get("/login").get_data(as_text=True)
        self.assertIn("data-toggle-password", login_page)
        self.assertIn("data-demo-login", login_page)
        self.assertIn('autocomplete="off"', login_page)
        response = client.post(
            "/login",
            data={
                "username": " admin ",
                "password": "  Admin123！  ",
                "csrf_token": self.token(client),
            },
            follow_redirects=True,
        )
        self.assertIn("数据驾驶舱", response.get_data(as_text=True))

    def test_login_v3_precise_failure_messages(self):
        missing_client = self.app.test_client()
        missing_client.get("/login")
        response = missing_client.post(
            "/login",
            data={"username": "missing_user", "password": "Wrong123!", "csrf_token": self.token(missing_client)},
            follow_redirects=True,
        )
        self.assertIn("用户名不存在", response.get_data(as_text=True))
        wrong_client = self.app.test_client()
        wrong_client.get("/login")
        response = wrong_client.post(
            "/login",
            data={"username": "admin", "password": "Wrong123!", "csrf_token": self.token(wrong_client)},
            follow_redirects=True,
        )
        self.assertIn("密码不正确", response.get_data(as_text=True))

    def test_registration_requires_admin_approval(self):
        public_client = self.app.test_client()
        public_client.get("/register")
        response = public_client.post(
            "/register",
            data={
                "csrf_token": self.token(public_client),
                "username": "new_worker",
                "display_name": "新员工",
                "department": "生产运行部",
                "role": "worker",
                "password": "NewWorker123!",
                "confirm_password": "NewWorker123!",
            },
            follow_redirects=True,
        )
        self.assertIn("注册申请已提交", response.get_data(as_text=True))
        with self.app.app_context():
            user = self.module.User.query.filter_by(username="new_worker").one()
            self.assertFalse(user.active)
            user_id = user.id
        response = self.client.post(
            f"/users/{user_id}/update",
            data={"csrf_token": self.token(), "role": "worker", "active": "yes"},
            follow_redirects=True,
        )
        self.assertIn("已更新", response.get_data(as_text=True))
        approved_client = self.app.test_client()
        approved_client.get("/login")
        self.login("new_worker", "NewWorker123!", approved_client)

    def test_role_permissions(self):
        cases = [
            ("worker", "Worker123!", "/equipment", "/stock"),
            ("warehouse", "Warehouse123!", "/stock", "/faults"),
            ("maintenance", "Maintenance123!", "/faults", "/procurement"),
            ("procurement", "Procurement123!", "/procurement", "/faults"),
            ("manager", "Manager123!", "/stock", "/users"),
            ("executive", "Executive123!", "/lifecycle", "/users"),
        ]
        for username, password, allowed, forbidden in cases:
            with self.subTest(username=username):
                client = self.app.test_client()
                client.get("/login")
                self.login(username, password, client)
                self.assertEqual(client.get(allowed).status_code, 200)
                self.assertEqual(client.get(forbidden).status_code, 403)

    def test_public_error_and_favicon(self):
        public_client = self.app.test_client()
        self.assertEqual(public_client.get("/favicon.ico").status_code, 204)
        self.assertEqual(public_client.get("/not-a-real-page").status_code, 404)

    def test_end_to_end_business_flow(self):
        m = self.module
        with self.app.app_context():
            low_part = m.Part.query.filter(m.Part.stock < m.Part.min_stock).first()
            supplier = m.Supplier.query.first()
            equipment = m.Equipment.query.first()
            original_stock = low_part.stock
            low_part_id = low_part.id
            supplier_id = supplier.id
            equipment_id = equipment.id

        response = self.client.post(
            "/procurement/generate", data={"csrf_token": self.token()}, follow_redirects=True
        )
        self.assertIn("采购需求", response.get_data(as_text=True))
        with self.app.app_context():
            procurement = m.Procurement.query.filter_by(part_id=low_part_id).first()
            self.assertIsNotNone(procurement)
            procurement_id = procurement.id

        response = self.client.post(
            f"/procurement/{procurement_id}/approve",
            data={"csrf_token": self.token()},
            follow_redirects=True,
        )
        self.assertIn("已批准", response.get_data(as_text=True))

        response = self.client.post(
            "/inbound",
            data={
                "csrf_token": self.token(),
                "part_id": low_part_id,
                "supplier_id": supplier_id,
                "quantity": 5,
                "unit_price": 238,
                "manufacturer": "测试制造厂",
            },
            follow_redirects=True,
        )
        self.assertIn("入库成功", response.get_data(as_text=True))
        with self.app.app_context():
            part = m.db.session.get(m.Part, low_part_id)
            self.assertEqual(part.stock, original_stock + 5)

        response = self.client.post(
            "/stock",
            data={
                "csrf_token": self.token(),
                "part_id": low_part_id,
                "actual_stock": original_stock + 4,
                "stocktake_type": "日常抽盘",
                "reason": "测试盘点差异",
            },
            follow_redirects=True,
        )
        self.assertIn("已纠错", response.get_data(as_text=True))

        response = self.client.post(
            "/faults",
            data={
                "csrf_token": self.token(),
                "equipment_id": equipment_id,
                "reporter": "测试人员",
                "contact": "1001",
                "description": "测试故障：设备异响",
            },
            follow_redirects=True,
        )
        self.assertIn("已提报", response.get_data(as_text=True))
        with self.app.app_context():
            fault = m.FaultReport.query.filter_by(reporter="测试人员").first()
            lifecycle_before = m.Lifecycle.query.count()
            fault_id = fault.id

        response = self.client.post(
            f"/faults/{fault_id}/process",
            data={
                "csrf_token": self.token(),
                "handling": "更换损坏备件并试机",
                "need_replacement": "yes",
                "part_id": low_part_id,
                "quantity": 1,
                "old_part_value": "有价值",
            },
            follow_redirects=True,
        )
        self.assertIn("寿命档案已联动更新", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(m.Lifecycle.query.count(), lifecycle_before + 1)
            self.assertEqual(m.db.session.get(m.FaultReport, fault_id).status, "已完成")
            self.assertIsNotNone(m.Disposal.query.filter_by(part_id=low_part_id).first())

        for kind in ["stock", "warnings", "procurement"]:
            response = self.client.get(f"/export/{kind}.csv")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/csv", response.content_type)


if __name__ == "__main__":
    unittest.main(verbosity=2)
