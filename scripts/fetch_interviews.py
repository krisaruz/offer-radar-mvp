#!/usr/bin/env python3
"""
Interview data fetcher for GitHub Actions.
Fetches interview posts from public sources (Nowcoder, Bing search results).
Runs daily via GitHub Actions, appends new data to interview-events.json.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Configuration
DATA_DIR = Path("data")
EVENTS_FILE = DATA_DIR / "interview-events.json"
QUESTIONS_FILE = DATA_DIR / "daily-questions.json"

SEARCH_QUERIES = [
    "Agent开发 面试 面经 2026",
    "AI测试 测开 面经 2026",
    "大模型 面经 RAG Agent",
    "AI工程师 面试题 社招 面经",
    "测试开发 面经 一面 二面",
    "LLM 面试 算法 面经",
    "AIGC 面经 offer",
    "MCP Agent 面试",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sha256_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def fetch_url(url: str, timeout: int = 20) -> str:
    """Fetch URL content with proper headers."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return ""


def search_bing(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """
    Search via DuckDuckGo HTML interface and return result URLs.
    Falls back to Bing if DDG fails.
    """
    import urllib.parse
    encoded_query = urllib.parse.quote(query)

    # Try DDG first
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    html = fetch_url(url)
    if html:
        results = _parse_ddg_results(html, max_results)
        if results:
            return results

    # Fallback: Bing search
    url = f"https://www.bing.com/search?q={encoded_query}"
    html = fetch_url(url)
    if html:
        return _parse_bing_results(html, max_results)

    return []


def _parse_ddg_results(html: str, max_results: int) -> list[dict[str, str]]:
    import urllib.parse
    results = []
    for match in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html):
        href = match.group(1)
        title = match.group(2).strip()
        if "uddg=" in href:
            actual_url = href.split("uddg=")[-1].split("&")[0]
            actual_url = urllib.parse.unquote(actual_url)
        else:
            actual_url = href
        results.append({"url": actual_url, "title": title})
        if len(results) >= max_results:
            break
    return results


def _parse_bing_results(html: str, max_results: int) -> list[dict[str, str]]:
    results = []
    for match in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]{5,})</a>', html):
        url = match.group(1)
        title = match.group(2).strip()
        # Skip Bing's own URLs
        if "bing.com" in url or "microsoft.com" in url:
            continue
        results.append({"url": url, "title": title})
        if len(results) >= max_results:
            break
    return results


def scrape_nowcoder_post(url: str) -> dict[str, Any] | None:
    """
    Scrape a Nowcoder discussion post and extract interview info.
    """
    html = fetch_url(url)
    if not html:
        return None

    # Extract title
    title_match = re.search(r'<h1[^>]*class="[^"]*discuss-title[^"]*"[^>]*>([^<]+)</h1>', html)
    if not title_match:
        title_match = re.search(r'<title>([^<]+)</title>', html)
    title = title_match.group(1).strip() if title_match else "未知标题"

    # Extract content
    content_match = re.search(r'<div[^>]*class="[^"]*post-content[^"]*"[^>]*>(.*?)</div>', html, re.S)
    if not content_match:
        content_match = re.search(r'<div[^>]*class="[^"]*j-post-content[^"]*"[^>]*>(.*?)</div>', html, re.S)
    content = content_match.group(1) if content_match else ""
    content = re.sub(r'<[^>]+>', ' ', content)
    content = re.sub(r'\s+', ' ', content).strip()

    # Detect company and role
    company = "未知公司"
    if "小红书" in title or "小红书" in content:
        company = "小红书"
    elif "字节" in title or "抖音" in title:
        company = "字节跳动"
    elif "阿里" in title:
        company = "阿里巴巴"
    elif "腾讯" in title:
        company = "腾讯"

    role_track = "通用"
    title_lower = title.lower()
    content_lower = content.lower()
    if "agent" in title_lower or "agent" in content_lower:
        role_track = "Agent开发"
    elif "ai测" in title_lower or "大模型测试" in title_lower or "模型测试" in title_lower:
        role_track = "AI测开"
    elif "测开" in title_lower or "测试开发" in title_lower:
        role_track = "测开"
    elif "ai产品" in title_lower:
        role_track = "AI产品经理"

    # Extract rounds and questions
    rounds = extract_rounds(content)

    # Detect recruiting type
    recruiting_type = "unspecified"
    if re.search(r"(实习|暑期|校招|秋招|春招|26届|27届)", title + content):
        recruiting_type = "excluded"

    # Extract tags
    tags = extract_tags(title + " " + content)

    event_id = sha256_id(url + title)[:16]

    return {
        "id": f"nowcoder-{event_id}",
        "title": title[:100],
        "company": company,
        "roleTrack": role_track,
        "seniority": "未说明招聘类型",
        "sourcePlatform": "牛客",
        "sourceUrl": url,
        "sourceDate": utc_date(),
        "evidenceLevel": "medium",
        "rounds": rounds,
        "takeaways": [],
        "tags": tags,
        "recruitingType": recruiting_type,
    }


