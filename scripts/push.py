#!/usr/bin/env python3
"""把一段 Markdown 推送到微信（经第三方推送服务或企业微信群机器人）。

这是一份自包含脚本：只用 Python 标准库，可直接拷到任意机器上跑。

用法：
    python3 push.py --check
    python3 push.py --title "AI 日报 2026-11-06" --file digest.md
    cat digest.md | python3 push.py --title "AI 日报 2026-11-06"
    python3 push.py --channel serverchan --title "..." --file digest.md --verbose

配置：每行 KEY=VALUE，按以下顺序查找，先找到的优先：
    1. 环境变量（如 SERVERCHAN_SENDKEY）
    2. --config 指定的文件
    3. 默认 ~/.dsh/ai-daily-push/config.env
    4. 脚本所在目录下的 config.env（老版本的位置，兼容用）

    SERVERCHAN_SENDKEY    Server酱³ SendKey（SCT 开头）
    SERVERCHAN_API        可选，自定义 Server酱 接口完整 URL（自建 sctp 用）
    PUSHPLUS_TOKEN        PushPlus token
    WXPUSHER_APP_TOKEN    WxPusher appToken
    WXPUSHER_UID          WxPusher 接收者 UID，多个用英文逗号分隔
    WECOM_WEBHOOK         企业微信群机器人 Webhook 完整 URL

退出码：0 成功；1 推送失败；2 未配置 / 参数错误。
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = Path.home() / ".dsh" / "ai-daily-push" / "config.env"
LEGACY_CONFIG = HERE / "config.env"

CHANNELS = ("serverchan", "pushplus", "wxpusher", "wecom")
KEYS = (
    "SERVERCHAN_SENDKEY", "SERVERCHAN_API", "PUSHPLUS_TOKEN",
    "WXPUSHER_APP_TOKEN", "WXPUSHER_UID", "WECOM_WEBHOOK",
)
# 以这些开头的值视为「还没填」的占位符。
PLACEHOLDERS = ("YOUR_", "<", "粘贴", "xxxx", "XXXX")


def redact(text: str, cfg: dict) -> str:
    """把返回体里可能回显的密钥打码，再写进日志/终端。

    推送服务偶尔会在返回体里带上部分 key（例如错误信息里包含 token 前缀）。
    日志不进 git，但也别让它变成第二份密钥副本。
    """
    for key in KEYS:
        value = cfg.get(key)
        if not value or len(value) < 8:
            continue
        text = text.replace(value, value[:4] + "***")
        # 只展示尾部的形式也别漏：对 4 位以上、8 位以下的值不做处理，避免误伤短字符串
    return text


def ssl_context() -> ssl.SSLContext:
    """返回一个能验过证书的 SSLContext。

    python.org 版 macOS Python 的默认 CA 文件常常不存在，导致
    CERTIFICATE_VERIFY_FAILED。这里按「环境变量 -> 系统 bundle -> certifi」顺序
    挑一个可用的 CA 文件；仍然保持证书校验开启，不做任何跳过。
    """
    bundle = os.environ.get("SSL_CERT_FILE")
    if not bundle or not Path(bundle).is_file():
        for candidate in (
            "/etc/ssl/cert.pem",                       # macOS 系统 bundle
            "/etc/ssl/certs/ca-certificates.crt",     # Linux
            "/opt/homebrew/etc/openssl@3/cert.pem",   # Apple Silicon Homebrew
            "/usr/local/etc/openssl@3/cert.pem",      # Intel Homebrew
            "/Library/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem",
        ):
            if Path(candidate).is_file():
                bundle = candidate
                break
    if not bundle or not Path(bundle).is_file():
        try:
            import certifi
            bundle = certifi.where()
        except ImportError:
            bundle = None
    return ssl.create_default_context(cafile=bundle) if bundle else ssl.create_default_context()


def _read_env(path: Path) -> dict:
    cfg = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value and not value.startswith(PLACEHOLDERS):
            cfg[key.strip()] = value
    return cfg


def load_config(explicit: str | None = None) -> dict:
    """按优先级合并配置；返回实际用到的文件也在 `_source` 里（便于 --verbose 排错）。"""
    cfg: dict = {}
    sources = []
    for path in ([Path(explicit)] if explicit else []) + [DEFAULT_CONFIG, LEGACY_CONFIG]:
        if path.is_file():
            cfg.update(_read_env(path))
            sources.append(str(path))
    for key in KEYS:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
            sources.append(f"env:{key}")
    cfg["_source"] = ", ".join(sources) or "（无）"
    return cfg


def available(cfg: dict) -> list:
    found = []
    if cfg.get("SERVERCHAN_SENDKEY"):
        found.append("serverchan")
    if cfg.get("PUSHPLUS_TOKEN"):
        found.append("pushplus")
    if cfg.get("WXPUSHER_APP_TOKEN") and cfg.get("WXPUSHER_UID"):
        found.append("wxpusher")
    if cfg.get("WECOM_WEBHOOK", "").startswith("https://"):
        found.append("wecom")
    return found


def request(url: str, data: bytes, headers: dict) -> str:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20, context=ssl_context()) as resp:
        return resp.read().decode("utf-8", "replace")


def send(channel: str, cfg: dict, title: str, text: str) -> str:
    if channel == "serverchan":
        key = cfg["SERVERCHAN_SENDKEY"]
        url = cfg.get("SERVERCHAN_API") or f"https://sctapi.ftqq.com/{key}.send"
        body = urllib.parse.urlencode({"title": title[:32], "desp": text}).encode()
        return request(url, body, {"Content-Type": "application/x-www-form-urlencoded"})

    if channel == "pushplus":
        payload = {
            "token": cfg["PUSHPLUS_TOKEN"],
            "title": title[:100],
            "content": text,
            "template": "markdown",
        }
        return request(
            "https://www.pushplus.plus/send",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json"},
        )

    if channel == "wxpusher":
        payload = {
            "appToken": cfg["WXPUSHER_APP_TOKEN"],
            "uids": [u.strip() for u in cfg["WXPUSHER_UID"].split(",") if u.strip()],
            "content": f"## {title}\n\n{text}",
            "contentType": 3,  # markdown
        }
        return request(
            "https://wxpusher.zjiecode.com/api/send/message",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json"},
        )

    if channel == "wecom":
        content = text
        while len(content.encode("utf-8")) > 4000:  # 企业微信 markdown 上限
            content = content[: len(content) - 200]
        content = f"# {title}\n\n{content}"
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        return request(
            cfg["WECOM_WEBHOOK"],
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json"},
        )

    raise ValueError(f"未知通道: {channel}")


def sent_ok(channel: str, raw: str) -> bool:
    """判断服务返回体是否表示成功。返回体格式各家不同，这里只做保守判断。"""
    try:
        data = json.loads(raw)
    except ValueError:
        return True  # 不是 JSON 的返回体无法判断，交给调用方看原文
    if channel == "serverchan":
        return data.get("code") == 0
    if channel == "pushplus":
        return data.get("code") == 200
    if channel == "wxpusher":
        return data.get("code") == 1000
    if channel == "wecom":
        return data.get("errcode") == 0
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="把 Markdown 推送到微信")
    ap.add_argument("--title", default="AI 日报")
    ap.add_argument("--file", help="要推送的文本文件；省略则从 stdin 读取")
    ap.add_argument("--channel", choices=CHANNELS, help="强制指定通道，默认用第一个已配置的")
    ap.add_argument("--config", help="额外的 config.env 路径")
    ap.add_argument("--check", action="store_true", help="只列出已配置通道，不发送")
    ap.add_argument("--verbose", action="store_true", help="打印配置文件位置")
    args = ap.parse_args()

    cfg = load_config(args.config)
    ready = available(cfg)
    if args.check:
        print("已配置的微信推送通道: " + (", ".join(ready) if ready else "无"))
        if args.verbose:
            print(f"配置文件: {cfg['_source']}")
        return 0 if ready else 2
    if not ready:
        print(
            "未配置任何微信推送通道，请把 Key/Token 填入 ~/.dsh/ai-daily-push/config.env",
            file=sys.stderr,
        )
        return 2
    channel = args.channel or ready[0]
    if channel not in ready:
        print(f"通道 {channel} 尚未配置；当前可用: {', '.join(ready)}", file=sys.stderr)
        return 2

    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    if not text.strip():
        print("推送内容为空", file=sys.stderr)
        return 2
    try:
        result = send(channel, cfg, args.title, text)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"[{channel}] 推送失败: {redact(str(exc), cfg)}", file=sys.stderr)
        return 1
    print(f"[{channel}] 已发送，服务返回: {redact(result, cfg)[:500]}")
    return 0 if sent_ok(channel, result) else 1


if __name__ == "__main__":
    raise SystemExit(main())
