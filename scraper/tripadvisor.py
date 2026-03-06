"""TripAdvisor review scraper using patchright (stealth browser)."""
import os
import re
import shutil
import time
import uuid

from patchright.sync_api import sync_playwright

PROFILE_BASE = "/tmp/ta-profiles"


def scrape_tripadvisor_reviews(url: str, progress_callback=None) -> list[dict]:
    """Scrape all reviews from a TripAdvisor URL with pagination.

    Uses patchright with cookie warm-up and up to 5 retries.
    Timeout: 30 minutes total.
    """
    if "tripadvisor" not in url.lower():
        raise ValueError("TripAdvisorのURLを入力してください")

    base_url = _prepare_base_url(url)
    start_time = time.time()
    max_time = 1800  # 30 minutes

    last_error = ""
    for attempt in range(5):
        if time.time() - start_time > max_time:
            break

        if progress_callback:
            progress_callback(0, f"セッション開始中... (試行 {attempt + 1}/5)")

        profile_dir = os.path.join(PROFILE_BASE, uuid.uuid4().hex[:8])
        os.makedirs(profile_dir, exist_ok=True)

        pw = None
        ctx = None
        try:
            pw = sync_playwright().start()
            ctx = pw.chromium.launch_persistent_context(
                profile_dir,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
                locale="ja-JP",
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            # Block heavy resources
            page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
                lambda route: route.abort(),
            )

            # Cookie warm-up: visit TripAdvisor homepage first
            if progress_callback:
                progress_callback(0, "Cookie取得中 (トップページ)...")
            page.goto("https://www.tripadvisor.jp/", wait_until="networkidle", timeout=30000)
            time.sleep(3)

            cookies = ctx.cookies()
            cookie_names = [c["name"] for c in cookies]
            if progress_callback:
                progress_callback(0, f"Cookie: {len(cookies)}個 ({', '.join(cookie_names[:5])})")

            # Check for DataDome captcha on homepage
            html = page.content()
            if "captcha-delivery" in html:
                if progress_callback:
                    progress_callback(0, f"トップページでCAPTCHA検出、リトライ... ({attempt + 1}/5)")
                last_error = "DataDome CAPTCHA on homepage"
                _cleanup(ctx, pw, profile_dir)
                time.sleep(5)
                continue

            # Navigate to first page
            if progress_callback:
                progress_callback(0, "レストランページ読み込み中...")
            page_url = base_url.format("")
            page.goto(page_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)

            html = page.content()
            if "captcha-delivery" in html:
                if progress_callback:
                    progress_callback(0, f"CAPTCHA検出、プロファイル再作成してリトライ... ({attempt + 1}/5)")
                last_error = "DataDome CAPTCHA on restaurant page"
                _cleanup(ctx, pw, profile_dir)
                time.sleep(5)
                continue

            # Check for review cards
            cards = page.query_selector_all('[data-automation="reviewCard"]')
            if not cards:
                for alt_sel in ['[data-test-target="HR_CC_CARD"]', '.review-container', '[data-reviewid]']:
                    cards = page.query_selector_all(alt_sel)
                    if cards:
                        break

            if not cards:
                if progress_callback:
                    progress_callback(0, f"レビューカード未検出、リトライ... ({attempt + 1}/5)")
                last_error = "No review cards found on page"
                _cleanup(ctx, pw, profile_dir)
                time.sleep(3)
                continue

            # Success! Collect reviews from all pages
            if progress_callback:
                progress_callback(0, f"レビュー検出OK ({len(cards)}件)、収集開始...")

            all_reviews = _collect_all_pages(page, ctx, base_url, progress_callback, start_time, max_time)

            _cleanup(ctx, pw, profile_dir)
            return all_reviews

        except Exception as e:
            last_error = str(e)
            if progress_callback:
                progress_callback(0, f"エラー: {e}、リトライ... ({attempt + 1}/5)")
            _cleanup(ctx, pw, profile_dir)
            time.sleep(3)
            continue

    raise RuntimeError(f"TripAdvisor レビュー取得失敗 (5回リトライ済み): {last_error}")


def _cleanup(ctx, pw, profile_dir):
    """Close browser and clean up profile."""
    try:
        if ctx:
            ctx.close()
    except Exception:
        pass
    try:
        if pw:
            pw.stop()
    except Exception:
        pass
    shutil.rmtree(profile_dir, ignore_errors=True)


