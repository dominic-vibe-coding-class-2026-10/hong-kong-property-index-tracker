# Deployment log — Hong Kong property index tracker

Recorded on Sunday, 15 November 2026, Asia/Hong Kong (HKT), for the Thursday class report.

## Live service

- Public URL: https://43b8-64-177-61-125.ngrok-free.app
- App on the Atlanta VM (`64.177.61.125`), listening on `127.0.0.1:5050`
- systemd unit: `hk-property-dashboard.service` (enabled, starts on boot)
- Weekly pipeline: `hk-property-pipeline.timer` at Monday 08:00 HKT (`Persistent=true`, up to 2 minutes randomized delay)
- Next scheduled run at the time of this log: Monday, 16 November 2026, 08:01 HKT
- Attribution on the dashboard header and page title: Dominic Yu, [dominic@data-science-hk.org](mailto:dominic@data-science-hk.org)

The ngrok free URL can change if the tunnel service is recreated. The dashboard itself is served locally on port 5050.

## Git log

Commits on `main` as of this deployment note:

| Commit | Time (HKT) | Author | Message |
| --- | --- | --- | --- |
| [`5baf212`](https://github.com/dominic-vibe-coding-class-2026-10/hong-kong-property-index-tracker/commit/5baf212) | 2026-11-15 17:25 | Dominic Yu | Add the Hong Kong property index tracker. |
| [`962c8fc`](https://github.com/dominic-vibe-coding-class-2026-10/hong-kong-property-index-tracker/commit/962c8fc) | 2026-11-15 17:59 | Dominic Yu | Add the post-manifest Cursor conversation transcript. |
| [`d3e1f78`](https://github.com/dominic-vibe-coding-class-2026-10/hong-kong-property-index-tracker/commit/d3e1f786dbd7ed39a91564d825c343472422c106) | 2026-11-15 | Dominic Yu | Show author details on the dashboard and record deployment outcomes. |

Remote: `git@github.com:dominic-vibe-coding-class-2026-10/hong-kong-property-index-tracker.git`

## Still to do before the scheduled jobs can refresh data

The `.env` file is present but API keys (Ollama, and Tavily / Firecrawl for the adaptive sources) still need to be filled in on the VM. Until then the dashboard can stay up, but the Monday pipeline may not produce a complete new update.
