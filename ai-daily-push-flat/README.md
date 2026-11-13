# ai-daily-push · 技能包（可独立上架）

「每日 AI 新闻 → 中文简报 → 微信推送」技能的独立形态：一个文件夹、一份 `SKILL.md`、
两个只用 Python 标准库的脚本，外加让它同时能被 `dsh plugin add` 安装、被插件市场收录的打包文件。
不含需要编译的代码，不含密钥。

```text
ai-daily-push-skill/
├── SKILL.md            # 技能正文（frontmatter: name / version / description / allowed-tools）
├── scripts/
│   ├── push.py         # 推送：Server酱³ / PushPlus / WxPusher / 企业微信群机器人
│   └── queue.py        # 补写队列：记录哪天缺简报，Agent 下次启动补写
├── lib/index.js        # 可选：把 SKILL.md 挂进 ctx.skills 的 provider（插件形态用）
├── cordis.patch.yml    # 可选：插件形态的 loader 注册
├── package.json        # 可选：dsh.bundle + bin，`dsh plugin add` 用
├── tools/selftest.mjs  # 不联网自检
├── LICENSE
└── packaging/
    ├── marketplace-entry.yml   # 插件市场条目（直接放进 awesome-dsh-plugin 的 data/plugins/）
    ├── pr-body.md              # PR 正文
    └── publish.md              # 从技能包到市场收录的完整步骤
```

| 你想要的形态 | 需要的文件 |
|---|---|
| 只当技能用（拷进 `~/.dsh/skills/`） | `SKILL.md` + `scripts/` |
| `dsh plugin add` 安装、进插件市场 | 再加上 `package.json`、`cordis.patch.yml`、`lib/` |

## 装到本机（验证用）

```sh
mkdir -p ~/.dsh/skills
cp -R ai-daily-push-skill ~/.dsh/skills/ai-daily-push
mkdir -p ~/.dsh/ai-daily-push && chmod 700 ~/.dsh/ai-daily-push
# 写 ~/.dsh/ai-daily-push/config.env（见下）后：
python3 ~/.dsh/skills/ai-daily-push/scripts/push.py --check
```

刷新 DSH（普通 `dsh web` 刷新页面；桌面端需要重启）后，技能目录里会出现 `ai-daily-push`。

## 配置推送通道（一次性）

```sh
printf 'SERVERCHAN_SENDKEY=SCTxxxxxxxx\n' > ~/.dsh/ai-daily-push/config.env
chmod 600 ~/.dsh/ai-daily-push/config.env
```

| 通道 | 需要 | 备注 |
|---|---|---|
| Server酱³ | `SERVERCHAN_SENDKEY` | sct.ftqq.com 扫码登录，关注服务号 |
| PushPlus | `PUSHPLUS_TOKEN` | markdown 模板 |
| WxPusher | `WXPUSHER_APP_TOKEN` + `WXPUSHER_UID`（逗号分隔） | 可多接收者 |
| 企业微信群机器人 | `WECOM_WEBHOOK` | 4KB 截断 |

环境变量优先于文件；`--check` 只输出通道名，不输出密钥。

## 发布

见 [packaging/publish.md](packaging/publish.md)。最短路径：

1. 建公开仓库 `dsh-plugin-ai-daily-push`，把**本文件夹内容**推到仓库根目录（仓库满 1 天才过 CI）；
2. `npm publish --registry=https://registry.npmjs.org`；
3. 向 [awesome-dsh-plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin) 提 PR，只加一个
   `data/plugins/mjm123456__dsh-plugin-ai-daily-push.yml`。

## 自检

```sh
npm run selftest   # 不联网、不发消息，18 项
```

MIT © mjm123456
