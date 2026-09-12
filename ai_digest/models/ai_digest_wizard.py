# Copyright (c) 2026 John Kolby — Victory Technical Services
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo import api, fields, models
from odoo.exceptions import AccessError


class AiDigestWizard(models.TransientModel):
    _name = "ai.digest.wizard"
    _description = "AI Digest Wizard"

    date_from = fields.Date(string="From", required=True)
    date_to = fields.Date(string="To", required=True)
    summary = fields.Text(string="AI Summary", readonly=True)
    stats_json = fields.Text(string="Collected stats", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault("date_to", today)
        res.setdefault("date_from", fields.Date.add(today, days=-30))
        return res

    def action_generate(self):
        self.ensure_one()
        if not self.env.user.has_group("ai_digest.group_ai_user"):
            raise AccessError("You are not allowed to run AI digests.")
        # collect_stats + build_summary run AS self.env.user:
        # record rules and access rights apply, per-user permission scoping.
        stats = self.env["ai.digest"].collect_stats(self.date_from, self.date_to)
        import json

        summary = self.env["ai.digest"].build_summary(self.date_from, self.date_to)
        self.write({"summary": summary, "stats_json": json.dumps(stats, indent=2, default=str)})
        return {
            "type": "ir.actions.act_window",
            "res_model": "ai.digest.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
