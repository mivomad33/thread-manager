# Development guide

[한국어](DEVELOPMENT.md) | **English** · [Back to README](README.en.md)

Reads the work history of the projects in the parent folder (`projects_root` in `config.json`, `..` by default), writes Threads post drafts, and picks one of them to post.

```
scheduled run → /threads-auto    : write drafts with /threads-draft → pick one remaining draft and post → notify
you           → /threads-draft   : write drafts only (never posts)
you           → /threads-publish : review drafts yourself → approve / edit / reject → post approved ones only. Record why an auto post was deleted
```

## Files
| File | Contents |
|---|---|
| `config.json` | Folders to exclude, number of drafts per run, auto-publish switch (`auto_publish`) |
| `style.md` | What to post and what not to, tone. Reasons for rejecting or deleting posts accumulate here |
| `state.json` | Last checked commit per repository (generated) |
| `drafts/` | Drafts not yet posted. `status`: draft → approved → posted, or rejected. A post deleted after publishing becomes deleted. Auto-posted drafts get `approved_by: auto` |
| `drafts/images/` | Images for drafts (screenshots, images from the repository) |
| `drafts/archive/` | Finished drafts (posted, rejected, deleted) and drafts older than 14 days (expired), moved here with their images. Kept, not deleted |
| `backlog.json` | Candidate topics pushed out by the cap (3 per run). Reconsidered on the next run, dropped after 14 days |
| `posts.log` | Posted entries (JSON Lines). `approved_by` tells automatic and manual posts apart |
| `.env` | Threads token (not committed) |
| `scripts/collect.py` | Collects commits; `--save` stores the checkpoint |
| `scripts/threads.py` | Token management, draft checks, link checks, image upload, posting |
| `scripts/shot.mjs` | Web page screenshots (Playwright). Run `npm install` first |

`state.json`, `backlog.json`, `posts.log`, and the drafts and images inside `drafts/` are runtime data and are not committed,
because they contain private repository names and commits and drafts that are not public yet.

## Images
When a topic has a UI, the draft uses a screenshot of the deployed public site (or demo), or an image already in the repository.
A dev server is used only for public repositories that start without login using demo data. Claude opens every image
and discards it if personal data is visible.

The Threads API only accepts images at a public URL, so when a draft is posted its images are uploaded to the public repository
[mivomad33/threads-images](https://github.com/mivomad33/threads-images) and posted from there.
Images of drafts that are not posted are never uploaded. Uploaded images stay public in that repository even if the post is deleted.

To use another account, create your own public image repository and change `images_repo` in `config.json`.

## Target repositories
Every run finds all git repositories directly under `projects_root`. New projects are included automatically,
starting from the last 7 days of commits when first seen. Add folders to skip to `exclude` in `config.json`.

Each repository's visibility is checked with `gh`. Drafts from non-public repositories leave out repository links
and unreleased details. Auto-publishing posts drafts from private repositories too.
When you review drafts yourself, they are flagged as coming from a private source.

## Getting a Threads token (once)
1. Sign in to [Meta for Developers](https://developers.facebook.com/apps) with a Facebook account and register as a developer (phone verification)
2. Create an app → choose the **Access the Threads API** use case (no business portfolio needed)
3. Customize the use case → add the `threads_content_publish` permission (`threads_basic` is included by default)
4. App roles → add people → add your Threads account as a **Threads tester** → accept the invite in the Threads app under Settings → Account → Website permissions → Invites
5. In the use case settings, use the **User token generator** → **Generate access token** → approve in the Threads popup. You get a 60-day long-lived token (public accounts only)
6. Save it in `.env`
   ```
   THREADS_ACCESS_TOKEN=...
   ```
7. Check: `python3 scripts/threads.py whoami`

Long-lived tokens expire after 60 days. When posting, the token is refreshed automatically if it is 30 days or older.
If nothing was posted for more than 60 days, repeat steps 5–6.
If you got a short-lived (1 hour) token, put `THREADS_APP_SECRET` in `.env` and exchange it with `python3 scripts/threads.py exchange <short-lived token>`.

## Scheduled runs (auto-publishing)
Run `threads-auto` periodically with a scheduled task in the Claude desktop app. Example: weekdays at 10 AM (`0 10 * * 1-5`).
Put the following in the task instructions.

- Read `.claude/skills/threads-auto/SKILL.md` and follow it exactly. Run commands in this repository's folder
- You allowed auto-publishing in advance and do not review posts beforehand
- Post at most one per run. Do not post if something was already posted today (Korea time) or a draft fails a check
- If `auto_publish` in `config.json` is not `true`, only write drafts
- If posting fails, do not retry or post a different draft
- Only read files in the target repositories
- Right after posting, send the post link with PushNotification. Finish with a short report: commits reviewed, new drafts, the post, topics skipped

Check published posts on Threads. Threads posts can be edited only for a few minutes after posting, so look as soon as the notification arrives.
If something is wrong, delete it in the Threads app and tell Claude why (`/threads-publish`). The reason is kept in `style.md` and shapes later picks.
To stop auto-publishing, set `auto_publish` to `false` or turn off the scheduled task.

Scheduled tasks run while the app is open. If the app was closed, the task runs the next time it starts.

## Common commands
```bash
python3 scripts/collect.py
python3 scripts/collect.py --save
python3 scripts/threads.py check drafts/<file>.md
python3 scripts/threads.py archive
python3 scripts/threads.py quota
node scripts/shot.mjs <url> drafts/images/<name>.png --mobile
```
