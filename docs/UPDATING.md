# Updating the site

Two things are updated from a form, no file editing:

| What | Form | Changes |
|---|---|---|
| Dutch Duolingo score | **Update Dutch score** | `Jinbei.html` (number, level text, optional note) |
| Blog post | **New Chopper log entry** | new card at the top of `Chopper.html` |

**To update:** repo → **Issues → New issue** → pick a form → fill it in → **Submit new issue**
(works from the GitHub mobile app too).

Bookmarks:
- https://github.com/devadarshan5/portfolio/issues/new?template=dutch-score.yml
- https://github.com/devadarshan5/portfolio/issues/new?template=chopper-entry.yml

Prefill a field from the link by adding its id, e.g. `...dutch-score.yml&score=31`.

## What happens after you submit

1. A GitHub Action reads the form and edits the HTML.
2. It checks that every image/audio/page the changed page references exists, then opens
   the page in headless Chromium and fails on any JS error or missing file.
3. If that passes it commits to `main`. GitHub Pages then publishes it.
4. It waits until the new content is visible on the live site, replies on the issue with the
   link and closes it. If anything fails, **nothing is published** and the reply says why.

Only issues opened by the repo owner are processed.

## One-time setup

1. **Settings → Actions → General → Workflow permissions →** "Read and write permissions".
2. **Settings → Pages:** source stays "Deploy from a branch" (`main`, `/ (root)`).
3. Apply the three `id`s to the Dutch entry in `Jinbei.html` (the script finds the elements by id):
   `duo-nl-note`, `duo-nl-score`, `duo-nl-tier`.
4. Optional **Settings → Secrets and variables → Actions → Variables:**
   - `SITE_TZ`: e.g. `Asia/Kolkata`. Timezone for the auto-dated "Nov 18" label (default UTC).
   - `SITE_URL`: only if the live site is on a custom domain.

If `main` is branch-protected, allow `github-actions[bot]` to push or the publish step will fail.

## Writing tips (Chopper form)

- `[link text](https://example.com)` becomes a link; a blank line starts a new paragraph.
- Plain text only otherwise: anything like `<b>` is shown literally, not rendered.
- Leave **Date** empty for today's date, or give `YYYY-MM-DD` to backdate.
- Only the newest card keeps the NEW! sticker.

## Checks you can run yourself

```bash
python3 scripts/check_assets.py          # every referenced file exists (case-sensitive, like Pages)
npm ci && npx playwright install chromium
npm test                                 # opens every page, fails on JS errors / 404s
PAGES=Jinbei.html npm test               # just one page
```

`Validate site` runs both on every push to `main` and every pull request.

## Dry-run an update locally

```bash
python3 scripts/update_content.py --body-file my-update.md --dry-run
```

where `my-update.md` looks like the issue body (`### Duolingo score`, blank line, `24`, ...).