def _collect_all_pages(page, ctx, base_url, progress_callback, start_time, max_time):
    """Collect reviews from all pagination pages."""
    all_reviews = []
    page_num = 0

    while True:
        if time.time() - start_time > max_time:
            if progress_callback:
                progress_callback(len(all_reviews), "30分タイムアウト、収集終了")
            break

        cards = page.query_selector_all('[data-automation="reviewCard"]')
        if not cards:
            for alt_sel in ['[data-test-target="HR_CC_CARD"]', '.review-container']:
                cards = page.query_selector_all(alt_sel)
                if cards:
                    break

        if not cards:
            if progress_callback:
                progress_callback(len(all_reviews), f"ページ{page_num + 1}: カードなし、終了")
            break

        new_count = 0
        for card in cards:
            review = _parse_review_card(card)
            if review:
                all_reviews.append(review)
                new_count += 1

        if progress_callback:
            progress_callback(len(all_reviews), f"ページ{page_num + 1}: {new_count}件取得 (合計{len(all_reviews)}件)")

        if new_count == 0:
            break

        page_num += 1
        if page_num >= 30:
            break

        # Navigate to next page
        offset = f"-or{page_num * 15}"
        next_url = base_url.format(offset)
        try:
            page.goto(next_url, wait_until="networkidle", timeout=60000)
            time.sleep(3)

            html = page.content()
            if "captcha-delivery" in html:
                if progress_callback:
                    progress_callback(len(all_reviews), f"ページ{page_num + 1}でCAPTCHA、収集終了")
                break
        except Exception as e:
            if progress_callback:
                progress_callback(len(all_reviews), f"ページ{page_num + 1}取得失敗: {e}")
            break

    return all_reviews


def _prepare_base_url(url: str) -> str:
    """Ensure the URL has a {} placeholder for pagination offset."""
    if "{}" in url:
        return url
    if "Reviews-" in url:
        return url.replace("Reviews-", "Reviews{}-", 1)
    if "Reviews" in url:
        return url.replace("Reviews", "Reviews{}", 1)
    return url + "{}"


def _parse_review_card(card) -> dict | None:
    """Parse a single TripAdvisor review card element."""
    # review_id
    review_id = ""
    try:
        review_links = card.query_selector_all('a[href*="ShowUserReviews"]')
        for link in review_links:
            href = link.get_attribute("href") or ""
            m = re.search(r"-r(\d+)-", href)
            if m:
                review_id = m.group(1)
                break
    except Exception:
        pass

    if not review_id:
        for attr in ["data-reviewid", "data-review-id"]:
            val = card.get_attribute(attr) or ""
            if val:
                review_id = val
                break

    # Author
    author = ""
    for sel in [
        "a.BMQDV", "a.ui_header_link", "span.biGQs._P.fiohW.fOtGX",
        "a[onclick*='member']", "[class*='username']", "a[href*='/Profile/']",
    ]:
        try:
            el = card.query_selector(sel)
            if el:
                author = (el.text_content() or "").strip()
                if author:
                    break
        except Exception:
            continue

    # Rating
    rating = ""
    try:
        titles = card.query_selector_all("title")
        for t in titles:
            txt = t.text_content() or ""
            if "バブル評価" in txt or "段階中" in txt or "of 5 bubbles" in txt:
                rating = txt.strip()
                break
        if not rating:
            bubble = card.query_selector("[class*='bubble']")
            if bubble:
                rating = bubble.get_attribute("aria-label") or ""
    except Exception:
        pass

    # Date
    date = ""
    try:
        full_text = card.text_content() or ""
        date_match = re.search(r"(\d{4}年\d{1,2}月)", full_text)
        if date_match:
            date = date_match.group(1)
        else:
            date_match_en = re.search(r"([A-Z][a-z]+ \d{4})", full_text)
            if date_match_en:
                date = date_match_en.group(1)
    except Exception:
        pass

    # Comment
    comment = ""
    for sel in [
        "div.biGQs._P.VImYz.AWdfh", "div.biGQs._P.pZUbB.KxBGd",
        "[class*='reviewText']", ".partial_entry",
    ]:
        try:
            el = card.query_selector(sel)
            if el:
                comment = (el.text_content() or "").strip()
                if comment:
                    break
        except Exception:
            continue

    if not comment:
        return None

    return {
        "review_id": review_id, "author": author,
        "rating": rating, "date": date, "comment": comment,
    }
