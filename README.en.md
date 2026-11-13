# dsh-plugin-ai-daily-push

A daily AI-news → WeChat skill pack for DeepSeek Harness: it searches the last 24 hours of
AI news, de-duplicates and picks five stories, writes an 800-character Chinese Markdown
brief, archives it by date, and pushes it to WeChat.

[中文说明](README.md)

| Part | What it does |
|---|---|
| `SKILL.md` | The skill: search → select → write → archive → push → report, with explicit failure branches and a no-fabrication rule |
| `scripts/push.py` | Push script, Python standard library only; supports ServerChan, PushPlus, WxPusher and a WeCom group bot |
| `scripts/queue.py` | Catch-up queue: records which dates are missing a brief so the agent can backfill them later |
| `bin/dsh-ai-daily.mjs` | Entry point for cron / launchd / Task Scheduler (`tick`, `list`, `check`, `push`, `doctor`) |

## Install

```sh
dsh plugin --profile web add dsh-plugin-ai-daily-push
```

On DSH Desktop (0.2.1+), install from **Settings → Plugins** instead: the desktop app uses the
`desktop` profile, so a command-line `--profile web` install will not show up there. From source:

```sh
dsh plugin --profile web add github:mjm123456/dsh-plugin-ai-daily-push
```

After a restart (or a page refresh) the skill `ai-daily-push` appears in the session skill catalog.

## Configure a push channel (one-time)

Neither requirement is in the package: the key lives in your home directory.

```sh
mkdir -p ~/.dsh/ai-daily-push && chmod 700 ~/.dsh/ai-daily-push
printf 'SERVERCHAN_SENDKEY=SCTxxxxxxxx\n' > ~/.dsh/ai-daily-push/config.env
chmod 600 ~/.dsh/ai-daily-push/config.env
```

| Channel | Keys | Notes |
|---|---|---|
| ServerChan | `SERVERCHAN_SENDKEY` | Scan-to-login at sct.ftqq.com, then follow its WeChat service account |
| PushPlus | `PUSHPLUS_TOKEN` | Markdown template is used |
| WxPusher | `WXPUSHER_APP_TOKEN`, `WXPUSHER_UID` (comma-separated) | Multiple recipients |
| WeCom group bot | `WECOM_WEBHOOK` | Message lands in a WeCom group; truncated at 4 KB |

Environment variables win over the file; `SERVERCHAN_API` overrides the endpoint for a self-hosted sctp.

```sh
python3 <package>/scripts/push.py --check --verbose
node <package>/bin/dsh-ai-daily.mjs check
```

## Use it

Ask the agent "generate today's AI daily and push it to WeChat", or name the `ai-daily-push` skill
explicitly. For scheduling, create a daily DSH scheduled task with the prompt
"use the ai-daily-push skill to generate and push today's AI daily", and add a cron job running
`dsh-ai-daily.mjs tick` so days missed while the desktop app was closed are queued for backfill.

## Security

Digest text passes through a third-party push server — do not push sensitive content. `config.env`
holds a plaintext key: `chmod 600` it and keep it out of git. `push.py` and `dsh-ai-daily doctor`
redact keys in their output, and TLS verification is never disabled.

## License

MIT
