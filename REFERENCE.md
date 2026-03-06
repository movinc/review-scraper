# Scrapling 口コミスクレイピング 再現手順書

> **サマリ**
> - **Scrapling** の `StealthySession` を使えば、Google Maps・TripAdvisor の口コミをログインなしで取得可能
> - Google Maps は素の Playwright では口コミタブが表示されない → **Scrapling のフィンガープリント偽装が必須**
> - 全件取得にはスクロール操作が必要。1000件超はメモリ対策（画像ブロック＋逐次CSV保存）で対応
> - TripAdvisor は `StealthyFetcher` のみで安定取得。ページネーションで全件カバー
> - 検証日: 2026-03-06 / Python 3.10 + Scrapling 0.4.1

## 概要

[Scrapling](https://github.com/D4Vinci/Scrapling) を使って Google Maps・TripAdvisor の口コミを取得する手順。
Scraplingのフィンガープリント偽装機能がないと Google Maps の口コミタブが表示されないため、素の Playwright では再現不可。

---

## 1. 環境構築

```bash
pip install scrapling[all]
python3 -m playwright install chromium
python3 -m playwright install-deps chromium
```

---

## 2. Google Maps 口コミ取得

### 2-1. 初期表示分のみ（15件程度）

```python
from scrapling.fetchers import StealthyFetcher

url = "https://www.google.com/maps/place/店名/@lat,lng,17z/data=!4m8!3m7!1sPlaceID!8m2!3dlat!4dlng!9m1!1b1!16s..."

page = StealthyFetcher.fetch(url, headless=True, network_idle=True)

reviews = page.css('.wiI7pd')
for r in reviews:
    print(r.text)
```

**ポイント:**
- URLに `!9m1!1b1` を含めると口コミタブが初期表示される
- `network_idle=True` が必須（JS レンダリング待ち）
- `google_search=True` は明示しない（デフォルトのままが安定）
- `page_action` パラメータは渡さない（口コミが消えるバグあり）

### 2-2. 全件取得（スクロール）

`StealthySession` でブラウザを起動し、Playwright のページオブジェクトを直接操作する。

```python
from scrapling.fetchers import StealthySession
from scrapling.engines.toolbelt.fingerprints import generate_convincing_referer
import csv, time, sys

url = "Google MapsのURL（!9m1!1b1付き）"
CSV_PATH = "output.csv"

# --- ブラウザ起動（リトライ付き） ---
for retry in range(5):
    session = StealthySession(headless=True)
    session.start()
    page = session.context.pages[0] if session.context.pages else session.context.new_page()
    
    # 画像をブロック（メモリ節約）
    page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
               lambda route: route.abort())
    
    # リファラ偽装（重要）
    referer = generate_convincing_referer(url)
    page.goto(url, referer=referer, wait_until='domcontentloaded', timeout=60000)
    
    # 口コミ描画待ち（wait_for_selectorは不安定なのでポーリング）
    found = False
    for _ in range(20):
        if page.query_selector_all('.wiI7pd'):
            found = True
            break
        time.sleep(2)
    
    if found:
        print(f"✅ 口コミ検出 (retry {retry})")
        break
    
    try: session.close()
    except: pass
    print(f"❌ retry {retry} 失敗")
else:
    print("全リトライ失敗")
    sys.exit(1)

# --- CSV逐次書き込み ---
saved_ids = set()
f = open(CSV_PATH, 'w', newline='', encoding='utf-8-sig')
writer = csv.writer(f)
writer.writerow(['review_id', '投稿者', 'Rating', '投稿日', 'コメント'])

def save_reviews():
    """現在DOMにある未保存の口コミをCSVに書き込む"""
    blocks = page.query_selector_all('[data-review-id]')
    new_count = 0
    for block in blocks:
        try:
            rid = block.get_attribute('data-review-id')
            if not rid or rid in saved_ids:
                continue
            
            # 「もっと見る」を展開
            more = block.query_selector('button.w8nwRe')
            if more:
                try: more.click(); time.sleep(0.08)
                except: pass
            
            author = block.query_selector('.d4r55')
            rating = block.query_selector('.kvMYJc')
            date = block.query_selector('.rsqaWe')
            text = block.query_selector('.wiI7pd')
            
            a = (author.text_content() or '').strip() if author else ''
            r = (rating.get_attribute('aria-label') or '').strip() if rating else ''
            d = (date.text_content() or '').strip() if date else ''
            t = (text.text_content() or '').strip() if text else ''
            
            if t:
                writer.writerow([rid, a, r, d, t])
                saved_ids.add(rid)
                new_count += 1
        except:
            continue
    f.flush()
    return new_count

def cleanup_heavy_elements():
    """画像等の重い要素だけ削除（口コミブロック自体は残す）"""
    page.evaluate('''() => {
        document.querySelectorAll('[data-review-id] img, [data-review-id] picture, [data-review-id] svg').forEach(el => el.remove());
        document.querySelectorAll('canvas, .Tya61d, .p0Aybe, .cYrDcb').forEach(el => el.remove());
    }''')

# --- 初期保存 ---
save_reviews()
print(f"初期: {len(saved_ids)} 件")

# --- スクロールループ ---
no_new = 0
for i in range(2000):
    # スクロール
    page.evaluate('''() => {
        const els = document.querySelectorAll('div.m6QErb');
        for (const el of els) {
            if (el.scrollHeight > el.clientHeight && el.scrollHeight > 500) {
                el.scrollTop = el.scrollHeight;
            }
        }
    }''')
    time.sleep(1.0)
    
    # 3スクロールごとに保存 + メモリ解放
    if i % 3 == 2:
        new = save_reviews()
        cleanup_heavy_elements()
        if new == 0:
            no_new += 1
        else:
            no_new = 0
    
    if i % 20 == 0:
        print(f"scroll {i+1}: saved {len(saved_ids)}")
    
    # 20回連続で新規なし → 終了
    if no_new >= 20:
        save_reviews()
        print(f"→ 完了 ({len(saved_ids)} 件)")
        break

f.close()
try: session.close()
except: pass
```

---

## 3. TripAdvisor 口コミ取得

```python
from scrapling.fetchers import StealthyFetcher
import csv, re

base_url = "https://www.tripadvisor.jp/Restaurant_Review-g...-d...-Reviews{}-店名.html"
CSV_PATH = "tripadvisor_output.csv"

all_reviews = []
page_num = 0

while True:
    offset = f"-or{page_num * 15}" if page_num > 0 else ""
    url = base_url.format(offset)
    
    page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
    cards = page.css('[data-automation="reviewCard"]')
    
    if not cards:
        break
    
    for card in cards:
        # review_id
        review_id = ''
        review_link = card.css('a[href*="ShowUserReviews"]')
        if review_link:
            m = re.search(r'-r(\d+)-', review_link[0].attrib.get('href', ''))
            if m: review_id = m.group(1)
        
        # 投稿者
        author_el = card.css('a.BMQDV')
        author = (author_el[0].text or '').strip() if author_el else ''
        
        # Rating
        rating = ''
        for t in card.css('title'):
            txt = t.text or ''
            if 'バブル評価' in txt:
                rating = txt.strip()
                break
        
        # 投稿日
        full_text = card.get_all_text()
        date_match = re.search(r'(\d{4}年\d{1,2}月)', full_text)
        date = date_match.group(1) if date_match else ''
        
        # コメント（.text ではなく .get_all_text() を使う）
        comment_el = card.css('div.biGQs._P.VImYz.AWdfh')
        comment = comment_el[0].get_all_text().strip() if comment_el else ''
        
        if comment:
            all_reviews.append([review_id, author, rating, date, comment])
    
    page_num += 1
    if page_num >= 30:
        break

with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(['review_id', '投稿者', 'Rating', '投稿日', 'コメント'])
    writer.writerows(all_reviews)
```

---

## 4. CSS セレクタ一覧

### Google Maps

| 要素 | セレクタ | 取得方法 |
|------|----------|----------|
| 口コミブロック | `[data-review-id]` | `data-review-id` 属性が review_id |
| 口コミテキスト | `.wiI7pd` | `.text_content()` |
| 投稿者名 | `.d4r55` | `.text_content()` |
| 評価（星数） | `.kvMYJc` | `.get_attribute('aria-label')` → 例: "5 つ星" |
| 投稿日 | `.rsqaWe` | `.text_content()` → 例: "2 週間前" |
| 「もっと見る」 | `button.w8nwRe` | `.click()` で展開 |
| スクロールコンテナ | `div.m6QErb` | `scrollTop = scrollHeight` でスクロール |

### TripAdvisor

| 要素 | セレクタ | 取得方法 |
|------|----------|----------|
| 口コミカード | `[data-automation="reviewCard"]` | |
| コメント | `div.biGQs._P.VImYz.AWdfh` | `.get_all_text()`（`.text` は空になる） |
| 投稿者 | `a.BMQDV` | `.text` |
| 評価 | `title` 要素 | 「バブル評価 5 段階中 X」テキスト |
| review_id | `a[href*="ShowUserReviews"]` | href から `-r{id}-` を正規表現抽出 |

---

## 5. 注意事項・既知の問題

| 問題 | 対策 |
|------|------|
| StealthySession 起動の約30%で口コミ非表示 | 最大5回リトライ |
| 1000件超でブラウザ EPIPE クラッシュ | 画像ブロック + 逐次CSV保存 |
| `page_action` を渡すと口コミが消える | 使わない（直接ページ操作する） |
| DOM要素削除でスクロール停止 | 画像等の子要素だけ削除、口コミブロック自体は残す |
| TripAdvisor 2ページ目以降で 403 | リトライまたは間隔を空ける |
| Google Maps の口コミタブが出ない | URLに `!9m1!1b1` を含める |

---

## 6. 出力CSV形式

```
review_id,投稿者,Rating,投稿日,コメント
```

- エンコーディング: `utf-8-sig`（Excel で文字化けしない BOM 付き UTF-8）
- review_id: Google Maps は base64風文字列、TripAdvisor は数値ID
