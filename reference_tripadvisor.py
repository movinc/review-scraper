"""TripAdvisor口コミ取得 - 平城苑 銀座5丁目店（review_id付き）"""
from scrapling.fetchers import StealthyFetcher
import csv, re

base_url = "https://www.tripadvisor.jp/Restaurant_Review-g14129573-d15009042-Reviews{}-TokyoYakiniku_Heijoen_Ginza_5chome-Ginza_Chuo_Tokyo_Tokyo_Prefecture_Kanto.html"
CSV_PATH = '/home/ubuntu/.openclaw/workspace/tripadvisor_reviews_heijoen.csv'

all_reviews = []
page_num = 0

while True:
    offset = f"-or{page_num * 15}" if page_num > 0 else ""
    url = base_url.format(offset)
    print(f"\nPage {page_num + 1}", flush=True)
    
    page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
    cards = page.css('[data-automation="reviewCard"]')
    print(f"  Cards: {len(cards)}", flush=True)
    
    if not cards:
        print("  → 終了", flush=True)
        break
    
    new_count = 0
    for card in cards:
        # review_id（data-reviewid属性やリンクから取得）
        review_id = ''
        review_link = card.css('a[href*="ShowUserReviews"]')
        if review_link:
            href = review_link[0].attrib.get('href', '')
            m = re.search(r'-r(\d+)-', href)
            if m: review_id = m.group(1)
        if not review_id:
            # data属性から
            for attr_name in ['data-reviewid', 'data-review-id']:
                val = card.attrib.get(attr_name, '')
                if val:
                    review_id = val; break
        
        # 投稿者
        author_el = card.css('a.BMQDV')
        author = (author_el[0].text or '').strip() if author_el else ''
        
        # Rating
        rating = ''
        title_els = card.css('title')
        for t in title_els:
            txt = t.text or ''
            if 'バブル評価' in txt or '段階中' in txt:
                rating = txt.strip(); break
        
        # 投稿日
        full_text = card.get_all_text()
        date = ''
        date_match = re.search(r'(\d{4}年\d{1,2}月)', full_text)
        if date_match:
            date = date_match.group(1)
        
        # コメント
        comment_el = card.css('div.biGQs._P.VImYz.AWdfh')
        comment = comment_el[0].get_all_text().strip() if comment_el else ''
        
        if comment:
            all_reviews.append({
                'review_id': review_id,
                'author': author,
                'rating': rating,
                'date': date,
                'text': comment,
            })
            new_count += 1
            print(f"    [{review_id}] {author} | {rating} | {date} | {comment[:50]}", flush=True)
    
    if new_count == 0:
        print("  → 口コミなし、終了", flush=True)
        break
    
    page_num += 1
    if page_num >= 30: break

with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(['review_id', '投稿者', 'Rating', '投稿日', 'コメント'])
    for r in all_reviews:
        writer.writerow([r['review_id'], r['author'], r['rating'], r['date'], r['text']])

print(f"\n=== 完了: {len(all_reviews)} 件 → {CSV_PATH} ===", flush=True)
