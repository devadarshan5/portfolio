#!/usr/bin/env python3
"""
Apply a site update described by a GitHub issue form to the portfolio HTML.

Reads the issue body from $ISSUE_BODY (or --body-file for local use), works out
which form it came from, and edits the right page:

  * "Duolingo score" form -> Jinbei.html   (ids: duo-nl-score, duo-nl-tier, duo-nl-note)
  * "Entry title" form    -> Chopper.html  (new card at the top of #entryGrid)

Writes `changed`, `summary` and `commit_msg` to $GITHUB_OUTPUT when it is set.
Exits 1 with a readable message on bad input so the workflow fails loudly.

Local use:
  python3 scripts/update_content.py --body-file my-update.md --dry-run
"""
import argparse
import html
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("SITE_ROOT") or Path(__file__).resolve().parent.parent)

# Issue-form field labels. Must match .github/ISSUE_TEMPLATE/*.yml exactly.
F_SCORE, F_LEVEL, F_NOTE = "Duolingo score", "Level", "Note (optional)"
F_TITLE, F_FORM, F_BODY = "Entry title", "Form", "What happened"
F_ORDERS, F_DATE = "Dr. Chopper's Orders (optional)", "Date (optional)"

FORMS = {  # dropdown label -> (data-cat, badge text)
    "Brain Point (Lore/Tech)": ("brain", "Brain Point"),
    "Walk Point (Journal)": ("walk", "Walk Point"),
    "Kung Fu Point (Action)": ("kungfu", "Kung Fu Point"),
}


class UpdateError(Exception):
    pass


# ---------------------------------------------------------------- helpers
def parse_sections(body: str) -> dict:
    """Issue forms render as '### Label\\n\\nvalue'. Return {label: value}."""
    parts = re.split(r"^###\s+(.+?)\s*$", body.replace("\r\n", "\n"), flags=re.M)
    sections = {}
    for label, value in zip(parts[1::2], parts[2::2]):
        value = value.strip()
        sections[label.strip()] = "" if value == "_No response_" else value
    return sections


def require(sec: dict, label: str) -> str:
    value = sec.get(label, "").strip()
    if not value:
        raise UpdateError(f'The "{label}" field is empty. Fields found: {", ".join(sec) or "none"}.')
    return value


def inline(text: str) -> str:
    """Escape HTML, then turn [label](https://url) into the site's link style."""
    text = html.escape(text, quote=False)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2))
        if not re.match(r"https?://", url):
            return m.group(0)
        return (
            f'<a href="{html.escape(url, quote=True)}" '
            f'style="color:inherit;text-decoration:underline;" '
            f'target="_blank" rel="noopener">{label}</a>'
        )

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)


def set_inner(text: str, element_id: str, value: str, filename: str) -> str:
    pattern = re.compile(r'(<(\w+)\b[^>]*\bid="%s"[^>]*>)(.*?)(</\2>)' % re.escape(element_id), re.S)
    if len(pattern.findall(text)) != 1:
        raise UpdateError(
            f'Expected exactly one element with id="{element_id}" in {filename}. '
            "Has the id snippet from docs/UPDATING.md been applied?"
        )
    return pattern.sub(lambda m: m.group(1) + html.escape(value, quote=False) + m.group(4), text, count=1)


def get_inner(text: str, element_id: str) -> str:
    m = re.search(r'<(\w+)\b[^>]*\bid="%s"[^>]*>(.*?)</\1>' % re.escape(element_id), text, re.S)
    return m.group(2).strip() if m else "?"


# ---------------------------------------------------------------- Dutch score
def update_dutch(sec: dict, dry_run: bool):
    score_raw = require(sec, F_SCORE)
    if not re.fullmatch(r"\d{1,3}", score_raw):
        raise UpdateError(f'"{F_SCORE}" must be a whole number, got "{score_raw}".')
    level = require(sec, F_LEVEL)
    note = sec.get(F_NOTE, "").strip()

    path = ROOT / "Jinbei.html"
    text = path.read_text(encoding="utf-8")
    old_score = get_inner(text, "duo-nl-score")
    text = set_inner(text, "duo-nl-score", str(int(score_raw)), path.name)
    text = set_inner(text, "duo-nl-tier", level, path.name)
    if note:
        text = set_inner(text, "duo-nl-note", note, path.name)
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return {
        "summary": f"Dutch score {old_score} -> {int(score_raw)} ({level}) on Jinbei.html",
        "commit_msg": f"Update Dutch Duolingo score to {int(score_raw)}",
        "verify_file": "Jinbei.html",
        "verify_text": f'id="duo-nl-score">{int(score_raw)}<',
    }


