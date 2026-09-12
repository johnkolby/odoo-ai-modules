{
    "name": "AI Web Editor Assistant",
    "version": "16.0.1.0.0",
    "category": "Website/AI",
    "summary": "In-editor AI collaborator: describe a section, it appears on the page",
    "description": """
AI Web Editor Assistant
=======================
Adds an "AI Assist" floating panel to the website editor (edit mode only).
Select a block, describe what you want, the AI-generated HTML section is
inserted live into the page — designer keeps full control with native tools.

- Reuses ai_digest's LLM plumbing (provider/api_key/model parameters)
- Server-side sanitization: no scripts/iframes/event handlers/javascript: URIs
- Group-gated: AI Web Editor / Designer
""",
    "author": "johnkolby",
    "license": "LGPL-3",
    "depends": ["website", "web_editor", "ai_digest"],
    "data": [
        "security/ai_web_editor_groups.xml",
    ],
    "assets": {
        "website.assets_editor": [
            "ai_web_editor/static/src/js/ai_assist.js",
        ],
    },
    "installable": True,
    "application": False,
}
