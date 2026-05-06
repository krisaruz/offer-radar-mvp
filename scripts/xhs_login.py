#!/usr/bin/env python3
"""
小红书登录工具 - 首次使用时运行，通过扫码登录保存 Cookie。
后续采集脚本直接加载 Cookie 文件，无需再次登录。

用法：
    python scripts/xhs_login.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

COOKIE_FILE = Path("data/.xhs_cookies.json")
XHS_HOME = "https://www.xiaohongshu.com"


def save_cookies(context, path: Path) -> None:
    """保存浏览器上下文中的 Cookie 到 JSON 文件。"""
    cookies = context.cookies()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Cookie 已保存到 {path}（共 {len(cookies)} 条）")


def is_logged_in(page) -> bool:
    """检测当前页面是否已登录（通过检查头像/用户中心入口）。"""
    try:
        avatar = page.locator('[class*="user-avatar"], [class*="avatar"], [data-v-][class*="reds-avatar"]')
        return avatar.count() > 0
    except Exception:
        return False


def main() -> int:
    print("=" * 50)
    print("  小红书登录工具")
    print("  请在弹出的浏览器窗口中扫码登录")
    print("=" * 50)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
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
        page = context.new_page()

        page.goto(XHS_HOME)
        print("\n[等待] 请在浏览器中完成扫码登录...")
        print("       登录成功后脚本会自动检测并保存 Cookie。")
        print("       如果自动检测失败，登录后按 Enter 键手动确认。\n")

        max_wait = 180  # 最多等 3 分钟
        start = time.time()
        logged_in = False

        while time.time() - start < max_wait:
            time.sleep(3)
            page.reload()
            time.sleep(2)

            if is_logged_in(page):
                logged_in = True
                break

            # 检查 cookie 中是否包含登录标识
            cookies = context.cookies()
            cookie_names = {c["name"] for c in cookies}
            if "web_session" in cookie_names or "galaxy_creator_session_id" in cookie_names:
                logged_in = True
                break

        if not logged_in:
            print("[提示] 未自动检测到登录状态，请确认是否已登录。")
            input("       如果已登录，按 Enter 继续保存 Cookie...")

        save_cookies(context, COOKIE_FILE)
        browser.close()

    print("\n[完成] 登录流程结束。后续运行采集脚本无需再次登录。")
    print(f"       Cookie 文件: {COOKIE_FILE.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
