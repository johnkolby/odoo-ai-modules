# Victory Technical — Odoo AI Modules

Practical AI integrations for Odoo 16, released as free software (LGPL-3).

Both modules are **model-agnostic** (Anthropic, OpenAI, OpenRouter, or a local
Ollama — switchable via a single system parameter), **permission-aware** (all
data access runs as the requesting user; record rules and access rights apply
automatically), and **privacy-first** (only aggregated, permission-filtered
data ever reaches the model; API keys live server-side).

| Module | What it does |
|---|---|
| [`ai_digest`](./ai_digest) | Permission-aware executive summaries of receivables, payables, sales, pipeline and activities — interactive wizard, daily digest cron, and a collaborative Q&A bot in Odoo Discuss |
| [`ai_web_editor`](./ai_web_editor) | An AI design partner inside Odoo's visual website editor — describe a section and it appears, highlight text and have it rewritten in place |

## Installation (Odoo 16)

```bash
git clone https://github.com/<you>/odoo-ai-modules.git
ln -s $(pwd)/odoo-ai-modules/ai_digest /path/to/addons/
ln -s $(pwd)/odoo-ai-modules/ai_web_editor /path/to/addons/
odoo -d YOUR_DB -i ai_digest,ai_web_editor
```

Then configure the LLM provider in *Settings → Technical → System Parameters*:

| Key | Values |
|---|---|
| `ai_digest.provider` | `anthropic` / `openai` / `openrouter` / `ollama` |
| `ai_digest.api_key` | your provider key (server-side only) |
| `ai_digest.model` | optional, provider default if unset |
| `ai_digest.channel_id` | optional Discuss channel id for the daily digest |

## Security model

- **No `sudo()` in the data path.** All statistics are collected with the
  requesting user's environment, so `ir.model.access` and `ir.rule` (including
  multi-company rules) filter every query.
- **Aggregates only**: counts, totals and top-N references are sent to the
  LLM — never full documents.
- **Group-gated**: both modules require dedicated user groups.
- **Sanitized** editor output server-side: scripts, iframes, event handlers
  and `javascript:` URIs are stripped before anything reaches the browser.

## Running the tests

```bash
odoo -d test_db -i ai_digest,ai_web_editor --test-enable --stop-after-init
```

CI runs the same suite on every push (see `.github/workflows/tests.yml`).

## License

LGPL-3 — see the LICENSE file in each module.
