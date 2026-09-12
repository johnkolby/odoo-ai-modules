# Copyright (c) 2026 John Kolby — Victory Technical Services
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
import re

import lxml.html

from odoo import http
from odoo.http import request
from odoo.exceptions import UserError

SYSTEM_PROMPT = (
    "You are a senior web designer working INSIDE Odoo 16's website editor. "
    "The user will give you an instruction and optionally the HTML of the "
    "section they currently have selected. Reply with ONLY the raw HTML of a "
    "replacement or new section — no markdown fences, no explanations, no "
    "<script>, <style>, <link>, <meta> or <iframe> tags, no external assets. "
    "Constraints: "
    "- Use Bootstrap 4.6 utility classes available in Odoo (container, row, "
    "col-lg-*, pt-5, pb-5, text-center, bg-*, btn btn-primary, img-fluid, ...). "
    "- Wrap sections in a <section> tag. "
    "- Use Odoo's editable text pattern where the designer should edit text: "
    '<span class="s_text_block"> or plain <p>/<h1>-<h3> content. '
    "- Use placeholder https://placehold.co images with descriptive sizes if "
    "images are needed. "
    "- Keep the design clean and modern; follow the user's instruction for "
    "tone and layout. If they ask to modify the provided HTML, keep what "
    "works and change what they asked for. If they highlighted text and ask "
    "for a rewrite, rewrite that text within the returned section."
)


def _sanitize(raw):
    """Best-effort safety net: strip fences, scripts, event handlers, js: URIs."""
    raw = (raw or "").strip()
    raw = re.sub(r"^```(html)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        doc = lxml.html.fromstring(raw)
    except Exception:
        doc = lxml.html.fromstring("<div>%s</div>" % raw)
    for bad in doc.xpath("//script|//iframe|//object|//embed|//link|//meta|//form"):
        bad.drop_tree()
    for el in doc.iter():
        for attr in list(el.attrib):
            al = attr.lower()
            val = (el.attrib[attr] or "").strip().lower()
            if al.startswith("on") or (al in ("href", "src", "xlink:href") and val.startswith("javascript")):
                del el.attrib[attr]
    return lxml.html.tostring(doc, encoding="unicode")


class AiWebEditor(http.Controller):

    @http.route(
        "/ai_web_editor/generate",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=True,
        website=True,
    )
    def generate(self, instruction=None, snippet_html=None, selection_text=None, page_url=None, **kwargs):
        if not request.env.user.has_group("ai_web_editor.group_ai_designer"):
            return {"error": "You are not authorized to use the AI editor assistant."}
        instruction = (instruction or "").strip()[:2000]
        if not instruction:
            return {"error": "Please describe what you want."}
        snippet_html = (snippet_html or "")[:15000]
        selection_text = (selection_text or "").strip()[:2000]

        user_prompt = "Instruction: %s" % instruction
        if selection_text:
            user_prompt += "\n\nThe user highlighted this text:\n%s" % selection_text
        if snippet_html:
            user_prompt += "\n\nCurrently selected section HTML:\n%s" % snippet_html
        if page_url:
            user_prompt += "\n\nPage: %s" % page_url

        try:
            result = request.env["ai.digest"].sudo().call_llm(SYSTEM_PROMPT, user_prompt)
        except UserError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": "LLM call failed: %s" % e}

        return {"html": _sanitize(result)}
