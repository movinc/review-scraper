# Bot対策突破ガイド — Google Maps & TripAdvisor（2026年3月時点）

> review-scraperプロジェクトで得た実践的知見。別リポジトリでクローラーを作り直す際の引き継ぎ資料。

---

## 目次

1. [共通の原則](#共通の原則)
2. [ツールチェイン](#ツールチェイン)
3. [Google Maps](#google-maps)
4. [TripAdvisor](#tripadvisor)
5. [Cloud Run固有の問題](#cloud-run固有の問題)
6. [CSSセレクタ一覧](#cssセレクタ一覧)
7. [失敗パターン集](#失敗パターン集)
8. [推奨アーキテクチャ](#推奨アーキテクチャ)

---

## 共通の原則

### フィンガープリント対策は必須

素のPlaywrightはボット判定される。以下の対策が必要：

| 対策 | 効果 | 実装方法 |
|------|------|----------|
| browserforgeフィンガープリント | navigator, screen, WebGL等を偽装 | Scrapling内蔵 |
| WebRTCブロック | ローカルIP漏洩防止 | `block_webrtc=True` |
| Canvas fingerprint隠蔽 | Canvas API経由の識別防止 | `hide_canvas=True` |
| ビューポートランダム化 | 同一解像度の連続アクセス回避 | 6種類からランダム選択 |
| ランダム遅延 | 機械的アクセスパターン回避 | 1.5〜2.5秒のスクロール間隔 |

### リトライ戦略

```
失敗したら → ブラウザプロファイル再生成 → 15-30秒で次の試行
90秒待ってリトライは遅すぎる。ダメなものは早く切り替える。
```

- リトライごとに新しいプロファイルディレクトリ（`/tmp/profiles/{uuid}`）
- SingletonLock競合を防ぐため、古いプロファイルは使い回さない
- 最大3回のアウターリトライ × 5回のインナーリトライ

### IPローテーション

- **Cloud RunのIPはブラックリスト入りしやすい**（特にTripAdvisor）
- Torは「フォールバック」として使う（メインにしない）
- Tor出口ノードもブロック対象なので万能ではない
- 直接接続を優先し、CAPTCHA検出時にTorに切り替える

### `networkidle` は使うな

```python
# ❌ ハングする
page.goto(url, wait_until="networkidle")

# ✅ これで十分
page.goto(url, wait_until="domcontentloaded")
# その後、必要な要素をwait_for_selectorで待つ
```

Google Maps SPA、TripAdvisorともに`networkidle`は永遠に完了しない（WebSocket、Analytics等）。

### `disable_resources=True` は使うな

Scraplingの`disable_resources=True`はfont/image/media/**stylesheet**を全部ブロックする。

- Google Maps: SPAがレンダリング不能（タブ検出不可）
- TripAdvisor: DOM構造が変化し、パーサーが全件失敗

**画像だけブロックしたい場合:**
```python
page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,mp3}", lambda r: r.abort())
```

---

## ツールチェイン

### Scrapling（推奨）

```
pip install scrapling[all]==0.4.1
```

> ⚠️ バージョン固定必須。0.4.2以降で`generate_convincing_referer`が削除された。

**使い分け:**

| クラス | 用途 | 特徴 |
|--------|------|------|
| `StealthySession` | Google Maps | ブラウザセッションを直接制御。`page_action`不要 |
| `StealthyFetcher.fetch()` | TripAdvisor | `google_search=True`でリファラ偽装。`page_action`でDOM操作 |

`StealthyFetcher.fetch(page_action=...)` はGoogle Mapsには使えない（SPAのレビュータブがレンダリングされない）。

### Playwright直接操作が必要な場面

Scraplingはラッパーなので、以下はPlaywrightのページオブジェクトを直接操作する必要がある：

- `page.evaluate()` — DOM操作、JS実行
- `page.mouse.wheel()` — スクロール
- `page.route()` — リソースブロック
- `page.screenshot()` — デバッグ用スクリーンショット

---

## Google Maps

### 基本フロー

```
1. google.com にアクセス（Cookie取得: NID, AEC）
2. Google Maps URLにgoto（domcontentloaded）
3. 「クチコミ」タブをクリック
4. 「新しい順」にソート
5. スクロールしてレビューを読み込み
6. DOMからレビューを抽出
```

### URL形式の罠

```
❌ https://www.google.com/maps/place/...!9m1!1b1
   → レビューが0件表示される

✅ https://www.google.com/maps/place/...
   → 概要タブから開始、クチコミタブをクリックで遷移
```

`!9m1!1b1`（レビュータブ直接指定）はSPAの内部状態がおかしくなる。必ず概要タブから入る。

### スクロール方式（最重要）

```python
# ❌ ボット判定される
container.evaluate("el => el.scrollTop = el.scrollHeight")

# ✅ 人間的なスクロール
page.mouse.move(container_x, container_y)  # まずhover
page.mouse.wheel(0, 800)                    # wheelイベントで800px
await asyncio.sleep(random.uniform(1.5, 2.5))
```

**なぜ `scrollTop` がダメか:**
- Google Mapsは`scrollTop`の変化速度を監視している
- 一気に最下部までジャンプ = ボット判定
- `mouse.wheel()` は人間のマウスホイール操作と同じイベントを発火

### スクロールリカバリ

新規レビューが読み込まれなくなったら：

```python
# 上に戻して再スクロール（lazy loadingのトリガー）
page.mouse.wheel(0, -3000)  # 上に大きく戻る
await asyncio.sleep(2)
page.mouse.wheel(0, 3000)   # 下に戻る
```

5回連続で新規0件 → 停滞判定 → リカバリ試行。それでもダメなら取れた分で完了。

### ソート（新しい順）

```python
# ソートボタンをクリック
sort_btn = page.query_selector('button[aria-label="クチコミの並べ替え"]')
sort_btn.click()
await asyncio.sleep(1)

# 「新しい順」を選択（index=1）
option = page.query_selector('[role="menuitemradio"][data-index="1"]')
option.click()
await asyncio.sleep(3)  # レビュー再読み込み待ち
```

### レビュー抽出

```python
# レビューコンテナ
reviews = page.query_selector_all('[data-review-id]')

# 各レビューから抽出
review_id = el.get_attribute('data-review-id')
text = el.query_selector('.wiI7pd')?.inner_text()
rating = el.query_selector('.kvMYJc')?.get_attribute('aria-label')
# "星 5 つ" → 5
```

> ⚠️ `data-review-id`は重複する（DOM内に同じIDの要素が複数存在）。セットで重複排除が必要。

### メモリ管理

1000件超えるとブラウザがクラッシュしやすい。対策：

```python
# 定期的にDOMの重い要素を削除
page.evaluate("""() => {
    document.querySelectorAll('img, svg, canvas').forEach(el => {
        if (!el.closest('[data-review-id]')) el.remove()
    })
}""")
```

レビューはインクリメンタルに保存（全件メモリに持たない）。

---

## TripAdvisor

### 基本フロー

```
1. StealthyFetcher.fetch(google_search=True, page_action=action_fn)
2. action_fn内でページ操作
   a. マーケティングモーダル除去
   b. 言語フィルタ解除（全言語に変更）
   c. ページネーションで全ページ取得
3. 各ページからレビュー抽出
```

### CAPTCHA（DataDome + スライダー）

**検出方法:**
```python
html = page.content()
if "captcha-delivery" in html:
    # CAPTCHA検出
```

**回避戦略:**
1. `google_search=True` — Google検索リファラ経由でアクセス（DataDome回避の主力）
2. Torプロキシ — IPブラックリスト回避（Cloud RunのIP帯がブロックされてる場合）
3. リトライ時に交互に切り替え（直接→Tor→直接+google_search→Tor+google_search）

**スライダーCAPTCHA（2026年3月時点）:**
- Cloud Run IPで高確率で発生
- 自動解決は非現実的（画像認証型ではないが、ブラウザ自動化検出と組み合わさっている）
- IP変更（Tor）が最も効果的な回避策

### 言語フィルタ（全言語取得）

TripAdvisorは国別ドメインでその言語のレビューのみ表示する:
- `.com` → English only
- `.jp` → Japanese only

**全言語取得の方法（`.com`ドメインで）:**

```python
# 1. マーケティングモーダルを除去（操作を阻害する）
page.evaluate("() => document.querySelectorAll('.ab-iam-root, iframe[title=\"Modal Message\"]').forEach(el => el.remove())")

# 2. フィルタボタンをdispatchEventでクリック（Playwright clickでは開かない）
page.evaluate("""() => {
    const btn = document.querySelector('[aria-label*="filter" i]');
    if (btn) btn.dispatchEvent(new MouseEvent('click', {bubbles: true}));
}""")
await asyncio.sleep(2)

# 3. ダイアログ内の「English」ボタンを解除（Playwright click必須）
dialog = page.query_selector('[role="dialog"]')
for btn in dialog.query_selector_all('button'):
    if 'English' in btn.inner_text():
        btn.click(force=True)  # React状態更新にはPlaywright click

# 4. 「All languages」を選択
for opt in dialog.query_selector_all('[role="option"]'):
    if 'All languages' in opt.inner_text():
        opt.click(force=True)

# 5. Applyをクリック
apply_btn = dialog.query_selector('button:has-text("Apply")')
apply_btn.click(force=True)
```

### Playwright click vs JS native click（超重要）

| 操作 | Playwright `click(force=True)` | JS `dispatchEvent` / `element.click()` |
|------|------|------|
| フィルタボタン開く | ❌ モーダル開かない | ✅ `dispatchEvent`で開く（成功率50%） |
| React状態変更（English解除等）| ✅ React合成イベント発火 | ❌ 状態更新されない |
| ページネーション（次へ）| ❌ DOM更新されない | ✅ SPA遷移発火 |

**原則: React SPAのリンク遷移 → JS native click、ボタン状態変更 → Playwright click**

### ページネーション

```python
# 次ページリンクのクリック（JS native click必須）
page.evaluate("""() => {
    const a = document.querySelector('a[aria-label*="Next"], a[aria-label*="次"]');
    if (a) { a.click(); return true; }
    return false;
}""")
await asyncio.sleep(3)
```

- 1ページ15件。15件未満 = 最終ページ
- `page.goto()`でページ遷移するとフィルタがリセットされるので、必ずDOM内のリンクをクリック

### レビュー抽出

```python
# 基本構造
review_cards = page.query_selector_all('[data-automation="reviewCard"]')

# Rating: SVG内のtitleから抽出
# ⚠️ query_selector_all("title") ではSVG内のtitleが取れない
# → inner_html()から正規表現で抽出
html = card.inner_html()
match = re.search(r'<title>.*?(\d+)\s*(?:of|段階中)\s*(\d+)', html)
rating = int(match.group(1)) if match else None

# Date
date_text = card.query_selector('.biGQs._P.pZUbB.ncFvv.osNWb')?.inner_text()
# "Feb 2025" or "2024年3月" → ISO date

# Author
author = card.query_selector('a.BMQDV.ukgoS')?.inner_text()

# review_id: ShowUserReviewsリンクから抽出
link = card.query_selector('a[href*="ShowUserReviews"]')
# href → review ID
```

---

## Cloud Run固有の問題

### 1ジョブ = 1インスタンス

ブラウザスクレイピングはCPU/メモリを大量消費する。Cloud Run上で複数ジョブを同一インスタンスで実行するとハングする。

**解決策: Cloud Tasks**

```
POST /scrape → Firestore(queued) → Cloud Tasks enqueue
                                        ↓
                              POST /worker/run（新インスタンスで実行）
```

- `concurrency=1` — 1リクエスト = 1インスタンス
- `max-instances=10` — 最大10並列
- Cloud Tasksキュー: `max-concurrent-dispatches=5`, `max-dispatches-per-second=10`

### asyncioとPlaywrightの競合

```python
# ❌ Playwright（sync API）をasyncioイベントループ内で実行
asyncio.to_thread(scrape_fn)  # スレッドプールが既存ループを検出

# ✅ 毎回新しいThreadPoolExecutorで実行
with ThreadPoolExecutor(max_workers=1) as executor:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, scrape_fn)
```

### デプロイ時の注意

```bash
# ❌ ソースデプロイ（キャッシュが効いて変更反映されない）
gcloud run deploy --source .

# ✅ 明示的ビルド + イメージ指定デプロイ
gcloud builds submit --tag $IMAGE --no-cache
gcloud run deploy --image $IMAGE
```

- リビジョンが失敗状態だとトラフィック切替が永遠にリトライされる
- `--filter="status.conditions.status=True"` でReadyなリビジョンのみ選択

### Firestoreキャッシュの罠

ジョブ作成インスタンス(A) ≠ ワーカーインスタンス(B)。インメモリキャッシュは使えない。

```python
# ❌ メモリ優先（他インスタンスの更新が見えない）
def get_job(id):
    if id in _mem: return _mem[id]

# ✅ 常にFirestoreから読む
def get_job(id):
    doc = db.collection('jobs').document(id).get()
    if doc.exists: return doc.to_dict()
```

---

## CSSセレクタ一覧

### Google Maps

```python
# レビューコンテナ
REVIEW_ITEM = '[data-review-id]'
REVIEW_TEXT = '.wiI7pd'
REVIEW_RATING = '.kvMYJc'
REVIEW_AUTHOR = '.d4r55'
REVIEW_DATE = '.rsqaWe'

# ナビゲーション
TAB_BUTTON = 'button[role="tab"]'
SORT_BUTTON = 'button[aria-label="クチコミの並べ替え"]'
SORT_NEWEST = '[role="menuitemradio"][data-index="1"]'
SCROLL_CONTAINER = 'div.m6QErb.DxyBCb'

# 「もっと見る」
MORE_BUTTON = '.w8nwRe.kyuRq'
```

### TripAdvisor

```python
# レビュー
REVIEW_CARD = '[data-automation="reviewCard"]'
REVIEW_AUTHOR = 'a.BMQDV.ukgoS'
REVIEW_DATE = '.biGQs._P.pZUbB.ncFvv.osNWb'

# ナビゲーション
NEXT_PAGE = 'a[aria-label*="Next"], a[aria-label*="次"]'
FILTER_BUTTON = '[aria-label*="filter" i]'

# CAPTCHA検出
CAPTCHA_MARKER = 'captcha-delivery'  # in page HTML
```

> ⚠️ セレクタは頻繁に変更される。動かなくなったらDevToolsで最新のDOM構造を確認すること。

---

## 失敗パターン集

| 症状 | 原因 | 対策 |
|------|------|------|
| Google Maps レビュー0件 | URLに`!9m1!1b1`が含まれている | URLからパラメータを除去 |
| Google Maps レビュー0件 | `disable_resources=True` | Falseに変更 |
| Google Maps 10-15件で停止 | `scrollTop = scrollHeight` | `mouse.wheel()`に変更 |
| Google Maps タブ0個 | Tor経由でSPAレンダリング失敗 | 直接接続に切り替え |
| Google Maps ハング | `wait_until="networkidle"` | `domcontentloaded`に変更 |
| TripAdvisor CAPTCHA | Cloud Run IPブラックリスト | Torフォールバック |
| TripAdvisor 英語のみ | `.com`ドメインのデフォルトフィルタ | 言語フィルタ解除 or `?filterLang=ALL` |
| TripAdvisor フィルタ開かない | Playwright `click()`使用 | `dispatchEvent`に変更 |
| TripAdvisor ページ遷移しない | Playwright `click()`使用 | JS `element.click()`に変更 |
| Cloud Run 同一インスタンスに複数ジョブ | asyncio.create_task | Cloud Tasks使用 |
| Cloud Run ハング | asyncio.to_thread のスレッド再利用 | 新規ThreadPoolExecutor |
| デプロイ反映されない | ソースデプロイのキャッシュ | `--no-cache` + イメージ指定 |
| ステータス更新されない | インメモリキャッシュ | 常にFirestoreから読む |

---

## 推奨アーキテクチャ

新規リポジトリで作り直す場合の推奨構成:

```
crawler/
├── core/
│   ├── browser.py          # Scrapling初期化、プロファイル管理
│   ├── antibot.py          # フィンガープリント、遅延、リトライ
│   └── proxy.py            # Tor管理、IPローテーション
├── sites/
│   ├── google_maps.py      # Google Maps固有ロジック
│   └── tripadvisor.py      # TripAdvisor固有ロジック
├── models/
│   └── review.py           # レビューデータモデル
├── storage/
│   └── firestore.py        # 永続化
├── api/
│   └── server.py           # FastAPI
└── worker/
    └── tasks.py            # Cloud Tasks連携
```

**設計原則:**
- サイト固有ロジックと共通ロジック（ブラウザ管理、リトライ、プロキシ）を分離
- `page_action`パターン（TripAdvisor）と直接セッション操作（Google Maps）の両方に対応
- レビューはインクリメンタル保存（メモリに全件持たない）
- スクリーンショットによるデバッグ可視化は最初から組み込む

---

*最終更新: 2026-03-10*
*ソース: review-scraper プロジェクト（github.com:sotarofujimaki/review-scraper.git）*
