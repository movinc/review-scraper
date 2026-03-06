"""Google Maps口コミ取得 - 平城苑 銀座5丁目店"""
from scrapling.fetchers import StealthySession
from scrapling.engines.toolbelt.fingerprints import generate_convincing_referer
import csv, time, sys

url = "https://www.google.com/maps/place/%E6%9D%B1%E4%BA%AC%E7%84%BC%E8%82%89+%E5%B9%B3%E5%9F%8E%E8%8B%91+%E9%8A%80%E5%BA%A75%E4%B8%81%E7%9B%AE%E5%BA%97/@35.670148,139.764609,17z/data=!4m8!3m7!1s0x60188b2c59652b99:0x5762724c3bb05387!8m2!3d35.670148!4d139.764609!9m1!1b1!16s%2Fg%2F11g2mx8ct4"
CSV_PATH = '/home/ubuntu/.openclaw/workspace/gmap_reviews_heijoen.csv'

for retry in range(5):
    session = StealthySession(headless=True)
    session.start()
    page = session.context.pages[0] if session.context.pages else session.context.new_page()
    page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}", lambda route: route.abort())
    referer = generate_convincing_referer(url)
    page.goto(url, referer=referer, wait_until='domcontentloaded', timeout=60000)
    found = False
    for attempt in range(20):
        if page.query_selector_all('.wiI7pd'):
            found = True; break
        time.sleep(2)
    if found:
        print(f"✅ 口コミ検出 (retry {retry})", flush=True)
        break
    try: session.close()
    except: pass
    print(f"❌ retry {retry}", flush=True)
else:
    sys.exit(1)

saved_ids = set()
f = open(CSV_PATH, 'w', newline='', encoding='utf-8-sig')
writer = csv.writer(f)
writer.writerow(['review_id', '投稿者', 'Rating', '投稿日', 'コメント'])

def save_reviews():
    blocks = page.query_selector_all('[data-review-id]')
    new_count = 0
    for block in blocks:
        try:
            rid = block.get_attribute('data-review-id')
            if not rid or rid in saved_ids: continue
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
        except: continue
    f.flush()
    return new_count

def cleanup():
    page.evaluate('''() => {
        document.querySelectorAll('[data-review-id] img, [data-review-id] picture, [data-review-id] svg').forEach(el => el.remove());
        document.querySelectorAll('canvas, .Tya61d, .p0Aybe, .cYrDcb').forEach(el => el.remove());
    }''')

save_reviews()
print(f"初期: {len(saved_ids)} 件", flush=True)

no_new = 0
for i in range(2000):
    page.evaluate('''() => {
        const els = document.querySelectorAll('div.m6QErb');
        for (const el of els) {
            if (el.scrollHeight > el.clientHeight && el.scrollHeight > 500) {
                el.scrollTop = el.scrollHeight;
            }
        }
    }''')
    time.sleep(1.0)
    if i % 3 == 2:
        new = save_reviews()
        cleanup()
        if new == 0: no_new += 1
        else: no_new = 0
    if i % 20 == 0:
        print(f"scroll {i+1}: saved {len(saved_ids)}", flush=True)
    if no_new >= 20:
        save_reviews()
        print(f"→ 完了 ({len(saved_ids)} 件)", flush=True)
        break

f.close()
try: session.close()
except: pass
print(f"\n=== {len(saved_ids)} 件 → {CSV_PATH} ===", flush=True)
