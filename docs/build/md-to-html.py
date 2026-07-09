#!/usr/bin/env python3
"""Minimal markdown to HTML for Bloodstone download docs (no external deps)."""

from __future__ import annotations

import html
import re
import sys


def md_to_html(text: str, title: str = "Document") -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_table = False
    in_code = False
    in_ul = False

    def close_table():
        nonlocal in_table
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            close_table()
            close_ul()
            if in_code:
                out.append("</pre>")
                in_code = False
            else:
                out.append('<pre class="code">')
                in_code = True
            continue
        if in_code:
            out.append(html.escape(line))
            continue

        if "|" in line and line.strip().startswith("|"):
            close_ul()
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.match(r"^:?-+:?$", c.replace(" ", "")) or c == "" for c in cells):
                continue
            if not in_table:
                out.append('<table><thead><tr>')
                for c in cells:
                    out.append(f"<th>{inline(c)}</th>")
                out.append("</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>")
                for c in cells:
                    out.append(f"<td>{inline(c)}</td>")
                out.append("</tr>")
            continue
        else:
            close_table()

        if line.startswith("# "):
            close_ul()
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("## "):
            close_ul()
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("### "):
            close_ul()
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(line[2:])}</li>")
        elif re.match(r"^\d+\.\s", line):
            if not in_ul:
                out.append("<ol>")
                in_ul = True
            item = re.sub(r"^\d+\.\s", "", line)
            out.append(f"<li>{inline(item)}</li>")
        elif line.strip() == "---":
            close_ul()
            out.append("<hr>")
        elif not line.strip():
            close_ul()
            out.append("<p></p>")
        else:
            close_ul()
            out.append(f"<p>{inline(line)}</p>")

    close_table()
    close_ul()
    if in_code:
        out.append("</pre>")

    body = "\n".join(out)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Georgia, serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.55; color: #1a1a1a; }}
    h1, h2, h3 {{ font-family: Arial, sans-serif; color: #0d2137; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.92rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }}
    th {{ background: #e8f0f8; }}
    code, pre.code {{ font-family: ui-monospace, monospace; font-size: 0.9em; background: #f4f4f4; }}
    pre.code {{ padding: 0.75rem; overflow-x: auto; }}
    a {{ color: #0b57d0; }}
    hr {{ border: none; border-top: 1px solid #ddd; margin: 1.5rem 0; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    s = re.sub(
        r"(https?://[^\s<]+)",
        r'<a href="\1">\1</a>',
        s,
    )
    return s


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: md-to-html.py input.md output.html [title]", file=sys.stderr)
        return 1
    src, dst = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else "Document"
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    html_doc = md_to_html(text, title=title)
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html_doc)
    print(dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())