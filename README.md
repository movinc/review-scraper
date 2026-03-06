# Review Scraper API

FastAPI web service that scrapes reviews from Google Maps and TripAdvisor.

## API

### POST /scrape

**Request body:**
```json
{"url": "https://...", "source": "gmap"}
```

`source` is either `"gmap"` or `"tripadvisor"`.

**Response (JSON):**
```json
[{"review_id": "...", "author": "...", "rating": "...", "date": "...", "comment": "..."}]
```

**CSV response:** Add `?format=csv` query parameter.

## Local Development

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

## Deploy to Cloud Run

```bash
gcloud run deploy review-scraper \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300
```
