# CYBER PULSE — GitHub-ready Cybersecurity News Dashboard

Dark responsive dashboard for cybersecurity news using RSS + GitHub Actions.

## Setup
1. Create a GitHub repository and upload this folder.
2. Settings → Pages → Deploy from branch → `main` → `/ (root)`.
3. Actions → Update Cyber Pulse → Run workflow.
4. Open the published Pages site.

## Included
- 17 Greek + international configurable sources
- Server-side RSS collection every 15 minutes
- Search/source/category/age filters
- Images, titles, summaries, dates, source and HOT flags
- Article click opens the original story in a new tab
- `data/status.json` records per-source failures
- AI Brief UI with a no-key heuristic fallback

## Add feeds
Edit `data/sources.json` and add `{ "name": "...", "url": "...", "enabled": true }`.

## Local test
`python -m http.server 8000` then open `http://localhost:8000`.