def extract_rounds(content: str) -> list[dict[str, Any]]:
    """Extract interview rounds from content."""
    rounds = []

    # Pattern: 一面/二面/三面 with duration
    round_patterns = [
        (r'一面[^。]*?(?:时长?[：:]\s*(\d+)\s*分钟)?[^。]*?问[了：:]?\s*([^.。!?！？]+)', "技术一面"),
        (r'二面[^。]*?(?:时长?[：:]\s*(\d+)\s*分钟)?[^。]*?问[了：:]?\s*([^.。!?！？]+)', "技术二面"),
        (r'三面[^。]*?(?:时长?[：:]\s*(\d+)\s*分钟)?[^。]*?问[了：:]?\s*([^.。!?！？]+)', "三面/交叉面"),
        (r'HR面[^。]*?(?:时长?[：:]\s*(\d+)\s*分钟)?', "HR面"),
    ]

    # Also look for duration mentions
    duration_match = re.search(r'(?:时长|时间|大概)[：:]\s*(\d+)\s*分钟', content)
    default_duration = int(duration_match.group(1)) if duration_match else None

    # Look for question-like sentences
    questions = []
    for match in re.finditer(r'问[了：:]\s*([^.。!?！？]{5,80}[?？]?)', content):
        q = match.group(1).strip()
        if len(q) >= 5:
            questions.append(q)

    # Also extract numbered questions
    for match in re.finditer(r'\d+[\.、]\s*([^.。!?！？]{5,80}[?？]?)', content):
        q = match.group(1).strip()
        if len(q) >= 5:
            questions.append(q)

    # Dedupe questions
    questions = list(dict.fromkeys(questions))[:10]

    if questions:
        round_info = {
            "name": "技术面",
            "durationMin": default_duration,
            "durationLabel": f"{default_duration}min" if default_duration else "未标注时长",
            "interviewer": "技术面试官",
            "focus": extract_focus(content),
            "questions": questions[:6],
        }
        rounds.append(round_info)

    return rounds


def extract_focus(content: str) -> list[str]:
    """Extract focus areas from content."""
    focus_areas = []

    keywords = {
        "项目": "项目深挖",
        "RAG": "RAG",
        "agent": "Agent架构",
        "Agent": "Agent架构",
        "MCP": "MCP/工具调用",
        "function calling": "工具调用",
        "测试": "测试设计",
        "自动化": "自动化",
        "pytest": "pytest",
        "Redis": "Redis",
        "MySQL": "MySQL",
        "算法": "算法",
        "系统设计": "系统设计",
        "大模型": "大模型",
        "LLM": "大模型",
    }

    for kw, focus in keywords.items():
        if kw.lower() in content.lower() and focus not in focus_areas:
            focus_areas.append(focus)
        if len(focus_areas) >= 4:
            break

    return focus_areas[:4]


def extract_tags(text: str) -> list[str]:
    """Extract tags from text."""
    tag_keywords = {
        "agent": "agent-architecture",
        "rag": "rag",
        "MCP": "tool-calling",
        "function calling": "tool-calling",
        "记忆": "memory",
        "pytest": "automation",
        "自动化": "automation",
        "redis": "redis",
        "mysql": "mysql",
        "算法": "algorithm",
        "项目": "project-deep-dive",
        "测试": "test-case-design",
        "测开": "test-case-design",
    }

    tags = []
    text_lower = text.lower()
    for kw, tag in tag_keywords.items():
        if kw.lower() in text_lower and tag not in tags:
            tags.append(tag)
        if len(tags) >= 5:
            break

    return tags


def search_nowcoder(query: str, max_pages: int = 2) -> list[str]:
    """Search Nowcoder discussion forum directly and return post URLs."""
    import urllib.parse
    encoded = urllib.parse.quote(query)
    urls = []

    for page in range(1, max_pages + 1):
        search_url = f"https://www.nowcoder.com/search?query={encoded}&page={page}&type=post"
        html = fetch_url(search_url)
        if not html:
            continue

        # Extract discussion links
        for match in re.finditer(r'href="(/discuss/\d+[^"]*)"', html):
            path = match.group(1)
            full_url = f"https://www.nowcoder.com{path}"
            if full_url not in urls:
                urls.append(full_url)

        # Also try feed links
        for match in re.finditer(r'href="(/feed/main/detail/\w+[^"]*)"', html):
            path = match.group(1)
            full_url = f"https://www.nowcoder.com{path}"
            if full_url not in urls:
                urls.append(full_url)

    return urls[:20]


def load_existing_events() -> dict[str, Any]:
    """Load existing interview events."""
    if EVENTS_FILE.exists():
        return json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    return {"updatedAt": utc_date(), "events": []}


