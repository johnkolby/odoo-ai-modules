# Victory Technical Services
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
import json
import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext, plaintext2html
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)


class AiDigest(models.AbstractModel):
    """Core digest logic. IMPORTANT PERMISSION NOTE:

    Every stat is collected with ``self.env`` — the *calling* user's
    environment. Odoo applies ir.model.access and ir.rule (record rules)
    automatically on search(), so a user can never trigger an AI summary
    over records they cannot read. Never replace these searches with
    sudo() unless you deliberately want an org-wide admin digest.
    """

    _name = "ai.digest"
    _description = "AI Business Digest (service model)"

    # ------------------------------------------------------------------
    # Data collection (runs AS the current user)
    # ------------------------------------------------------------------

    @api.model
    def collect_stats(self, date_from, date_to, focus="all"):
        """focus: all | receivables | payables | sales | leads | activities.
        A specific focus collects ONLY that section, with deep detail."""
        today = fields.Date.context_today(self)
        stats = {
            "period": {"from": str(date_from), "to": str(date_to)},
            "focus": focus,
            "sections": [],
        }

        deep = focus != "all"

        def want(key):
            return focus == "all" or focus == key

        if "account.move" in self.env:
            if want("receivables"):
                stats["sections"].append(self._safe(self._receivables, today, deep=deep))
            if want("payables"):
                stats["sections"].append(self._safe(self._payables, today, deep=deep))

        if "sale.order" in self.env and want("sales"):
            stats["sections"].append(self._safe(self._sales, date_from, date_to, deep=deep))

        if "crm.lead" in self.env and want("leads"):
            stats["sections"].append(self._safe(self._leads, today, deep=deep))

        if want("activities") or focus == "all":
            stats["sections"].append(self._safe(self._my_overdue_activities, today, deep=deep))
        return stats

    def _safe(self, fn, *args, **kwargs):
        """Run a section collector; on AccessError report it gracefully.
        This is how role boundaries surface as information, not errors."""
        try:
            return fn(*args, **kwargs)
        except AccessError:
            return {
                "name": fn.__name__.replace("_", " ").strip(),
                "note": "This data is not visible with your access rights.",
            }

    def _top(self, records, n=5):
        return [
            {
                "ref": r.display_name,
                "partner": r.partner_id.name if "partner_id" in r._fields and r.partner_id else "",
                "amount": float(r.amount_residual if "amount_residual" in r._fields else 0.0),
            }
            for r in records.sorted("amount_residual", reverse=True)[:n]
            if "amount_residual" in r._fields
        ] or [
            {"ref": r.display_name, "partner": "", "amount": 0.0} for r in records[:n]
        ]

    def _receivables(self, today, deep=False):
        rec = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("invoice_date_due", "<", today),
                ("amount_residual", ">", 0),
            ]
        )
        late = [(today - r.invoice_date_due).days for r in rec if r.invoice_date_due]
        out = {
            "name": "Accounts receivable — overdue customer invoices",
            "count": len(rec),
            "total_outstanding": float(sum(rec.mapped("amount_residual"))),
            "oldest_days": max(late) if late else 0,
            "largest": self._top(rec),
        }
        if deep:
            buckets = {"1-30d": 0.0, "31-60d": 0.0, "61-90d": 0.0, "90d+": 0.0}
            for r in rec:
                days = (today - r.invoice_date_due).days
                for lo, hi in ((1, 30), (31, 60), (61, 90)):
                    if lo <= days <= hi:
                        buckets["%d-%dd" % (lo, hi)] += r.amount_residual
                        break
                else:
                    if days > 90:
                        buckets["90d+"] += r.amount_residual
            out["aging_buckets"] = {k: float(v) for k, v in buckets.items()}
            # customer concentration
            by_partner = {}
            for r in rec:
                by_partner[r.partner_id.name or "?"] = (
                    by_partner.get(r.partner_id.name or "?", 0.0) + r.amount_residual
                )
            total = out["total_outstanding"] or 1.0
            out["concentration"] = [
                {"partner": p, "amount": float(v), "pct": round(100.0 * v / total, 1)}
                for p, v in sorted(by_partner.items(), key=lambda kv: kv[1], reverse=True)[:5]
            ]
            out["invoices"] = [
                {
                    "ref": r.name,
                    "partner": r.partner_id.name,
                    "amount": float(r.amount_residual),
                    "due": str(r.invoice_date_due),
                    "days_late": (today - r.invoice_date_due).days,
                }
                for r in rec.sorted("invoice_date_due")[:10]
            ]
            # last inbound payment date per most-overdue partner
            partners = rec.mapped("partner_id")[:10]
            pay_hist = []
            for p in partners:
                pay = self.env["account.payment"].search(
                    [
                        ("partner_id", "=", p.id),
                        ("payment_type", "=", "inbound"),
                        ("state", "=", "posted"),
                    ],
                    order="payment_date desc",
                    limit=1,
                )
                pay_hist.append(
                    {
                        "partner": p.name,
                        "last_payment": str(pay.payment_date) if pay else "never",
                        "days_since": (today - pay.payment_date).days if pay else None,
                    }
                )
            out["payment_history"] = pay_hist
        return out

    def _payables(self, today, deep=False):
        bills = self.env["account.move"].search(
            [
                ("move_type", "in", ("in_invoice", "in_refund")),
                ("state", "=", "posted"),
                ("amount_residual", ">", 0),
            ]
        )
        overdue = bills.filtered(lambda b: b.invoice_date_due and b.invoice_date_due < today)
        soon = bills.filtered(
            lambda b: b.invoice_date_due and today <= b.invoice_date_due <= fields.Date.add(today, days=30)
        )
        out = {
            "name": "Accounts payable — vendor bills",
            "overdue_count": len(overdue),
            "overdue_total": float(sum(overdue.mapped("amount_residual"))),
            "due_next_30d_count": len(soon),
            "due_next_30d_total": float(sum(soon.mapped("amount_residual"))),
            "largest_upcoming": self._top(soon),
        }
        if deep:
            out["overdue_detail"] = [
                {
                    "ref": b.name,
                    "partner": b.partner_id.name,
                    "amount": float(b.amount_residual),
                    "due": str(b.invoice_date_due),
                    "days_late": (today - b.invoice_date_due).days,
                }
                for b in overdue.sorted("invoice_date_due")[:10]
            ]
            out["upcoming_detail"] = [
                {
                    "ref": b.name,
                    "partner": b.partner_id.name,
                    "amount": float(b.amount_residual),
                    "due": str(b.invoice_date_due),
                }
                for b in soon.sorted("invoice_date_due")[:10]
            ]
        return out

    def _sales(self, date_from, date_to, deep=False):
        orders = self.env["sale.order"].search(
            [
                ("state", "in", ("sale", "done")),
                ("date_order", ">=", fields.Datetime.to_datetime(date_from)),
                ("date_order", "<=", fields.Datetime.to_datetime(date_to)),
            ]
        )
        out = {
            "name": "Confirmed sales in period",
            "count": len(orders),
            "total": float(sum(orders.mapped("amount_total"))),
            "top_customers": self._top(orders.sorted("amount_total", reverse=True)),
        }
        if deep:
            by_user = {}
            for o in orders:
                name = o.user_id.name or "unassigned"
                by_user.setdefault(name, {"count": 0, "total": 0.0})
                by_user[name]["count"] += 1
                by_user[name]["total"] += o.amount_total
            out["by_salesperson"] = {
                k: {"count": v["count"], "total": float(v["total"])}
                for k, v in by_user.items()
            }
            out["orders"] = [
                {
                    "ref": o.name,
                    "customer": o.partner_id.name,
                    "amount": float(o.amount_total),
                    "date": str(o.date_order.date()),
                    "salesperson": o.user_id.name or "",
                }
                for o in orders.sorted("amount_total", reverse=True)[:10]
            ]
        return out

    def _leads(self, today, deep=False):
        Lead = self.env["crm.lead"].search([])  # record rules filter by user
        open_leads = Lead.filtered(lambda l: not l.probability or l.probability < 100)
        by_stage = {}
        for lead in open_leads:
            stage = lead.stage_id.name or "unnamed"
            by_stage.setdefault(stage, {"count": 0, "expected_revenue": 0.0})
            by_stage[stage]["count"] += 1
            by_stage[stage]["expected_revenue"] += lead.expected_revenue or 0.0
        out = {
            "name": "Open CRM leads by stage",
            "stages": by_stage,
            "total_open": len(open_leads),
            "total_expected_revenue": float(sum(open_leads.mapped("expected_revenue"))),
        }
        if deep:
            stale = open_leads.filtered(
                lambda l: l.date_last_stage_update
                and (today - l.date_last_stage_update.date()).days >= 14
            )
            out["stale_14d_no_stage_change"] = len(stale)
            out["leads"] = [
                {
                    "name": l.name,
                    "partner": l.partner_id.name or "",
                    "expected_revenue": float(l.expected_revenue or 0.0),
                    "probability": l.probability or 0.0,
                    "stage": l.stage_id.name or "",
                    "days_in_stage": (today - l.date_last_stage_update.date()).days
                    if l.date_last_stage_update
                    else None,
                    "salesperson": l.user_id.name or "",
                }
                for l in open_leads.sorted("expected_revenue", reverse=True)[:10]
            ]
        return out

    def _my_overdue_activities(self, today, deep=False):
        acts = self.env["mail.activity"].search(
            [("user_id", "=", self.env.uid), ("date_deadline", "<", today)]
        )
        out = {
            "name": "My overdue activities",
            "count": len(acts),
            "models": sorted({a.res_model for a in acts}),
        }
        if deep:
            out["activities"] = [
                {
                    "summary": a.summary or "(untitled)",
                    "on": "%s/%s" % (a.res_model, a.res_name),
                    "deadline": str(a.date_deadline),
                }
                for a in acts.sorted("date_deadline")[:15]
            ]
        return out

    # ------------------------------------------------------------------
    # LLM backends
    # ------------------------------------------------------------------

    @api.model
    def _llm_config(self):
        icp = self.env["ir.config_parameter"].sudo()
        return {
            "provider": icp.get_param("ai_digest.provider", "anthropic"),
            "api_key": icp.get_param("ai_digest.api_key", ""),
            "model": icp.get_param("ai_digest.model", ""),
            "base_url": icp.get_param("ai_digest.base_url", ""),
        }

    @api.model
    def call_llm(self, system, user_prompt):
        cfg = self._llm_config()
        provider = cfg["provider"]
        try:
            if provider == "anthropic":
                return self._call_anthropic(cfg, system, user_prompt)
            if provider == "openai":
                return self._call_openai(cfg, system, user_prompt)
            if provider == "openrouter":
                return self._call_openrouter(cfg, system, user_prompt)
            if provider == "ollama":
                return self._call_ollama(cfg, system, user_prompt)
            raise UserError(_("Unknown ai_digest.provider: %s", provider))
        except UserError:
            raise
        except Exception as e:
            _logger.exception("AI digest LLM call failed")
            raise UserError(_("LLM call failed: %s", e)) from e

    def _call_anthropic(self, cfg, system, user_prompt):
        url = (cfg["base_url"] or "https://api.anthropic.com") + "/v1/messages"
        resp = requests.post(
            url,
            headers={
                "x-api-key": cfg["api_key"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": cfg["model"] or "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "system": system,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    def _call_openai(self, cfg, system, user_prompt):
        url = (cfg["base_url"] or "https://api.openai.com") + "/v1/chat/completions"
        resp = requests.post(
            url,
            headers={"Authorization": "Bearer %s" % cfg["api_key"]},
            json={
                "model": cfg["model"] or "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_openrouter(self, cfg, system, user_prompt):
        """OpenRouter is OpenAI-compatible; models are namespaced
        (e.g. 'anthropic/claude-sonnet-4', 'meta-llama/llama-3.1-70b-instruct')."""
        url = (cfg["base_url"] or "https://openrouter.ai") + "/api/v1/chat/completions"
        resp = requests.post(
            url,
            headers={
                "Authorization": "Bearer %s" % cfg["api_key"],
                "HTTP-Referer": "https://odoo.local",
                "X-Title": "Odoo AI Business Digest",
            },
            json={
                "model": cfg["model"] or "openai/gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_ollama(self, cfg, system, user_prompt):
        url = (cfg["base_url"] or "http://localhost:11434") + "/api/chat"
        resp = requests.post(
            url,
            json={
                "model": cfg["model"] or "llama3.1",
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    @api.model
    def build_summary(self, date_from=None, date_to=None):
        date_to = date_to or fields.Date.context_today(self)
        date_from = date_from or fields.Date.add(date_to, days=-30)
        stats = self.collect_stats(date_from, date_to)
        system = (
            "You are a concise business analyst embedded in an Odoo instance. "
            "You receive AGGREGATED business statistics that the requesting user "
            "has permission to see. Produce a short executive summary in plain "
            "text with sections: Overview, Cash position (AR/AP), Sales & Pipeline, "
            "Risks & suggested actions. Be specific with numbers. Max ~300 words. "
            "If a section has no data, skip it."
        )
        return self.call_llm(system, json.dumps(stats, indent=2, default=str))

    # ------------------------------------------------------------------
    # Follow-up Q&A (Discuss channel bot)
    # ------------------------------------------------------------------

    FOCUS_KEYWORDS = [
        # order matters: most-specific first ("salesperson" contains "sale")
        ("receivables", ("receivab", "customer invoice", "customer payment", "ar ", "aging")),
        ("payables", ("payable", "vendor", "supplier", "bill", "ap ")),
        ("leads", ("lead", "pipeline", "prospect", "opportunit", "stale")),
        ("sales", ("sale", "order", "revenue this", "sold")),
        ("activities", ("activity", "task", "to-do", "todo", "follow-up")),
    ]

    @api.model
    def detect_focus(self, question):
        q = (question or "").lower()
        for focus, words in self.FOCUS_KEYWORDS:
            if any(w in q for w in words):
                return focus
        return "all"

    def _persona(self, user):
        """Role lens derived from the asker's groups. Guards with
        raise_if_not_found=False: apps like Sales may not be installed."""
        roles = []
        g = user.groups_id
        acct_mgr = self.env.ref("account.group_account_manager", raise_if_not_found=False)
        acct_user = self.env.ref("account.group_account_user", raise_if_not_found=False)
        sale_mgr = self.env.ref("sales_team.group_sale_manager", raise_if_not_found=False)
        sale_user = self.env.ref("sales_team.group_sale_salesman", raise_if_not_found=False)
        sys_admin = self.env.ref("base.group_system", raise_if_not_found=False)
        if acct_mgr and acct_mgr in g:
            roles.append("finance/accounting leadership")
        elif acct_user and acct_user in g:
            roles.append("accounting/finance staff")
        if sale_mgr and sale_mgr in g:
            roles.append("sales leadership")
        elif sale_user and sale_user in g:
            roles.append("sales staff")
        if sys_admin and sys_admin in g:
            roles.append("system administration")
        return ", ".join(roles) or "general business user"

    @api.model
    def answer(self, question, asker, date_from=None, date_to=None):
        """Deep-dive follow-up. Data is collected AS THE ASKER (with_user),
        so record rules and access rights apply. The LLM reply is shaped by
        the asker's role groups."""
        date_to = date_to or fields.Date.context_today(self)
        date_from = date_from or fields.Date.add(date_to, days=-30)
        focus = self.detect_focus(question)
        stats = self.with_user(asker).collect_stats(date_from, date_to, focus=focus)
        persona = self._persona(asker)
        system = (
            "You are a business analyst embedded in an Odoo Discuss channel. "
            "The asking user's role is: %s. Their access rights have already "
            "been applied to the data below — sections marked as not visible "
            "are outside their permissions; state that naturally if relevant. "
            "The user asked a follow-up question; answer IT directly, with "
            "specific numbers from the data. Plain text, max ~250 words. "
            "End with one concrete suggested action when appropriate."
        ) % persona
        user_prompt = "Question: %s\n\nDATA (focus=%s):\n%s" % (
            question,
            focus,
            json.dumps(stats, indent=2, default=str),
        )
        return self.call_llm(system, user_prompt)

    # ------------------------------------------------------------------
    # Channel bot cron
    # ------------------------------------------------------------------

    TRIGGER_PREFIXES = ("!ai", "?ai", "ai:")

    @api.model
    def _bot_partner_id(self):
        icp = self.env["ir.config_parameter"].sudo()
        return int(icp.get_param("ai_digest.bot_partner_id") or 0) or self.env.ref(
            "base.partner_root"
        ).id

    @api.model
    def _cron_channel_bot(self):
        """Runs every minute. Processes new channel messages that trigger the
        bot, answers each AS THE ASKER, posts the reply as the bot."""
        icp = self.env["ir.config_parameter"].sudo()
        channel_id = int(icp.get_param("ai_digest.channel_id") or 0)
        if not channel_id:
            return
        Msg = self.env["mail.message"].sudo()

        last_id = icp.get_param("ai_digest.last_msg_id")
        if last_id is None:
            # first run: fast-forward past all history
            newest = Msg.search(
                [("model", "=", "mail.channel"), ("res_id", "=", channel_id)],
                order="id desc",
                limit=1,
            )
            icp.set_param("ai_digest.last_msg_id", str(newest.id or 0))
            return

        pending = Msg.search(
            [
                ("model", "=", "mail.channel"),
                ("res_id", "=", channel_id),
                ("id", ">", int(last_id)),
                ("message_type", "=", "comment"),
            ],
            order="id",
            limit=15,
        )
        bot_partner = self._bot_partner_id()
        for m in pending:
            icp.set_param("ai_digest.last_msg_id", str(m.id))  # advance even on skip
            if m.author_id.id == bot_partner or m.author_id.id == self.env.ref(
                "base.partner_root"
            ).id:
                continue  # our own replies
            body = html2plaintext(m.body or "").strip()
            triggered = body.lower().startswith(self.TRIGGER_PREFIXES) or bot_partner in [
                p.id for p in m.partner_ids
            ]
            if not triggered:
                continue
            question = body.lstrip("!?").removeprefix("ai:").strip() or body
            reply = self._process_question(m, question)
            self.env["mail.channel"].sudo().browse(channel_id).message_post(
                body=plaintext2html(reply),
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )

    def _process_question(self, msg, question):
        users = msg.author_id.user_ids
        if not users:
            return "I can only answer Odoo users — your Discuss identity has no linked user account."
        asker = users[0]
        if not self.env["res.users"].sudo().browse(asker.id).has_group("ai_digest.group_ai_user"):
            return (
                "You are not authorized for AI digests. Ask an administrator to add you "
                "to the 'AI Digest / User' group."
            )
        try:
            return self.answer(question, asker)
        except Exception as e:
            _logger.exception("ai_digest bot failed answering %s", asker.login)
            return "Sorry — I failed to process that (%s). Check the server logs." % e

    @api.model
    def _run_daily_digest(self):
        """Cron entry point: posts an org-wide digest into a Discuss channel.

        NOTE: cron runs as superuser, so this digest is intentionally
        org-wide. Keep the channel private and restricted to people who
        may see full company figures.
        """
        icp = self.env["ir.config_parameter"].sudo()
        channel_id = int(icp.get_param("ai_digest.channel_id") or 0)
        if not channel_id:
            _logger.info("ai_digest: no channel configured, skipping digest")
            return
        summary = self.sudo().build_summary()
        channel = self.env["mail.channel"].sudo().browse(channel_id)
        channel.message_post(
            body=summary.replace("\n", "<br/>"),
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

