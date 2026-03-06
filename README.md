# Review Scraper API

Google Maps・TripAdvisorのレビューをスクレイピングするFastAPIサービス。

## ファイル構成

```
review-scraper/
├── main.py              # FastAPIアプリ本体。エンドポイント定義・ジョブ管理
├── config.py            # 全設定値（タイムアウト、リトライ数、Torポートなど）の一元管理
├── models.py            # PydanticモデルとEnumの定義（ScrapeRequest, Review, JobStatusなど）
├── css_selectors.py     # CSSセレクターをフォールバック付きで一元管理。サイト変更時はここだけ修正
├── db.py                # Firestoreを使ったジョブ・レビューのCRUD操作
├── scraper/
│   ├── google.py        # Google Mapsスクレイパー（Playwright使用）
│   └── tripadvisor.py   # TripAdvisorスクレイパー（Playwright使用）
├── utils/
│   ├── tor.py           # Tor接続確認・回線切り替えユーティリティ
│   └── date_parser.py   # 日本語日付文字列（「1か月前」等）をISO 8601に変換
└── static/
    └── index.html       # 管理UI（ジョブ投入・ステータス確認）
```

## API エンドポイント

### `POST /scrape`

スクレイピングジョブを非同期で開始する。

**リクエスト:**
```json
{"url": "https://maps.google.com/...", "source": "google"}
```

`source` は `"google"` または `"tripadvisor"`。

**レスポンス (202):**
```json
{"job_id": "abc12345", "status": "running"}
```

---

### `GET /jobs/{job_id}`

ジョブの状態・進捗を取得する。

**レスポンス:**
```json
{
  "job_id": "abc12345",
  "status": "done",
  "progress": 42,
  "message": "完了: 42件取得",
  "duration": 38
}
```

---

### `GET /jobs/{job_id}/reviews`

取得済みレビュー一覧を返す。`?format=csv` でCSV形式にも対応。

---

### `GET /jobs`

最近のジョブ一覧を返す。

---

### `DELETE /jobs/{job_id}`

ジョブとレビューデータを削除する。

---

### `GET /jobs/{job_id}/logs`

スクレイピングの詳細ログを返す（デバッグ用）。

---

## ローカル開発

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium
uvicorn main:app --reload
```

## Docker

```bash
docker build -t review-scraper .
docker run -p 8080:8080 review-scraper
```

## Cloud Run デプロイ

```bash
gcloud run deploy review-scraper \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300
```

## 環境変数

| 変数名 | 説明 | デフォルト |
|---|---|---|
| `GOOGLE_PROFILE_BASE` | Playwrightプロファイルの保存先 | `/tmp/google-profiles` |
| `FIRESTORE_COLLECTION` | Firestoreコレクション名 | `scrape_jobs` |

Torが `localhost:9050` で起動していれば自動的にプロキシ経由でリクエストする。
