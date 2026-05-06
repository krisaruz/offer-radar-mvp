#!/usr/bin/env python3
"""
数据质量验证脚本 - 检查采集数据的完整性、相关性和质量。

验证维度：
1. Schema 完整性 - 必填字段是否齐全
2. 内容相关性 - 是否为面经内容
3. 信息密度 - 问题数量是否足够
4. 去重率 - URL 是否有重复
5. 新鲜度 - 日期是否合理
6. 招聘类型标记 - 实习/校招是否正确排除

用法：
    python scripts/validate_quality.py
    python scripts/validate_quality.py --source xhs  # 只验证小红书来源
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")
EVENTS_FILE = DATA_DIR / "interview-events.json"
RAW_XHS_FILE = DATA_DIR / "xhs_raw_notes.json"

REQUIRED_FIELDS = ["id", "title", "company", "sourceUrl", "sourcePlatform", "rounds", "tags"]
INTERVIEW_KEYWORDS = ["面经", "面试", "一面", "二面", "三面", "hr面", "技术面", "面试题", "offer"]
EXCLUDE_MARKERS = ["实习", "暑期", "校招", "秋招", "春招", "26届", "27届", "28届"]


class QualityReport:
    """质量报告收集器。"""

    def __init__(self, source_filter: str | None = None):
        self.source_filter = source_filter
        self.total = 0
        self.schema_pass = 0
        self.schema_issues: list[str] = []
        self.relevance_pass = 0
        self.relevance_issues: list[str] = []
        self.density_pass = 0
        self.density_issues: list[str] = []
        self.duplicates = 0
        self.freshness_pass = 0
        self.freshness_issues: list[str] = []
        self.recruiting_correct = 0
        self.recruiting_issues: list[str] = []
        self.track_distribution: Counter = Counter()
        self.company_distribution: Counter = Counter()
        self.platform_distribution: Counter = Counter()

    def grade(self) -> str:
        """根据通过率给出总评级。"""
        if self.total == 0:
            return "N/A (无数据)"
        scores = []
        if self.total > 0:
            scores.append(self.schema_pass / self.total)
            scores.append(self.relevance_pass / self.total)
            scores.append(self.density_pass / self.total)
        avg = sum(scores) / len(scores) if scores else 0
        if avg >= 0.9:
            return "A (优秀)"
        elif avg >= 0.75:
            return "B (合格)"
        elif avg >= 0.6:
            return "C (需优化)"
        else:
            return "D (质量差，建议检查采集逻辑)"

    def print_report(self) -> None:
        """输出质量报告。"""
        source_label = f"（来源: {self.source_filter}）" if self.source_filter else ""
        print(f"\n{'=' * 55}")
        print(f"  采集数据质量报告{source_label}")
        print(f"{'=' * 55}")

        print(f"\n  采集总量: {self.total} 条")
        print(f"  重复数据: {self.duplicates} 条")
        print()

        self._print_metric("Schema 完整性", self.schema_pass, self.total)
        self._print_metric("面经相关性", self.relevance_pass, self.total)
        self._print_metric("信息密度", self.density_pass, self.total)
        self._print_metric("日期新鲜度", self.freshness_pass, self.total)
        self._print_metric("招聘类型标记", self.recruiting_correct, self.total)

        print(f"\n  质量评级: {self.grade()}")

        # 分布统计
        if self.track_distribution:
            print(f"\n  岗位方向分布:")
            for track, count in self.track_distribution.most_common(8):
                print(f"    {track}: {count}")

        if self.company_distribution:
            print(f"\n  公司分布:")
            for company, count in self.company_distribution.most_common(8):
                print(f"    {company}: {count}")

        if self.platform_distribution:
            print(f"\n  来源平台分布:")
            for platform, count in self.platform_distribution.most_common():
                print(f"    {platform}: {count}")

        # 问题汇总
        all_issues = (
            self.schema_issues[:3]
            + self.relevance_issues[:3]
            + self.density_issues[:3]
            + self.recruiting_issues[:3]
        )
        if all_issues:
            print(f"\n  主要问题（前 {min(len(all_issues), 10)} 条）:")
            for issue in all_issues[:10]:
                print(f"    - {issue}")

        print(f"\n{'=' * 55}\n")

    def _print_metric(self, name: str, passed: int, total: int) -> None:
        if total == 0:
            print(f"  {name}: N/A")
            return
        pct = passed / total * 100
        status = "PASS" if pct >= 80 else "WARN" if pct >= 60 else "FAIL"
        print(f"  {name}: {passed}/{total} ({pct:.0f}%) [{status}]")


def validate_schema(event: dict) -> tuple[bool, str]:
    """验证 Schema 完整性。"""
    missing = [f for f in REQUIRED_FIELDS if f not in event or not event[f]]
    if missing:
        return False, f"缺失字段: {', '.join(missing)}"

    # rounds 结构检查
    rounds = event.get("rounds", [])
    if not isinstance(rounds, list):
        return False, "rounds 不是列表"

    for i, r in enumerate(rounds):
        if not isinstance(r, dict):
            return False, f"rounds[{i}] 不是字典"
        if "name" not in r:
            return False, f"rounds[{i}] 缺少 name"

    return True, ""


def validate_relevance(event: dict) -> tuple[bool, str]:
    """验证内容是否面经相关。"""
    text = f"{event.get('title', '')} {json.dumps(event.get('rounds', []), ensure_ascii=False)}".lower()
    if any(kw in text for kw in INTERVIEW_KEYWORDS):
        return True, ""
    return False, f"标题 '{event.get('title', '')[:30]}' 无面经关键词"


def validate_density(event: dict) -> tuple[bool, str]:
    """验证信息密度（问题数量）。"""
    rounds = event.get("rounds", [])
    if not rounds:
        return False, "无面试轮次"

    total_questions = sum(len(r.get("questions", [])) for r in rounds)
    if total_questions < 2:
        return False, f"问题数不足（仅 {total_questions} 条）"

    return True, ""


def validate_freshness(event: dict) -> tuple[bool, str]:
    """验证日期是否在合理范围内。"""
    date_str = event.get("sourceDate", "")
    if not date_str or "未" in date_str or "约" in date_str:
        return True, ""  # 无法判断，放行

    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        days_old = (datetime.now() - date).days
        if days_old > 365 * 3:
            return False, f"日期过旧: {date_str}（{days_old} 天前）"
        return True, ""
    except ValueError:
        return True, ""  # 格式不标准，放行


def validate_recruiting_type(event: dict) -> tuple[bool, str]:
    """验证招聘类型标记是否准确。"""
    text = f"{event.get('title', '')} {event.get('seniority', '')}".lower()
    declared_type = event.get("recruitingType", "unspecified")

    has_exclude_marker = any(m in text for m in EXCLUDE_MARKERS)

    if has_exclude_marker and declared_type != "excluded":
        return False, f"应标记为 excluded: '{event.get('title', '')[:30]}'"
    if not has_exclude_marker and declared_type == "excluded":
        # 检查 hiddenReason
        if not event.get("hiddenReason"):
            return False, f"标记为 excluded 但无排除标记: '{event.get('title', '')[:30]}'"

    return True, ""


def validate_events(events: list[dict], source_filter: str | None = None) -> QualityReport:
    """验证事件列表并生成报告。"""
    report = QualityReport(source_filter)

    # 过滤来源
    if source_filter:
        events = [e for e in events if e.get("sourcePlatform", "").lower() == source_filter.lower()
                  or source_filter.lower() in e.get("id", "").lower()]

    report.total = len(events)

    # 去重检查
    urls = [e.get("sourceUrl", "") for e in events]
    url_counts = Counter(urls)
    report.duplicates = sum(1 for c in url_counts.values() if c > 1)

    for event in events:
        # Schema
        passed, issue = validate_schema(event)
        if passed:
            report.schema_pass += 1
        else:
            report.schema_issues.append(f"[{event.get('id', '?')}] {issue}")

        # 相关性
        passed, issue = validate_relevance(event)
        if passed:
            report.relevance_pass += 1
        else:
            report.relevance_issues.append(issue)

        # 密度
        passed, issue = validate_density(event)
        if passed:
            report.density_pass += 1
        else:
            report.density_issues.append(f"[{event.get('id', '?')}] {issue}")

        # 新鲜度
        passed, issue = validate_freshness(event)
        if passed:
            report.freshness_pass += 1
        else:
            report.freshness_issues.append(issue)

        # 招聘类型
        passed, issue = validate_recruiting_type(event)
        if passed:
            report.recruiting_correct += 1
        else:
            report.recruiting_issues.append(issue)

        # 统计分布
        report.track_distribution[event.get("roleTrack", "未知")] += 1
        report.company_distribution[event.get("company", "未知")] += 1
        report.platform_distribution[event.get("sourcePlatform", "未知")] += 1

    return report


def validate_raw_notes(notes: list[dict]) -> None:
    """验证小红书原始笔记数据。"""
    print(f"\n{'=' * 55}")
    print(f"  小红书原始笔记质量检查")
    print(f"{'=' * 55}")
    print(f"\n  笔记总数: {len(notes)}")

    # 面经相关性
    interview_related = 0
    for note in notes:
        text = f"{note.get('title', '')} {note.get('desc', '')}".lower()
        if any(kw in text for kw in INTERVIEW_KEYWORDS):
            interview_related += 1

    pct = interview_related / len(notes) * 100 if notes else 0
    print(f"  面经相关: {interview_related}/{len(notes)} ({pct:.0f}%)")

    # 有内容的笔记
    has_content = sum(1 for n in notes if len(n.get("desc", "")) > 50)
    pct = has_content / len(notes) * 100 if notes else 0
    print(f"  有实质内容(>50字): {has_content}/{len(notes)} ({pct:.0f}%)")

    # 标题长度
    titles = [n.get("title", "") for n in notes]
    avg_title_len = sum(len(t) for t in titles) / len(titles) if titles else 0
    print(f"  平均标题长度: {avg_title_len:.1f} 字")

    # 互动数据
    likes = []
    for n in notes:
        try:
            likes.append(int(n.get("liked_count", "0").replace("万", "0000")))
        except (ValueError, AttributeError):
            pass
    if likes:
        print(f"  点赞数: 平均 {sum(likes)/len(likes):.0f}, 最高 {max(likes)}")

    print(f"\n{'=' * 55}\n")


def main() -> int:
    source_filter = None
    if "--source" in sys.argv:
        idx = sys.argv.index("--source")
        if idx + 1 < len(sys.argv):
            source_filter = sys.argv[idx + 1]

    # 验证结构化事件数据
    if EVENTS_FILE.exists():
        data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        events = data.get("events", [])
        report = validate_events(events, source_filter)
        report.print_report()
    else:
        print(f"[!] 事件文件不存在: {EVENTS_FILE}")
        print("    请先运行采集脚本。")

    # 如果有原始小红书数据，也验证一下
    if RAW_XHS_FILE.exists():
        notes = json.loads(RAW_XHS_FILE.read_text(encoding="utf-8"))
        if notes:
            validate_raw_notes(notes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