def dedupe_events(existing: list[dict], new_events: list[dict]) -> list[dict]:
    """Deduplicate events by sourceUrl."""
    existing_urls = {e.get("sourceUrl", "") for e in existing}
    return [e for e in new_events if e.get("sourceUrl") not in existing_urls]


def fetch_from_xiaohongshu() -> list[dict[str, Any]]:
    """尝试从小红书采集面经，失败时返回空列表。"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from fetch_xiaohongshu import fetch_xhs_interviews
        print("\n  [小红书] 开始采集...")
        events = fetch_xhs_interviews(headless=True)
        print(f"  [小红书] 采集到 {len(events)} 条面经")
        return events
    except FileNotFoundError as e:
        print(f"  [小红书] 跳过 - Cookie 未配置: {e}")
        return []
    except ImportError:
        print("  [小红书] 跳过 - playwright 未安装")
        return []
    except Exception as e:
        print(f"  [小红书] 采集失败: {e}")
        return []


def main() -> int:
    print(f"[{utc_date()}] Starting interview data fetch...")

    # Load existing data
    data = load_existing_events()
    existing_events = data.get("events", [])
    print(f"  Existing events: {len(existing_events)}")

    # Collect new events from search engines
    new_events = []
    seen_urls = set()

    for query in SEARCH_QUERIES:
        print(f"\n  Searching: {query}")
        results = search_bing(query, max_results=8)

        for result in results:
            url = result["url"]
            if url in seen_urls:
                continue
            # Accept nowcoder and other known platforms
            if not any(d in url for d in ["nowcoder.com", "ceshiren.com"]):
                continue

            seen_urls.add(url)
            print(f"    -> {url[:80]}...")

            event = scrape_nowcoder_post(url)
            if event and event.get("rounds"):
                new_events.append(event)
                print(f"       Extracted: {event['title'][:40]}")

    # Also try Nowcoder's own search to discover posts
    nc_queries = [
        "Agent开发 面经",
        "大模型 面试 面经",
        "AI测试 测开 面经",
        "RAG 面经 面试",
    ]
    for nq in nc_queries:
        print(f"\n  Searching Nowcoder: {nq}")
        nc_results = search_nowcoder(nq, max_pages=2)
        for url in nc_results:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            print(f"    -> {url[:80]}...")
            event = scrape_nowcoder_post(url)
            if event and event.get("rounds"):
                new_events.append(event)
                print(f"       Extracted: {event['title'][:40]}")

    # 小红书采集
    xhs_events = fetch_from_xiaohongshu()
    new_events.extend(xhs_events)

    # Dedupe
    unique_new = dedupe_events(existing_events, new_events)
    print(f"\n  New unique events: {len(unique_new)}")

    if unique_new:
        # Merge and save
        all_events = existing_events + unique_new
        data["events"] = all_events
        data["updatedAt"] = utc_date()
        data["scopeNote"] = "Auto-collected from public sources via GitHub Actions daily run."

        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        EVENTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f" Saved {len(all_events)} total events to {EVENTS_FILE}")
    else:
        print("  No new events to add.")

    # Update daily questions if we have new events
    if unique_new:
        update_daily_questions(unique_new)

    return 0


def update_daily_questions(new_events: list[dict]) -> None:
    """Update daily questions from new events."""
    questions_data = {"updatedAt": utc_date(), "dailyCount": 5, "questions": []}

    # Load existing questions
    if QUESTIONS_FILE.exists():
        existing = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
        questions_data["questions"] = existing.get("questions", [])

    # Extract questions from new events
    new_questions = []
    for event in new_events:
        if event.get("recruitingType") == "excluded":
            continue

        for round_info in event.get("rounds", []):
            for i, q in enumerate(round_info.get("questions", [])):
                q_id = sha256_id(q)[:12]
                priority = 1 if "测" in event.get("roleTrack", "") else 2

                question_entry = {
                    "id": f"{event['id']}-q{i}",
                    "priority": priority,
                    "track": event.get("roleTrack", "通用"),
                    "title": q[:50] + ("..." if len(q) > 50 else ""),
                    "question": q,
                    "sourcePlatform": event.get("sourcePlatform", "牛客"),
                    "sourceUrl": event.get("sourceUrl", ""),
                    "sourceHasAnswer": False,
                    "answer": "",
                    "tags": event.get("tags", []),
                }
                new_questions.append(question_entry)

    # Dedupe by question text
    existing_questions = {q.get("question", "") for q in questions_data["questions"]}
    for q in new_questions:
        if q["question"] not in existing_questions:
            questions_data["questions"].append(q)

    # Sort by priority
    questions_data["questions"].sort(key=lambda x: (x.get("priority", 3), x.get("track", "")))

    QUESTIONS_FILE.write_text(json.dumps(questions_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Updated daily questions: {len(questions_data['questions'])} total")


if __name__ == "__main__":
    raise SystemExit(main())