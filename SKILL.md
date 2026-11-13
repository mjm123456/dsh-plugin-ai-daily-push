---
name: ai-daily-push
version: 0.1.0
allowed-tools: web_search, web_fetch, bash, read, write
description: 每日 AI 新闻简报并推送到微信。检索最近 24 小时的 AI 新闻，去重后按重要性挑出 5 条，写成 800 字以内的中文 Markdown 简报（标题「AI 日报 · YYYY-MM-DD」，每条含 2–3 句摘要与真实来源链接），按日期归档并推送到微信（Server酱 / PushPlus / WxPusher / 企业微信群机器人），再汇报推送结果。当用户要求「每日 AI 新闻」「AI 日报」「今天有什么 AI 消息并推到微信」「把简报发我微信」「补写昨天/前几天的简报」，或任何定时/手动生成新闻摘要并推送的场景时使用。
---

# 每日 AI 新闻简报 → 微信

一条流水线：**检索 → 筛选 5 条 → 写简报 → 归档 → 推微信 → 汇报**。
每一步都有明确的失败分支，**不要**在失败时编造替代信息或换别的发送方式。

## 运行前提

| 级别 | 需要什么 | 缺失时 |
|---|---|---|
| 必需 | 一个可用的联网搜索能力（`web_search`），以及至少一条能抓正文的链路（`web_fetch` 或 `curl`） | 如实报告「检索能力不可用」，**禁止**用模型记忆凑新闻 |
| 必需 | Python 3（`python3` 在 PATH 上） | 推送无法进行，如实报告 |
| 必需 | 微信推送通道配置（见下） | 简报照常写完并归档，回复里说明「微信推送通道尚未配置」 |

本技能的所有脚本都在**本 SKILL.md 所在目录**（下文记作 `<技能目录>`，即 `~/.dsh/skills/ai-daily-push/`）：

- `scripts/push.py` —— 推送脚本，只用 Python 标准库，支持四种通道。
- `scripts/queue.py` —— 补写队列（缺哪天的简报）。
- 给 cron 用的入口在插件包形态里（`bin/dsh-ai-daily.mjs`），单独装技能时没有；
  cron 直接调用 `python3 <技能目录>/scripts/queue.py tick --quiet` 即可（无新增时静默）。

## 配置推送通道（用户一次性完成）

微信个人号没有官方机器人接口，需要借一个第三方通道。配置文件路径：

```
~/.dsh/ai-daily-push/config.env        # chmod 600 它
```

内容只写一种通道即可：

```ini
# A｜Server酱³（推荐）：微信扫码登录 sct.ftqq.com，复制 SCT 开头的 SendKey 并关注服务号
SERVERCHAN_SENDKEY=SCT...
# B｜PushPlus：pushplus.plus 扫码拿 token
# PUSHPLUS_TOKEN=...
# C｜WxPusher：appToken + 自己的 UID（多个用逗号）
# WXPUSHER_APP_TOKEN=...
# WXPUSHER_UID=UID_xxx
# D｜企业微信群机器人：群设置 → 群机器人 → 添加 → 复制完整 Webhook
# WECOM_WEBHOOK=https://qyapi.weixin...
```

环境变量优先于文件。**永远不要把真实密钥写进对话、日志、简报或 git**；
需要排查时只跑 `--check`，它会输出通道名而不输出密钥。

## 第 0 步：检查待补写的日子

```bash
python3 <技能目录>/scripts/queue.py list          # 列出缺简报的日期，可能为空
python3 <技能目录>/scripts/push.py --check        # 退出码 0 = 通道已配置
```

- `queue.py list` 输出若干日期时，先问用户是否补写；同意后按「第 2–6 步」逐天补写，
  每写完一天执行 `python3 <技能目录>/scripts/queue.py pop --date <日期>` 把它出队。
- `--check` 退出码非 0：**仍然**完成简报的检索、写作与归档（第 2–4 步），
  第 5 步跳过，最后回复「微信推送通道尚未配置，请按 README 填写 ~/.dsh/ai-daily-push/config.env」。

