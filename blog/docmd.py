#!/usr/bin/env python3
"""docmd — the SHARED doc-rendering surface: markdown → HTML through an allowlist / no-scripts
boundary.

The single rendering path BOTH Slice 5a (design docs: glossary, ADRs, Idiom, Source roadmap) and
Slice 5b (wiki / cluster pages) go through. Its reason to exist is the SECURITY boundary, not the
markdown: the docs are edge-authored AND source-derived, so the source can carry raw HTML, event
handlers, or `javascript:` URLs. A rendered doc must be INERT in the authed dashboard — an injected
`<script>` / `on*=` handler / `javascript:` URL could read state and fire an authenticated
log-mutating POST, defeating the Slice-1 write gate (PLAN.md Slice 5a/5b).

The boundary is an ALLOWLIST by construction, not a denylist scrub: we never pass source HTML
through. We parse a small, known markdown subset and emit ONLY a fixed set of safe tags, escaping
every text run with `html.escape`. So any raw HTML in the source (a `<script>`, an `<img onerror=>`)
is escaped to inert text — it renders as literal characters, never as live markup. Links are the one
attribute-bearing element, and their `href` scheme is allowlisted (http/https/relative only —
`javascript:` is dropped). Preferred over pulling a heavy markdown+sanitizer dep ("cheap on
resources", PLAN.md): the emit-only-safe-tags design is the sanitizer, with no third-party trust.
"""
import html
import re

# The href scheme allowlist for a markdown link. A `javascript:` (or `data:`, `vbscript:`) URL in a
# link is a same-origin code-execution vector, so an href that is not a safe scheme — http(s),
# mailto, a relative path, or an in-page fragment — is NEUTRALIZED (rendered as plain text, no live
# anchor). Matched case-insensitively on the leading `scheme:` only.
_SAFE_SCHEME = re.compile(r"^(?:https?:|mailto:|/|#|[^:]*$|[^:/?#]*[/?#])", re.IGNORECASE)

# Inline markdown over an ALREADY-html-escaped run: `[text](href)`, `**bold**`, `*em*`, `` `code` ``.
# Operating on escaped text is what keeps the inline pass safe — the only `<`/`>` it ever emits are
# the fixed inline tags it writes itself; a `<` from the source is already `&lt;`.
# href allows one level of balanced parens (URLs like `foo(1)`); leading/trailing space is trimmed
# in the handler. Capturing the whole `(...)` (not stopping at the first `)`) is what stops a
# `javascript:alert(1)` from leaving a dangling `)` when the scheme is rejected.
_LINK = re.compile(r"\[([^\]]*)\]\((\s*[^()\s]*(?:\([^()]*\)[^()\s]*)*\s*)\)")
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_EM = re.compile(r"(?<![*\w])\*([^*\s][^*]*?)\*(?!\w)")


def _href_ok(href):
    """A link href is safe iff its scheme is allowlisted (http/https/mailto/relative/fragment). The
    href arrives ALREADY html-escaped, so we decode it back to the browser's view before deciding —
    and decode REPEATEDLY until stable, so an entity-obfuscated scheme (`java&#115;cript:`,
    `javascript&colon;`) cannot smuggle a `javascript:`/`data:` past the allowlist by hiding one
    decode level deep. All whitespace/control chars are stripped (a `java\\tscript:` trick), then the
    leading scheme is matched against the allowlist. A disallowed scheme → not a live anchor (the
    link text is kept, the href dropped)."""
    raw = href
    for _ in range(4):  # fixpoint decode — &amp;#115; → &#115; → s, etc.
        dec = html.unescape(raw)
        if dec == raw:
            break
        raw = dec
    raw = re.sub(r"[\s\x00-\x1f]", "", raw).strip()
    return bool(_SAFE_SCHEME.match(raw))


def _inline(text):
    """Render inline markdown on an already-html-escaped run. Emits only the fixed inline tags
    (`<a>`, `<strong>`, `<em>`, `<code>`); a link with a non-allowlisted scheme keeps its text but
    drops the href (no live `javascript:` anchor)."""
    def link(m):
        label, href = m.group(1), m.group(2).strip()
        if href and _href_ok(href):
            return f'<a href="{href}">{label}</a>'
        return label  # disallowed scheme — keep the visible text, drop the live anchor
    text = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", text)
    text = _LINK.sub(link, text)
    text = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = _EM.sub(lambda m: f"<em>{m.group(1)}</em>", text)
    return text


def _heading(line):
    """`#`..`######` → an h1..h6, else None. The level is the run of leading `#`s before a space."""
    n = len(line) - len(line.lstrip("#"))
    if 1 <= n <= 6 and line[n:n + 1] == " ":
        return n, line[n + 1:].strip()
    return None


def render_doc_html(text):
    """Render design-doc / wiki markdown to INERT HTML. The output contains ONLY allowlisted tags;
    every text run is html-escaped, so raw HTML in the source renders as literal text, never live
    markup. The shared boundary for Slice 5a and 5b.

    Block-level: ATX headings (`#`..`######`), fenced code (```), bullet lists (`-`/`*`),
    blockquotes (`>`), and paragraphs (blank-line separated). Every emitted text run is `html.escape`d
    BEFORE any inline markup, so a raw `<script>` / `<img onerror=>` in the source becomes literal
    characters — present (the doc reads faithfully) but inert (never live markup). Inside a fence the
    content is escaped verbatim and NOT interpreted as markdown."""
    out = []
    para = []
    bullets = []
    quote = []

    def flush_para():
        if para:
            out.append(f"<p>{_inline(html.escape(' '.join(para).strip()))}</p>")
            para.clear()

    def flush_bullets():
        if bullets:
            items = "".join(f"<li>{_inline(html.escape(b))}</li>" for b in bullets)
            out.append(f"<ul>{items}</ul>")
            bullets.clear()

    def flush_quote():
        if quote:
            inner = _inline(html.escape(" ".join(quote).strip()))
            out.append(f"<blockquote>{inner}</blockquote>")
            quote.clear()

    def flush_all():
        flush_para()
        flush_bullets()
        flush_quote()

    lines = (text or "").split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip()
        stripped = raw.strip()

        # Fenced code block: content is escaped verbatim, markdown NOT interpreted (so a `<script>`
        # in a fence is shown literally, never executed). The fence runs until the closing ```.
        if stripped.startswith("```"):
            flush_all()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # consume the closing fence (or fall off the end)
            out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
            continue

        if not stripped:
            flush_all()
            i += 1
            continue

        h = _heading(raw)
        if h:
            flush_all()
            level, body = h
            out.append(f"<h{level}>{_inline(html.escape(body))}</h{level}>")
            i += 1
            continue

        if stripped[:2] in ("- ", "* "):
            flush_para()
            flush_quote()
            bullets.append(stripped[2:].strip())
            i += 1
            continue

        if stripped.startswith(">"):
            flush_para()
            flush_bullets()
            quote.append(stripped[1:].strip())
            i += 1
            continue

        flush_bullets()
        flush_quote()
        para.append(stripped)
        i += 1

    flush_all()
    return "\n".join(out)
