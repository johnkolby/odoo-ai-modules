// # Copyright (c) 2026 John Kolby — Victory Technical Services
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
/** @odoo-module **/

/**
 * AI Web Editor Assistant — floating panel for Odoo 16 website editor.
 *
 * Editor documents are located robustly: whichever document (the top one or
 * ANY iframe) has "editor_enable" on its body is the one being edited. This
 * covers the inline frontend editor AND the backend website-preview iframe.
 *
 * Selection caching: clicking the panel's textarea clears a same-document
 * selection, so the last non-collapsed selection is continuously captured
 * and reused at Generate time.
 */

let panel = null;
let lastCtx = null;

function bodyHasEditMode(doc) {
    try {
        return !!(doc && doc.body && doc.body.classList.contains("editor_enable"));
    } catch (e) {
        return false;
    }
}

function getEditDoc() {
    // 1. dedicated editor wrapper iframe
    const wrapper = document.querySelector(".iframe-editor-wrapper iframe");
    if (wrapper && bodyHasEditMode(wrapper.contentDocument)) {
        return wrapper.contentDocument;
    }
    // 2. top document
    if (bodyHasEditMode(document)) {
        return document;
    }
    // 3. any iframe whose body is in edit mode (backend preview etc.)
    for (const f of document.querySelectorAll("iframe")) {
        try {
            if (bodyHasEditMode(f.contentDocument)) return f.contentDocument;
        } catch (e) {
            /* cross-origin iframe — ignore */
        }
    }
    return null;
}

function inEditor() {
    return !!getEditDoc();
}

function buildCtx(doc, sel) {
    let node = sel.anchorNode;
    if (!node) return null;
    if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
    if (!node || !doc.body || !doc.body.contains(node)) return null;
    const snippet =
        node.closest &&
        (node.closest('.oe_structure > *') || node.closest('[data-oe-model="ir.ui.view"]'));
    const structure =
        (node.closest && node.closest(".oe_structure")) ||
        doc.querySelector("#wrap") ||
        null;
    return {
        doc,
        snippet,
        structure,
        html: snippet ? snippet.outerHTML.slice(0, 15000) : "",
        selection_text: (function () {
            try { return sel.toString(); } catch (e) { return ""; }
        })(),
    };
}

function captureSelection() {
    const doc = getEditDoc();
    if (!doc) return;
    let sel = null;
    try {
        sel = doc.getSelection();
    } catch (e) {
        return;
    }
    if (sel && sel.rangeCount > 0 && !sel.isCollapsed) {
        const ctx = buildCtx(doc, sel);
        if (ctx && (ctx.snippet || ctx.selection_text)) {
            lastCtx = ctx;
        }
    }
}

function getSelectedContext() {
    captureSelection();
    return lastCtx || null;
}

function setStatus(text, isError) {
    const el = panel.querySelector("#ai-assist-status");
    el.textContent = text;
    el.style.color = isError ? "#c0392b" : "#666";
}

const REWRITE_VERBS = /\b(rewrite|reword|rephrase|shorten|translate|fix|change|update|modify|improve|replace|redo|polish|simplify|expand|professional|casual|friendly|formal)\b/i;

