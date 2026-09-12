# Victory Technical Services
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo.exceptions import AccessError
from odoo.tests import common


class TestWizardGroupGate(common.TransactionCase):
    """Only users in the AI Digest group may run digests."""

    def setUp(self):
        super().setUp()
        self.plain_user = self.env["res.users"].create({
            "name": "Plain User",
            "login": "plain_digest_user",
            "email": "plain@example.com",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        self.gated_user = self.env["res.users"].create({
            "name": "Gated User",
            "login": "gated_digest_user",
            "email": "gated@example.com",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("ai_digest.group_ai_user").id,
            ])],
        })

    def test_plain_user_cannot_create_wizard(self):
        with self.assertRaises(AccessError):
            self.env["ai.digest.wizard"].with_user(self.plain_user).create({
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
            })

    def test_gated_user_can_create_wizard(self):
        wizard = self.env["ai.digest.wizard"].with_user(self.gated_user).create({
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        })
        self.assertTrue(wizard.exists())


class TestBotAuthorization(common.TransactionCase):
    """The channel bot must refuse users outside the group."""

    def test_unauthorized_user_gets_refusal_text(self):
        plain_user = self.env["res.users"].create({
            "name": "Bot Outsider",
            "login": "bot_outsider",
            "email": "outsider@example.com",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        msg = self.env["mail.message"].create({
            "model": "mail.channel",
            "res_id": 0,  # not a real channel; _process_question never posts here
            "message_type": "comment",
            "body": "<p>?ai dig into payables</p>",
            "author_id": plain_user.partner_id.id,
        })
        reply = self.env["ai.digest"]._process_question(msg, "dig into payables")
        self.assertIn("not authorized", reply.lower())
