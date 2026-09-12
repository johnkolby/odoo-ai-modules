# Copyright (c) 2026 John Kolby — Victory Technical Services
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
import datetime

from odoo.tests import common


class TestFocusDetection(common.TransactionCase):
    """The Discuss bot routes follow-up questions to the right data section."""

    def setUp(self):
        super().setUp()
        self.digest = self.env["ai.digest"]

    def test_receivables(self):
        self.assertEqual(self.digest.detect_focus("give me color on our receivables"), "receivables")

    def test_payables(self):
        self.assertEqual(self.digest.detect_focus("dig into payables"), "payables")

    def test_leads(self):
        self.assertEqual(self.digest.detect_focus("which salesperson has stale leads?"), "leads")

    def test_sales(self):
        self.assertEqual(self.digest.detect_focus("how were sales this month?"), "sales")

    def test_activities(self):
        self.assertEqual(self.digest.detect_focus("what tasks are overdue?"), "activities")

    def test_unknown_defaults_to_all(self):
        self.assertEqual(self.digest.detect_focus("how are we doing overall?"), "all")


class TestCollectStats(common.TransactionCase):
    """collect_stats must honour the calling user's record rules."""

    def setUp(self):
        super().setUp()
        self.digest = self.env["ai.digest"]
        self.today = datetime.date.today()
        self.month_start = self.today.replace(day=1)

    def test_admin_gets_all_sections(self):
        stats = self.env["ai.digest"].with_user(
            self.env.ref("base.user_admin")
        ).collect_stats(self.month_start, self.today)
        names = [s["name"] for s in stats["sections"]]
        self.assertTrue(any("receivable" in n.lower() for n in names))
        self.assertTrue(any("payable" in n.lower() for n in names))

    def test_focus_limits_sections(self):
        stats = self.digest.collect_stats(self.month_start, self.today, focus="payables")
        self.assertEqual(len(stats["sections"]), 1)
        self.assertIn("payable", stats["sections"][0]["name"].lower())

    def test_inaccessible_section_is_reported_not_raised(self):
        # A user with no accounting access must get a graceful note, not an error.
        user = self.env["res.users"].create({
            "name": "No Accounting",
            "login": "no_accounting_stats",
            "email": "noacc@example.com",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        stats = self.digest.with_user(user).collect_stats(
            self.month_start, self.today, focus="receivables"
        )
        self.assertTrue(stats["sections"])
        section = stats["sections"][0]
        # either real data or the graceful "not visible" note — never an exception
        self.assertTrue("name" in section or "note" in section)

    def test_deep_focus_adds_detail(self):
        stats = self.digest.collect_stats(self.month_start, self.today, focus="payables")
        section = stats["sections"][0]
        # deep mode adds per-bill detail keys
        self.assertIn("overdue_detail", section)
        self.assertIn("upcoming_detail", section)


class TestPersona(common.TransactionCase):
    """Answers are shaped by the asker's groups."""

    def test_admin_persona(self):
        persona = self.env["ai.digest"]._persona(self.env.ref("base.user_admin"))
        self.assertIn("administration", persona)

    def test_sales_persona(self):
        sale_grp = self.env.ref("sales_team.group_sale_salesman", raise_if_not_found=False)
        if not sale_grp:
            self.skipTest("sales_team app not installed")
        user = self.env["res.users"].create({
            "name": "Sales Person",
            "login": "sales_persona_test",
            "email": "sales@example.com",
            "groups_id": [(6, 0, [sale_grp.id])],
        })
        persona = self.env["ai.digest"]._persona(user)
        self.assertIn("sales", persona)

    def test_plain_user_persona(self):
        user = self.env["res.users"].create({
            "name": "Nobody Special",
            "login": "nobody_special_test",
            "email": "nobody@example.com",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        persona = self.env["ai.digest"]._persona(user)
        self.assertIn("general business user", persona)
