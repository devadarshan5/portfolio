#!/usr/bin/env python3
"""
Static check: every local file an HTML page refers to must exist.

Looks at src/href attributes, CSS url(...) and quoted strings in inline JS that
end in a known file extension (so config-driven loading screens are covered).
Case-sensitive, like GitHub Pages. Catches .jpg/.png/.jpeg mix-ups, renamed
folders (Jinbe -> Jinbei) and typos before they go live.

Usage: python3 scripts/check_assets.py [Page.html ...]
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
EXT = r"(?:png|jpe?g|gif|webp|avif|svg|ico|mp3|ogg|wav|m4a|mp4|webm|woff2?|ttf|otf|css|js|json|html)"
CANDIDATES = [
    re.compile(r"""(?:src|href|poster)\s*=\s*["']([^"']+)["']""", re.I),
    re.compile(r"""url\(\s*["']?([^"')\s]+)["']?\s*\)""", re.I),
    re.compile(r"""["'`]([^"'`\s<>]+\.%s(?:[?#][^"'`\s<>]*)?)["'`]""" % EXT, re.I),
]
LOCAL_EXT = re.compile(r"\.%s$" % EXT, re.I)


def is_local(ref: str) -> bool:
    return not (
        re.match(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", ref, re.I)  # http:, data:, mailto:, //cdn, #anchor
        or "${" in ref
        or "{{" in ref
    )


def main() -> int:
    missing = []
    checked = 0
    only = set(sys.argv[1:])  # optional: limit to these page names, e.g. Jinbei.html
    for page in sorted(ROOT.glob("*.html")):
        if only and page.name not in only:
            continue
        text = page.read_text(encoding="utf-8", errors="replace")
        seen = set()
        for rx in CANDIDATES:
            for ref in rx.findall(text):
                ref = ref.strip()
                if not is_local(ref):
                    continue
                clean = unquote(re.split(r"[?#]", ref)[0])
                if not clean or not LOCAL_EXT.search(clean) or clean in seen:
                    continue
                seen.add(clean)
                target = (ROOT / clean.lstrip("/")) if clean.startswith("/") else (page.parent / clean)
                checked += 1
                if not target.resolve().is_file():
                    missing.append((page.name, ref))
    if missing:
        print(f"{len(missing)} broken reference(s):")
        for page, ref in missing:
            print(f"  {page}: {ref}")
        return 1
    print(f"OK - {checked} local references resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
