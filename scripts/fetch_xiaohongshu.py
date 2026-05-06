#!/usr/bin/env python3
"""
小红书面经采集模块 - 通过 Playwright 浏览器自动化搜索并提取面经帖子。

核心流程：
1. 加载 Cookie -> 2. 按关键词搜索 -> 3. 提取笔记列表 ->
4. 逐条获取详情 -> 5. 结构化为 interview-event 格式

用法：
    python scripts/fetch_xiaohongshu.py
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

COOKIE_FILE = Path("data/.xhs_cookies.json")
DATA_DIR = Path("data")
EVENTS_FILE = DATA_DIR / "interview-events.json"
RAW_OUTPUT = DATA_DIR / "xhs_raw_notes.json"

XHS_SEARCH_QUERIES = [
    "面经 Agent开发",
    "面试 AI测试 测开",
    "面经 测试开发 社招",
    "Agent开发 面试题 社招",
    "大模型 面试 面经",
    "RAG 面试 面经",
    "AI测开 面试题",
    "面经 一面 二面 技术面",
]

MAX_NOTES_PER_QUERY = 15
MAX_TOTAL_NOTES = 50
REQUEST_DELAY_RANGE = (3, 7)
SEARCH_GAP_RANGE = (8, 15)

XHS_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_note"
XHS_NOTE_URL = "https://www.xiaohongshu.com/explore/{note_id}"


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sha256_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def random_delay(low: float, high: float) -> None:
    """随机延迟，模拟人类操作节奏。"""
    delay = random.uniform(low, high)
    time.sleep(delay)


def load_cookies() -> list[dict]:
    """加载已保存的 Cookie。"""
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(
            f"Cookie 文件不存在: {COOKIE_FILE}\n"
            "请先运行 python scripts/xhs_login.py 登录。"
        )
    return json.loads(COOKIE_FILE.read_text(encoding="utf-8"))


def extract_note_ids_from_search(page) -> list[str]:
    """从搜索结果页面提取笔记 ID 列表。"""
    note_ids = []

    # 方法1：从 __INITIAL_STATE__ 提取
    try:
        state = page.evaluate("JSON.stringify(window.__INITIAL_STATE__)")
        if state:
            state_data = json.loads(state)
            # 搜索结果在 note 字段下
            notes_map = state_data.get("search", {}).get("notes", {})
            if not notes_map:
                notes_map = state_data.get("search", {}).get("feedsMap", {})
            for key in notes_map:
                if isinstance(notes_map[key], dict):
                    note_id = notes_map[key].get("id") or notes_map[key].get("noteId") or key
                    if note_id and note_id not in note_ids:
                        note_ids.append(note_id)
    except Exception:
        pass

    # 方法2：从页面链接提取
    if not note_ids:
        try:
            links = page.eval_on_selector_all(
                'a[href*="/explore/"], a[href*="/search_result/"]',
                "els => els.map(e => e.href)"
            )
            for link in links:
                match = re.search(r'/explore/([a-f0-9]{24})', link)
                if match and match.group(1) not in note_ids:
                    note_ids.append(match.group(1))
        except Exception:
            pass

    # 方法3：从 section 元素的 data 属性提取
    if not note_ids:
        try:
            ids = page.eval_on_selector_all(
                'section.note-item[data-note-id], [id^="note_"]',
                "els => els.map(e => e.dataset.noteId || e.id.replace('note_',''))"
            )
            note_ids.extend([i for i in ids if i and i not in note_ids])
        except Exception:
            pass

    return note_ids[:MAX_NOTES_PER_QUERY]


def extract_note_detail(page, note_id: str) -> dict[str, Any] | None:
    """从笔记详情页提取结构化数据。"""
    try:
        state_raw = page.evaluate("JSON.stringify(window.__INITIAL_STATE__)")
        if not state_raw:
            return None
        state = json.loads(state_raw)
    except Exception:
        return None

    # 尝试多种路径找到笔记数据
    note_data = None
    for path_fn in [
        lambda s: s.get("note", {}).get("noteDetailMap", {}).get(note_id, {}).get("note"),
        lambda s: s.get("note", {}).get("note"),
        lambda s: s.get("noteData", {}).get("data", {}).get("noteData"),
    ]:
        try:
            candidate = path_fn(state)
            if candidate and isinstance(candidate, dict):
                note_data = candidate
                break
        except (KeyError, TypeError, AttributeError):
            continue

    if not note_data:
        return None

    title = note_data.get("title", "").strip()
    desc = note_data.get("desc", "").strip()
    content = f"{title} {desc}"

    # 互动数据
    interact_info = note_data.get("interactInfo", {})
    liked_count = interact_info.get("likedCount", "0")
    collected_count = interact_info.get("collectedCount", "0")
    comment_count = interact_info.get("commentCount", "0")

    # 标签
    tag_list = note_data.get("tagList", [])
    tags_raw = [t.get("name", "") for t in tag_list if isinstance(t, dict)]

    # 发布时间
    publish_time = note_data.get("time", "")
    if not publish_time:
        publish_time = note_data.get("lastUpdateTime", "")

    # 用户信息
    user_info = note_data.get("user", {})
    author = user_info.get("nickname", "")

    return {
        "note_id": note_id,
        "title": title,
        "desc": desc,
        "content": content,
        "author": author,
        "liked_count": str(liked_count),
        "collected_count": str(collected_count),
        "comment_count": str(comment_count),
        "tags_raw": tags_raw,
        "publish_time": publish_time,
        "url": f"https://www.xiaohongshu.com/explore/{note_id}",
    }


def is_interview_related(note: dict) -> bool:
    """判断笔记是否为面经相关内容。"""
    text = f"{note.get('title', '')} {note.get('desc', '')}".lower()
    interview_keywords = [
        "面经", "面试", "一面", "二面", "三面", "hr面",
        "笔试", "面试题", "offer", "秋招", "春招", "社招",
        "面试官", "技术面", "拿到offer",
    ]
    return any(kw in text for kw in interview_keywords)


def detect_company(text: str) -> str:
    """从文本中识别公司名称。"""
    company_map = {
        "小红书": "小红书",
        "字节": "字节跳动",
        "抖音": "字节跳动",
        "阿里": "阿里巴巴",
        "腾讯": "腾讯",
        "百度": "百度",
        "美团": "美团",
        "京东": "京东",
        "快手": "快手",
        "滴滴": "滴滴",
        "网易": "网易",
        "华为": "华为",
        "蚂蚁": "蚂蚁集团",
        "shopee": "Shopee",
        "微软": "微软",
        "google": "Google",
    }
    text_lower = text.lower()
    for keyword, company in company_map.items():
        if keyword.lower() in text_lower:
            return company
    return "未知公司"


def detect_role_track(text: str) -> str:
    """从文本中识别岗位方向。"""
    text_lower = text.lower()
    if "agent" in text_lower:
        return "Agent开发"
    if "ai测" in text_lower or "大模型测试" in text_lower or "模型测试" in text_lower:
        return "AI测开"
    if "测开" in text_lower or "测试开发" in text_lower:
        return "测开"
    if "ai产品" in text_lower or "ai pm" in text_lower:
        return "AI产品经理"
    if "大模型" in text_lower or "llm" in text_lower:
        return "大模型/AI应用"
    if "后端" in text_lower or "java" in text_lower or "golang" in text_lower:
        return "后端开发"
    if "前端" in text_lower:
        return "前端开发"
    return "通用"


def detect_recruiting_type(text: str) -> str:
    """检测招聘类型，用于排除实习/校招。"""
    if re.search(r"(实习|暑期|校招|秋招|春招|26届|27届|28届)", text):
        return "excluded"
    if re.search(r"(社招|跳槽|在职)", text):
        return "social"
    return "unspecified"


def extract_questions(text: str) -> list[str]:
    """从面经文本中提取面试问题。"""
    questions = []

    # 预处理：将 "1. xxx 2. yyy" 这种单行格式拆成多行
    normalized = re.sub(r'(\s)(\d+)[\.、）)]\s*', r'\n\2. ', text)

    # 模式1：问了xxx / 问：xxx
    for match in re.finditer(r'问[了：:]\s*([^.。!?！？\n]{5,100}[?？]?)', normalized):
        q = match.group(1).strip()
        if len(q) >= 5:
            questions.append(q)

    # 模式2：数字编号列表（如 "1. xxx" 或 "1、xxx"）
    for match in re.finditer(r'(?:^|\n)\s*[\d①②③④⑤⑥⑦⑧⑨⑩]+[\.、）)\s]+(.+)', normalized):
        q = match.group(1).strip()
        q = re.sub(r'\s*\d+[\.、）)]\s*$', '', q).strip()
        if len(q) >= 5 and q not in questions:
            questions.append(q)

    # 模式3：- 或 · 开头的列表项
    for match in re.finditer(r'[-·•]\s*([^.。\n]{5,100}[?？]?)', text):
        q = match.group(1).strip()
        if len(q) >= 5 and q not in questions:
            questions.append(q)

    # 模式4：含问号的句子
    for match in re.finditer(r'([^.。!！\n]{8,100}[?？])', text):
        q = match.group(1).strip()
        if q not in questions and not q.startswith("http"):
            questions.append(q)

    return list(dict.fromkeys(questions))[:12]


def extract_rounds(text: str) -> list[dict[str, Any]]:
    """提取面试轮次信息。"""
    rounds = []
    questions = extract_questions(text)

    # 检测是否有明确的轮次标记
    round_markers = re.findall(r'(一面|二面|三面|四面|HR面|技术面|交叉面)', text)

    if round_markers:
        for i, marker in enumerate(dict.fromkeys(round_markers)):
            round_name = {
                "一面": "技术一面",
                "二面": "技术二面",
                "三面": "三面/交叉面",
                "四面": "四面",
                "HR面": "HR面",
                "技术面": "技术面",
                "交叉面": "交叉面",
            }.get(marker, marker)

            # 尝试提取该轮时长
            duration = None
            dur_match = re.search(rf'{marker}[^。]*?(\d+)\s*(?:分钟|min)', text)
            if dur_match:
                duration = int(dur_match.group(1))

            round_questions = questions[i * 4:(i + 1) * 4] if questions else []

            rounds.append({
                "name": round_name,
                "durationMin": duration,
                "durationLabel": f"{duration}min" if duration else "未标注时长",
                "interviewer": "面试官",
                "focus": extract_focus(text),
                "questions": round_questions,
            })
    elif questions:
        # 无明确轮次标记，统一归为"技术面"
        duration_match = re.search(r'(\d+)\s*(?:分钟|min)', text)
        duration = int(duration_match.group(1)) if duration_match else None

        rounds.append({
            "name": "技术面",
            "durationMin": duration,
            "durationLabel": f"{duration}min" if duration else "未标注时长",
            "interviewer": "面试官",
            "focus": extract_focus(text),
            "questions": questions[:8],
        })

    return rounds


def extract_focus(text: str) -> list[str]:
    """提取面试考察重点。"""
    focus_map = {
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
        "评测": "评测体系",
        "prompt": "Prompt工程",
    }
    focus_areas = []
    for kw, focus in focus_map.items():
        if kw.lower() in text.lower() and focus not in focus_areas:
            focus_areas.append(focus)
        if len(focus_areas) >= 5:
            break
    return focus_areas


def extract_tags(text: str) -> list[str]:
    """提取标签。"""
    tag_map = {
        "agent": "agent-architecture",
        "rag": "rag",
        "mcp": "tool-calling",
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
        "评测": "evaluation",
        "prompt": "prompt-engineering",
        "大模型": "llm",
    }
    tags = []
    text_lower = text.lower()
    for kw, tag in tag_map.items():
        if kw.lower() in text_lower and tag not in tags:
            tags.append(tag)
        if len(tags) >= 6:
            break
    return tags


def note_to_event(note: dict) -> dict[str, Any] | None:
    """将原始笔记数据转换为 interview-event 格式。"""
    content = note.get("content", "")
    desc = note.get("desc", "")
    full_text = f"{content} {desc}"

    if not is_interview_related(note):
        return None

    rounds = extract_rounds(full_text)
    if not rounds:
        return None

    note_id = note.get("note_id", "")
    title = note.get("title", "").strip()
    if not title:
        title = desc[:50] if desc else "无标题面经"

    return {
        "id": f"xhs-{sha256_id(note_id + title)}",
        "title": title[:100],
        "company": detect_company(full_text),
        "roleTrack": detect_role_track(full_text),
        "seniority": "未说明招聘类型",
        "sourcePlatform": "小红书",
        "sourceUrl": note.get("url", f"https://www.xiaohongshu.com/explore/{note_id}"),
        "sourceDate": utc_date(),
        "evidenceLevel": "medium",
        "rounds": rounds,
        "takeaways": [],
        "tags": extract_tags(full_text),
        "recruitingType": detect_recruiting_type(full_text),
    }


def fetch_xhs_interviews(headless: bool = True) -> list[dict[str, Any]]:
    """
    主采集函数：搜索小红书面经并返回 interview-event 列表。

    Args:
        headless: 是否使用无头模式。本地调试设为 False 可看到浏览器。

    Returns:
        结构化的面经事件列表。
    """
    from playwright.sync_api import sync_playwright

    cookies = load_cookies()
    all_notes: list[dict] = []
    all_events: list[dict] = []
    seen_ids: set[str] = set()

    print(f"[{utc_date()}] 小红书面经采集开始...")
    print(f"  关键词数: {len(XHS_SEARCH_QUERIES)}")
    print(f"  每词上限: {MAX_NOTES_PER_QUERY} 条")
    print(f"  总上限: {MAX_TOTAL_NOTES} 条")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # 注入反检测脚本
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

        # 加载 Cookie
        context.add_cookies(cookies)
        page = context.new_page()

        for qi, query in enumerate(XHS_SEARCH_QUERIES):
            if len(all_notes) >= MAX_TOTAL_NOTES:
                print(f"\n  [达到上限] 已采集 {len(all_notes)} 条，停止搜索。")
                break

            print(f"\n  [{qi+1}/{len(XHS_SEARCH_QUERIES)}] 搜索: {query}")
            search_url = XHS_SEARCH_URL.format(keyword=quote(query))

            try:
                page.goto(search_url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                print(f"    [WARN] 页面加载失败: {e}")
                random_delay(*SEARCH_GAP_RANGE)
                continue

            random_delay(2, 4)

            # 滚动加载更多
            for _ in range(3):
                page.mouse.wheel(0, 800)
                random_delay(1, 2)

            # 提取笔记 ID
            note_ids = extract_note_ids_from_search(page)
            print(f"    发现 {len(note_ids)} 条笔记")

            # 逐条获取详情
            for note_id in note_ids:
                if note_id in seen_ids:
                    continue
                if len(all_notes) >= MAX_TOTAL_NOTES:
                    break

                seen_ids.add(note_id)
                note_url = XHS_NOTE_URL.format(note_id=note_id)

                try:
                    page.goto(note_url, wait_until="networkidle", timeout=20000)
                except Exception as e:
                    print(f"    [WARN] 笔记 {note_id[:8]}... 加载失败: {e}")
                    random_delay(*REQUEST_DELAY_RANGE)
                    continue

                random_delay(1, 2)

                # 检测是否遇到验证码
                if "captcha" in page.url or page.locator('[class*="captcha"]').count() > 0:
                    print("    [!] 检测到验证码，暂停 30 秒等待...")
                    time.sleep(30)
                    continue

                note_data = extract_note_detail(page, note_id)
                if note_data:
                    all_notes.append(note_data)
                    # 尝试转换为事件
                    event = note_to_event(note_data)
                    if event:
                        all_events.append(event)
                        print(f"    [+] {note_data['title'][:40]}... -> {event['roleTrack']}")
                    else:
                        print(f"    [-] {note_data['title'][:40]}... (非面经/无问题)")

                random_delay(*REQUEST_DELAY_RANGE)

            # 搜索间隔
            random_delay(*SEARCH_GAP_RANGE)

        browser.close()

    # 保存原始数据
    RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    RAW_OUTPUT.write_text(
        json.dumps(all_notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  原始笔记已保存: {RAW_OUTPUT} ({len(all_notes)} 条)")
    print(f"  转换为面经事件: {len(all_events)} 条")

    return all_events


def main() -> int:
    """独立运行时的入口。"""
    import sys

    headless = "--headless" in sys.argv or "-H" in sys.argv
    events = fetch_xhs_interviews(headless=headless)

    if events:
        # 合并到已有数据
        if EVENTS_FILE.exists():
            data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        else:
            data = {"updatedAt": utc_date(), "events": []}

        existing_urls = {e.get("sourceUrl", "") for e in data.get("events", [])}
        new_events = [e for e in events if e.get("sourceUrl") not in existing_urls]

        if new_events:
            data["events"].extend(new_events)
            data["updatedAt"] = utc_date()
            EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            EVENTS_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"\n[OK] 新增 {len(new_events)} 条面经到 {EVENTS_FILE}")
        else:
            print("\n[OK] 无新增面经（全部已存在）。")
    else:
        print("\n[!] 本次采集未获取到有效面经。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
