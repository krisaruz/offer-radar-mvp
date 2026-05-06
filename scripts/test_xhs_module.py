#!/usr/bin/env python3
"""测试小红书采集模块的核心逻辑（不需要浏览器/登录）。"""

import sys
import json
sys.path.insert(0, "scripts")

from fetch_xiaohongshu import (
    is_interview_related,
    detect_company,
    detect_role_track,
    detect_recruiting_type,
    extract_questions,
    extract_rounds,
    extract_tags,
    note_to_event,
)


def test_basic_functions():
    print("=" * 50)
    print("  小红书采集模块 - 单元测试")
    print("=" * 50)
    passed = 0
    failed = 0

    # 测试面经识别
    print("\n[1] 面经相关性检测")
    cases = [
        ({"title": "小红书Agent开发面试一面面经", "desc": "问了RAG"}, True),
        ({"title": "今天去吃了火锅", "desc": "好好吃"}, False),
        ({"title": "面试题整理", "desc": "算法题"}, True),
        ({"title": "秋招offer比较", "desc": "拿到了字节的offer"}, True),
    ]
    for note, expected in cases:
        result = is_interview_related(note)
        ok = result == expected
        passed += ok
        failed += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] '{note['title'][:20]}' -> {result}")

    # 测试公司识别
    print("\n[2] 公司识别")
    company_cases = [
        ("小红书Agent开发面试", "小红书"),
        ("字节跳动后端开发面经", "字节跳动"),
        ("阿里巴巴测开面试", "阿里巴巴"),
        ("某公司面经分享", "未知公司"),
    ]
    for text, expected in company_cases:
        result = detect_company(text)
        ok = result == expected
        passed += ok
        failed += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] '{text[:20]}' -> {result}")

    # 测试方向识别
    print("\n[3] 岗位方向识别")
    track_cases = [
        ("Agent开发工程师面试", "Agent开发"),
        ("AI测试开发面经", "AI测开"),
        ("测开社招面经", "测开"),
        ("大模型应用开发", "大模型/AI应用"),
        ("前端面试经验", "前端开发"),
    ]
    for text, expected in track_cases:
        result = detect_role_track(text)
        ok = result == expected
        passed += ok
        failed += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] '{text[:20]}' -> {result}")

    # 测试招聘类型检测
    print("\n[4] 招聘类型检测")
    recruit_cases = [
        ("暑期实习面经", "excluded"),
        ("秋招面试题", "excluded"),
        ("社招跳槽面经", "social"),
        ("面试经验分享", "unspecified"),
    ]
    for text, expected in recruit_cases:
        result = detect_recruiting_type(text)
        ok = result == expected
        passed += ok
        failed += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] '{text[:20]}' -> {result}")

    # 测试问题提取
    print("\n[5] 问题提取")
    test_desc = """面试官问了：
1. Agent的记忆怎么分层设计
2. RAG召回不到怎么办
3. MCP和Function Calling的区别是什么？
4. 你的项目怎么做评测
- 系统设计：设计一个问答系统
问了：多Agent协作怎么做状态同步"""
    questions = extract_questions(test_desc)
    print(f"  提取到 {len(questions)} 个问题:")
    for q in questions:
        print(f"    - {q}")
    ok = len(questions) >= 4
    passed += ok
    failed += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] 问题数 >= 4")

    # 测试轮次提取
    print("\n[6] 轮次提取")
    test_text = "一面 45分钟 问了项目和算法 二面 60分钟 系统设计 HR面谈薪资"
    rounds = extract_rounds(test_text)
    print(f"  提取到 {len(rounds)} 轮面试")
    for r in rounds:
        print(f"    {r['name']} ({r['durationLabel']})")
    ok = len(rounds) >= 2
    passed += ok
    failed += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] 轮次 >= 2")

    # 测试完整转换
    print("\n[7] 完整 note -> event 转换")
    test_note = {
        "note_id": "abc123def456",
        "title": "小红书Agent开发一面面经分享",
        "desc": "面试官问了：\n1. Agent的记忆怎么设计\n2. RAG召回不到怎么办\n3. MCP和Function Calling的区别\n4. 你的项目怎么做评测\n面试大约45分钟",
        "content": "小红书Agent开发一面面经分享",
        "author": "测试用户",
        "liked_count": "128",
        "collected_count": "56",
        "comment_count": "23",
        "tags_raw": ["面经", "Agent"],
        "publish_time": "2026-05-01",
        "url": "https://www.xiaohongshu.com/explore/abc123def456",
    }
    event = note_to_event(test_note)
    ok = event is not None
    passed += ok
    failed += not ok
    if event:
        print(f"  company={event['company']}, track={event['roleTrack']}")
        print(f"  rounds={len(event['rounds'])}, tags={event['tags']}")
        ok2 = event["company"] == "小红书" and event["roleTrack"] == "Agent开发"
        passed += ok2
        failed += not ok2
        print(f"  [{'PASS' if ok2 else 'FAIL'}] 字段值正确")
    else:
        print(f"  [FAIL] 转换返回 None")
        failed += 1

    # 测试标签提取
    print("\n[8] 标签提取")
    tags = extract_tags("Agent RAG pytest 大模型 自动化测试")
    ok = "agent-architecture" in tags and "rag" in tags
    passed += ok
    failed += not ok
    print(f"  标签: {tags}")
    print(f"  [{'PASS' if ok else 'FAIL'}] 包含预期标签")

    print(f"\n{'=' * 50}")
    print(f"  结果: {passed} 通过, {failed} 失败")
    print(f"{'=' * 50}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(test_basic_functions())
