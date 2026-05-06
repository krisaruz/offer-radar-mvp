#!/usr/bin/env python3
"""
飞书 Webhook 推送脚本 - 将当天新采集的面经推送到飞书群。

通过环境变量 FEISHU_WEBHOOK 获取 Webhook 地址。
读取 data/interview-events.json 中 sourceDate 为今天的事件并推送。

用法：
    FEISHU_WEBHOOK=https://open.feishu.cn/... python scripts/notify_feishu.py

    # 测试模式（不真正发送，打印 payload）
    python scripts/notify_feishu.py --dry-run
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")
EVENTS_FILE = DATA_DIR / "interview-events.json"

PAGES_URL = os.environ.get("PAGES_URL", "")


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_today_events() -> list[dict[str, Any]]:
    """加载今天新采集的事件。"""
    if not EVENTS_FILE.exists():
        return []
    data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    today = utc_date()
    return [
        e for e in data.get("events", [])
        if e.get("sourceDate") == today and e.get("recruitingType") != "excluded"
    ]


def build_event_element(event: dict) -> dict:
    """构建单条面经的飞书富文本元素。"""
    platform = event.get("sourcePlatform", "未知")
    track = event.get("roleTrack", "通用")
    title = event.get("title", "无标题")[:40]
    source_url = event.get("sourceUrl", "")

    # 提取前 3 个问题
    questions = []
    for r in event.get("rounds", []):
        for q in r.get("questions", []):
            questions.append(q)
            if len(questions) >= 3:
                break
        if len(questions) >= 3:
            break

    # 构建 markdown 文本
    lines = [f"**[{platform}] {track}** | {title}"]
    for q in questions:
        lines.append(f"  • {q[:60]}")
    if source_url:
        lines.append(f"  [查看原帖]({source_url})")

    return "\n".join(lines)


def build_card(events: list[dict]) -> dict:
    """构建飞书 Interactive Card 消息体。"""
    today = utc_date()
    count = len(events)

    header = {
        "template": "blue",
        "title": {
            "tag": "plain_text",
            "content": f"面经雷达 - {today} 新增 {count} 条"
        }
    }

    elements: list[dict] = []

    # 分隔线
    elements.append({"tag": "hr"})

    # 每条面经
    for event in events[:10]:  # 最多显示 10 条
        md_content = build_event_element(event)
        elements.append({
            "tag": "markdown",
            "content": md_content
        })
        elements.append({"tag": "hr"})

    # 底部操作区
    actions = []
    if PAGES_URL:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看完整看板"},
            "type": "primary",
            "url": PAGES_URL
        })

    # 统计摘要
    tracks = {}
    for e in events:
        t = e.get("roleTrack", "通用")
        tracks[t] = tracks.get(t, 0) + 1
    track_summary = " | ".join(f"{k}: {v}" for k, v in sorted(tracks.items(), key=lambda x: -x[1]))

    elements.append({
        "tag": "markdown",
        "content": f"**方向分布**: {track_summary}\n**数据来源**: {'、'.join(set(e.get('sourcePlatform', '') for e in events))}"
    })

    if actions:
        elements.append({"tag": "action", "actions": actions})

    return {
        "header": header,
        "elements": elements
    }


def build_no_data_message() -> dict:
    """当天无新数据时的消息。"""
    today = utc_date()
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "grey",
                "title": {
                    "tag": "plain_text",
                    "content": f"面经雷达 - {today} 暂无新面经"
                }
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": "今日采集未发现新的面经帖子。\n可能原因：数据源暂无更新，或 Cookie 需要刷新。"
                }
            ]
        }
    }


def send_webhook(webhook_url: str, payload: dict) -> bool:
    """发送消息到飞书 Webhook。"""
    import urllib.request
    import urllib.error

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                print(f"[OK] 飞书推送成功")
                return True
            else:
                print(f"[WARN] 飞书返回异常: {result}")
                return False
    except urllib.error.URLError as e:
        print(f"[ERROR] 飞书推送失败: {e}")
        return False


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    webhook_url = os.environ.get("FEISHU_WEBHOOK", "")
    if not webhook_url and not dry_run:
        print("[ERROR] 未设置 FEISHU_WEBHOOK 环境变量")
        print("  设置方式: export FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
        return 1

    events = load_today_events()
    print(f"[{utc_date()}] 今日新增面经: {len(events)} 条")

    if events:
        card = build_card(events)
        payload = {"msg_type": "interactive", "card": card}
    else:
        payload = build_no_data_message()

    if dry_run:
        print("\n[DRY RUN] 以下为将要发送的消息:")
        output = json.dumps(payload, ensure_ascii=False, indent=2)
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        return 0

    success = send_webhook(webhook_url, payload)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
