from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path


QUERIES = [
    "AI测试工程师 面试题 牛客 大模型测试",
    "AI测开 面试题 大模型 评测 RAG",
    "大模型业务测试 面试题 测试开发 牛客",
    "AI产品经理 面试题 Agent RAG 产品指标 牛客",
    "小红书 AI产品经理 面经 社招",
    "小红书 Agent开发 面试 一面 二面 多久",
    "小红书 AI Agent开发 面经 RAG 工具调用",
    "小红书 测试开发 面试 一面 二面 多久",
    "小红书 测开 实习 面经 Linux adb pytest",
    "Agent测试 面试题 评测 RAG 工具调用 质量",
    "AI应用开发 面试 Agent 测试 可靠性 评测",
]


def search_urls(query: str) -> dict[str, str]:
    encoded = urllib.parse.quote(query)
    return {
        "bing": f"https://www.bing.com/search?q={encoded}",
        "google": f"https://www.google.com/search?q={encoded}",
        "xiaohongshu": f"https://www.xiaohongshu.com/search_result?keyword={encoded}",
        "nowcoder": f"https://www.nowcoder.com/search?query={encoded}",
    }


def main() -> int:
    out = Path("data/discovery-links.json")
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])

    payload = {
        "note": "Open these searches in a logged-in browser when needed. Do not bypass login, captcha, or platform access controls.",
        "queries": [{"query": query, "urls": search_urls(query)} for query in QUERIES],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
