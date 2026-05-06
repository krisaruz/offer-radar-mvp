#!/usr/bin/env python3
"""
小红书登录工具 - 首次使用时运行，通过扫码登录保存 Cookie。
后续采集脚本直接加载 Cookie 文件，无需再次登录。

用法：
    python scripts/xhs_login.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def log(msg: str) -> None:
    print(msg, flush=True)

COOKIE_FILE = Path("data/.xhs_cookies.json")
XHS_HOME = "https://www.xiaohongshu.com"


def save_cookies(context, path: Path) -> None:
    """保存浏览器上下文中的 Cookie 到 JSON 文件。"""
    cookies = context.cookies()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Cookie 已保存到 {path}（共 {len(cookies)} 条）")


def is_truly_logged_in(context) -> bool:
    """通过 cookie 中 userid 字段判断是否真正登录。"""
    cookies = context.cookies()
    cookie_map = {c["name"]: c["value"] for c in cookies}
    if cookie_map.get("galaxy_creator_session_id"):
        return True
    customer_id = cookie_map.get("customerClientId", "")
    if customer_id and len(customer_id) > 10:
        login_token = cookie_map.get("access-token", "") or cookie_map.get("access-token-tt", "")
        if login_token:
            return True
    web_session = cookie_map.get("web_session", "")
    if web_session and len(web_session) > 50:
        return True
    return False


def main() -> int:
    log("=" * 50)
    log("  小红书登录工具")
    log("  请在弹出的浏览器窗口中手动登录")
    log("  脚本会每 5 秒检测一次，登录后自动保存 Cookie")
    log("=" * 50)

    with sync_playwright() as p:
        log("[启动] 正在打开 Chromium 浏览器...")
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

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

        page = context.new_page()
        log("[导航] 正在打开 xiaohongshu.com ...")
        page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)

        log("\n[操作] 浏览器已打开小红书首页。")
        log("       请在浏览器中完成登录（扫码/手机号/密码均可）。")
        log("       脚本将等待最多 3 分钟，检测到登录后自动保存。\n")

        max_wait = 180
        start = time.time()
        logged_in = False

        while time.time() - start < max_wait:
            time.sleep(5)
            if is_truly_logged_in(context):
                logged_in = True
                log("[OK] 检测到有效登录态！")
                break
            elapsed = int(time.time() - start)
            log(f"  [等待中... {elapsed}s] 尚未检测到登录，请在浏览器中操作")

        if not logged_in:
            log("[WARN] 等待超时(3分钟)，未检测到明确登录态，仍将保存当前 Cookie。")
            log("       如果后续采集失败，请重新运行此脚本登录。")

        save_cookies(context, COOKIE_FILE)
        browser.close()

    log("\n[完成] Cookie 已保存。后续运行采集脚本无需再次登录。")
    log(f"       Cookie 文件: {COOKIE_FILE.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