# ---------------------------------------------------------------- Chopper entry
def update_chopper(sec: dict, created_at: datetime, tz: ZoneInfo, dry_run: bool):
    title = require(sec, F_TITLE)
    form_label = require(sec, F_FORM)
    if form_label not in FORMS:
        raise UpdateError(f'Unknown form "{form_label}". Expected one of: {", ".join(FORMS)}.')
    cat, badge = FORMS[form_label]
    body = require(sec, F_BODY)
    orders = sec.get(F_ORDERS, "").strip()

    date_raw = sec.get(F_DATE, "").strip()
    if date_raw:
        try:
            when = datetime.strptime(date_raw, "%Y-%m-%d")
        except ValueError:
            raise UpdateError(f'"{F_DATE}" must look like 2026-11-18, got "{date_raw}".')
    else:
        when = created_at.astimezone(tz)
    date_label = f"{when.strftime('%b')} {when.day}"

    path = ROOT / "Chopper.html"
    text = path.read_text(encoding="utf-8")
    grid = re.search(r'<div class="grid" id="entryGrid">[ \t]*\n', text)
    if not grid:
        raise UpdateError('Could not find <div class="grid" id="entryGrid"> in Chopper.html.')

    # Look at the current top card so the new one tilts / tapes the opposite way.
    prev = re.search(r'<article class="card"[^>]*--tilt:(-?[\d.]+)deg;.*?<div class="tape (pink|blue) tl">', text[grid.end():], re.S)
    prev_tilt = float(prev.group(1)) if prev else 1.0
    prev_tape = prev.group(2) if prev else "blue"
    rng = random.Random(title)
    tilt = round(rng.uniform(0.6, 1.4), 1) * (1 if prev_tilt < 0 else -1)
    tl, br = ("pink", "blue") if prev_tape == "blue" else ("blue", "pink")

    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", body) if p.strip()]
    body_html = '      <p class="body-text">' + "<br><br>".join(inline(p) for p in paragraphs) + "</p>"
    ticket = ""
    if orders:
        ticket = (
            '\n      <div class="ticket">\n'
            "        <div class=\"tk-head\">Dr. Chopper's Orders:</div>\n"
            f'        <div class="tk-note">{inline(" ".join(orders.split()))}</div>\n'
            "      </div>"
        )
    card = (
        f'    <article class="card" data-cat="{cat}" style="--tilt:{tilt}deg;">\n'
        f'      <div class="tape {tl} tl"></div><div class="tape {br} br"></div>\n'
        '      <div class="new-sticker">NEW!</div>\n'
        f'      <span class="badge {cat}">{badge}</span>\n'
        f'      <span class="date">{date_label}</span>\n'
        f"      <h2>{html.escape(title, quote=False)}</h2>\n"
        f"{body_html}{ticket}\n"
        "    </article>\n\n"
    )

    text = re.sub(r'[ \t]*<div class="new-sticker">NEW!</div>\n', "", text)  # only the newest card is NEW
    grid = re.search(r'<div class="grid" id="entryGrid">[ \t]*\n', text)
    text = text[: grid.end()] + card + text[grid.end():]
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return {
        "summary": f'New {badge} entry "{title}" ({date_label}) at the top of Chopper.html',
        "commit_msg": f"Add Chopper log: {title}"[:120],
        "verify_file": "Chopper.html",
        "verify_text": f"<h2>{html.escape(title, quote=False)}</h2>",
    }


# ---------------------------------------------------------------- entry point
def set_output(**kv):
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as fh:
        for k, v in kv.items():
            fh.write(f"{k}={' '.join(str(v).split())}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body-file", help="read the issue body from a file instead of $ISSUE_BODY")
    ap.add_argument("--dry-run", action="store_true", help="validate and report, but do not write files")
    args = ap.parse_args()

    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else os.environ.get("ISSUE_BODY", "")
    created = os.environ.get("ISSUE_CREATED_AT")
    created_at = datetime.fromisoformat(created.replace("Z", "+00:00")) if created else datetime.now(timezone.utc)
    tz = ZoneInfo(os.environ.get("SITE_TZ") or "UTC")

    sec = parse_sections(body)
    try:
        if F_SCORE in sec:
            result = update_dutch(sec, args.dry_run)
        elif F_TITLE in sec:
            result = update_chopper(sec, created_at, tz, args.dry_run)
        else:
            print("Not one of the site-update forms; nothing to do.")
            set_output(changed="false")
            return 0
    except UpdateError as err:
        print(f"::error::{err}")
        set_output(changed="false", error=str(err))
        return 1

    print(("[dry run] " if args.dry_run else "") + result["summary"])
    set_output(changed="true", **result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