async function generate() {
    const textarea = panel.querySelector("#ai-assist-input");
    const instruction = textarea.value.trim();
    if (!instruction) {
        setStatus("Describe what you want first.", true);
        return;
    }
    const ctx = getSelectedContext();
    const wantsReplace = !!ctx && !!ctx.snippet && REWRITE_VERBS.test(instruction);
    setStatus("Generating…");
    panel.querySelector("#ai-assist-go").disabled = true;
    try {
        const resp = await fetch("/ai_web_editor/generate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": (window.odoo && window.odoo.csrf_token) || "",
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: {
                    instruction: instruction,
                    snippet_html: ctx ? ctx.html : "",
                    selection_text: ctx ? (ctx.selection_text || "").slice(0, 2000) : "",
                    page_url: window.location.pathname,
                },
            }),
        });
        const data = await resp.json();
        const result = data.result || data;
        if (result.error) {
            setStatus(result.error, true);
            return;
        }
        if (!ctx) {
            setStatus("No editable zone found — click into the page content first.", true);
            return;
        }
        const doc = ctx.doc;
        const target =
            (wantsReplace ? null : null) ||
            ctx.structure ||
            doc.querySelector("#wrap") ||
            doc.querySelector(".oe_structure");
        if (!target && !(wantsReplace && ctx.snippet)) {
            setStatus("No editable zone found on this page.", true);
            return;
        }
        let inserted;
        if (wantsReplace && ctx.snippet) {
            ctx.snippet.insertAdjacentHTML("beforebegin", result.html);
            inserted = ctx.snippet.previousElementSibling;
            ctx.snippet.remove();
            lastCtx = null;
        } else if (ctx.snippet) {
            ctx.snippet.insertAdjacentHTML("afterend", result.html);
            inserted = ctx.snippet.nextElementSibling;
            lastCtx = null;
        } else if (target) {
            target.insertAdjacentHTML("beforeend", result.html);
            inserted = target.lastElementChild;
        }
        if (inserted && inserted.scrollIntoView) {
            inserted.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        const where = wantsReplace
            ? "— replaced your selected section"
            : ctx.snippet
            ? "after your selected block"
            : "at the end of " + (target && target.id ? "#" + target.id : "the page");
        setStatus("Done ✓ " + where);
        console.log(
            "[ai_web_editor]",
            wantsReplace ? "REPLACE" : "INSERT",
            "| edit doc:",
            doc === document ? "top" : (doc.defaultView ? doc.defaultView.location.pathname : "iframe"),
            "| chars:",
            result.html.length
        );
        textarea.value = "";
    } catch (e) {
        setStatus("Request failed: " + e.message, true);
    } finally {
        panel.querySelector("#ai-assist-go").disabled = false;
    }
}

function mount() {
    if (panel) return;
    panel = document.createElement("div");
    panel.id = "ai-assist-panel";
    panel.style.cssText = [
        "position:fixed", "bottom:18px", "right:18px", "z-index:20000",
        "width:340px", "background:#fff", "border:1px solid #d0d7de",
        "border-radius:10px", "box-shadow:0 8px 30px rgba(0,0,0,.25)",
        "padding:12px", "font-family:sans-serif", "font-size:13px",
    ].join(";");
    panel.innerHTML = [
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">',
        '  <strong style="font-size:14px">✨ AI Assist</strong>',
        '  <button id="ai-assist-close" type="button" style="border:0;background:none;cursor:pointer;font-size:16px">×</button>',
        "</div>",
        '<textarea id="ai-assist-input" rows="3" placeholder="Select text on the page, then describe: e.g. \'rewrite professionally\' or \'add a testimonial section\'" style="width:100%;box-sizing:border-box;resize:vertical"></textarea>',
        '<div style="display:flex;gap:8px;align-items:center;margin-top:8px">',
        '  <button id="ai-assist-go" type="button" class="btn btn-primary" style="margin:0">Generate</button>',
        '  <span id="ai-assist-status" style="color:#666">Select a block or just ask.</span>',
        "</div>",
    ].join("");
    document.body.appendChild(panel);
    panel.querySelector("#ai-assist-go").addEventListener("click", generate);
    panel.querySelector("#ai-assist-input").addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) generate();
    });
    panel.querySelector("#ai-assist-close").addEventListener("click", () => {
        panel.style.display = "none";
    });
}

function unmount() {
    if (panel) {
        panel.remove();
        panel = null;
    }
}

function refresh() {
    if (inEditor()) {
        if (!panel) {
            mount();
            console.log("[ai_web_editor] panel mounted");
        }
        panel.style.display = "block";
    } else if (panel) {
        unmount();
    }
}

function init() {
    console.log("[ai_web_editor] assistant loaded (doc-scan mode)");
    const obs = new MutationObserver(refresh);
    obs.observe(document.body, { childList: true, subtree: false, attributes: true, attributeFilter: ["class"] });
    setInterval(refresh, 800);
    setInterval(captureSelection, 500);
    refresh();
}

if (document.body) {
    init();
} else {
    document.addEventListener("DOMContentLoaded", init);
}
