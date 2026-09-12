# AI Business Digest (Odoo module)

Permission-aware AI summaries of your Odoo business data: receivables,
payables, sales, CRM pipeline, and your overdue activities.

## How permissions work (the important part)

- **Interactive wizard:** all data is collected with the *requesting user's*
  environment — no `sudo()`. Odoo's access rights and record rules filter
  the searches automatically, so the AI can only summarize what that user
  can already read. Multi-company rules are respected too.
- **Only aggregates go to the LLM:** counts, totals, top-5 refs/partners.
  Full documents never leave your database.
- **Daily cron digest:** runs as superuser → org-wide. Post it into a
  *private* Discuss channel restricted to people allowed to see full figures.
- **Gate:** users must be in the "AI Digest / User" group to run anything.

## Install (Odoo 17)

```bash
# copy/mount the module into your addons path, then:
odoo -d YOUR_DB -u ai_digest
```

Dependencies: `mail`, `account` (crm/sale used only if installed).

## Configure (Settings → Technical → System Parameters)

| Key | Example | Notes |
|---|---|---|
| `ai_digest.provider` | `anthropic` / `openai` / `openrouter` / `ollama` | default: anthropic |
| `ai_digest.api_key` | `sk-or-...` / `sk-...` | required for anthropic/openai/openrouter |
| `ai_digest.model` | `anthropic/claude-sonnet-4` | openrouter uses namespaced model ids |
| `ai_digest.base_url` | `https://your-proxy` | optional (proxies, ollama host) |
| `ai_digest.channel_id` | `5` | Discuss channel id for the daily digest |

## Use

- **Menu: Settings → AI Digest** — pick a date range, "Generate Summary".
  The result plus the exact JSON sent to the LLM is shown (transparency).
- **Daily digest** — posted by cron to the configured Discuss channel.
- Developers: `self.env['ai.digest'].build_summary(date_from, date_to)`.

## Version notes

Written for **Odoo 17**. For 16: same code should load; for 18: replace
`invisible="not summary"` with the new `invisible="not summary"` expression
syntax (18 still supports these Python-ish expressions in this simple form).
Test before production use.
