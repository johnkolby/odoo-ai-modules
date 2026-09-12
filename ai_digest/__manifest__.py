# Copyright (c) 2026 John Kolby — Victory Technical Services
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
{
    "name": "AI Business Digest",
    "version": "16.0.2.1.0",
    "category": "Productivity/AI",
    "summary": "Permission-aware AI summaries of invoices, payables, leads and sales",
    "description": """
AI Business Digest
==================
- Interactive wizard: pick a date range, get an AI summary of the data
  *you* are allowed to see (record rules and access rights apply).
- Daily cron digest posted into an Odoo Discuss channel.
- Pluggable LLM provider: Anthropic, OpenAI, or a local Ollama.
- Only aggregates leave the database (counts, totals, top-5 names) —
  never full documents.
""",
    "author": "John Kolby",
    "website": "https://victorytechnical.com",
    "maintainers": ["John Kolby"],
    "license": "LGPL-3",
    "depends": ["mail", "account"],
    "data": [
        "security/ai_digest_groups.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/ai_digest_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