## 第 1 步：检索

- 范围：最近 24 小时（补写时以目标日期为准）。
- 来源优先级：官方博客/公告/模型卡 > 权威媒体（Reuters、AP、Bloomberg、FT、CNBC）>
  主流科技媒体（The Verge、TechCrunch、Wired、Ars Technica、36氪、机器之心等）。
- 优先覆盖：模型/产品发布、重要融资与并购、监管与政策、关键研究进展、行业大事件。
- **每条入选新闻都要用 `web_fetch`（或 `curl -sL <url>`）打开原文核实**，
  确认标题、数字、日期与原文一致。拿不到原文的就不选。

## 第 2 步：筛选与去重

- 同一事件只算一条（比如「某公司融资」多家报道只取信息最全的一条，可并列第二名来源）。
- 按「重要性 × 影响面 × 时效性」排序，取前 5 条。宁可少一条，也不凑数。

## 第 3 步：写简报（Markdown，800 字以内）

```markdown
# AI 日报 · YYYY-MM-DD

**1. 标题（不超过 25 字，说结果不说口号）**
2–3 句话：发生了什么（带上关键数字）、为什么重要（对谁有影响）。
来源：媒体名 — https://真实链接

**2. ……**（同样结构，共 5 条）

今日看点：一句话总结今天的主线。
```

硬性要求：

- **链接必须是检索结果里真实出现、且已打开过的 URL**，不得编造、不得改造。
- 中文表达，避免营销词；每条控制在 80 字以内，手机上两三行读完。
- 涉及数字、估值、日期时，以原文为准，原文没说的不写。

## 第 4 步：归档

写入 `~/.dsh/ai-daily-push/digests/ai-YYYY-MM-DD.md`（同名存在则覆盖为最终版，
不存在则先 `mkdir -p`）。用户指定了别的目录时以用户为准。

## 第 5 步：推送

```bash
python3 <技能目录>/scripts/push.py --check
# 仅当上一条退出码为 0 时：
python3 <技能目录>/scripts/push.py --title "AI 日报 · YYYY-MM-DD" --file ~/.dsh/ai-daily-push/digests/ai-YYYY-MM-DD.md
```

- 退出码 0 = 服务确认成功；脚本会打印服务返回体（密钥已打码）。
- 退出码 1 = 服务拒绝或网络失败：把服务返回的**错误原文**转述给用户，不要重试超过 1 次。
- 退出码 2 = 未配置：按第 0 步的处理方式说明，**不要**尝试邮件、短信、剪贴板等其他发送方式。

## 第 6 步：汇报

在回复里给出：5 条简报全文、推送结果（成功 / 未配置 / 失败 + 服务返回的错误）、
以及简报文件路径。推送成功时，推送服务的返回体里带 pushid，可以一并给出便于排查。

## 常见故障

| 现象 | 处理 |
|---|---|
| `CERTIFICATE_VERIFY_FAILED` | 脚本会依次尝试系统 CA、Homebrew CA、certifi；都失败时提示用户设置 `SSL_CERT_FILE`，**不要**改成跳过校验 |
| 服务返回 `code != 0` | 按返回体判断：key 错误、通道未关注/未激活、频率超限。原样转述 |
| 微信里排版乱 | PushPlus / WxPusher 需 markdown 模板（脚本已带）；企业微信机器人上限 4KB，脚本会截断 |
| 定时任务没触发 | DSH 定时任务只在宿主运行时触发；改用 cron 跑 `python3 <技能目录>/scripts/queue.py tick --quiet`（重定向到日志）记队列，下次开 App 时按 `queue.py list` 补写 |
| 日志里有密钥 | `push.py` 与 `dsh-ai-daily doctor` 都会打码；如发现明文，提醒用户轮换该 key |

## 不要做的事

- 不要编造新闻、链接、数字或来源。
- 不要在用户没有授权的情况下把简报发到其他渠道（群、公众号接口、邮件）。
- 不要把 `config.env` 的内容打印出来或写进任何文件。
