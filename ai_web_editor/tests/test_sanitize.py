# Victory Technical Services
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo.addons.ai_web_editor.controllers.main import SYSTEM_PROMPT, _sanitize

from odoo.tests import common


class TestSanitize(common.TransactionCase):
    """Nothing dangerous may survive the sanitizer before it reaches the editor."""

    def test_strips_script_tags(self):
        out = _sanitize('<section><p>ok</p><script>alert(1)</script></section>')
        self.assertNotIn("<script", out.lower())
        self.assertIn("<p>ok</p>", out)

    def test_strips_iframes(self):
        out = _sanitize('<section><iframe src="http://evil"></iframe><p>ok</p></section>')
        self.assertNotIn("<iframe", out.lower())

    def test_strips_event_handlers(self):
        out = _sanitize('<section><p onclick="alert(1)" onmouseover="x()">hi</p></section>')
        self.assertNotIn("onclick", out.lower())
        self.assertNotIn("onmouseover", out.lower())

    def test_strips_javascript_urls(self):
        out = _sanitize('<section><a href="javascript:alert(1)">click</a></section>')
        self.assertNotIn("javascript:", out.lower())

    def test_strips_markdown_fences(self):
        out = _sanitize('```html\n<section><p>ok</p></section>\n```')
        self.assertNotIn("```", out)
        self.assertIn("<section>", out)

    def test_keeps_bootstrap_markup(self):
        src = '<section class="container"><div class="row"><div class="col-lg-6"><p class="s_text_block">keep me</p></div></div></section>'
        out = _sanitize(src)
        self.assertIn("s_text_block", out)
        self.assertIn("col-lg-6", out)

    def test_handles_plain_text_input(self):
        # LLM sometimes answers without tags; sanitizer must not crash
        out = _sanitize("just some text")
        self.assertTrue(out)


class TestSystemPrompt(common.TransactionCase):
    """The generation prompt must keep the LLM inside safe, editor-friendly output."""

    def test_prompt_forbids_scripts(self):
        self.assertIn("no\n<script", SYSTEM_PROMPT.replace("no ", "no\n"))  # 'no <script>' present
        self.assertIn("script", SYSTEM_PROMPT)

    def test_prompt_requires_bootstrap(self):
        self.assertIn("Bootstrap", SYSTEM_PROMPT)
