"""Migrate existing review dates to ISO format in Firestore."""
import os
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fujimaki-sandbox-484206")

from google.cloud import firestore
from utils.date_parser import parse_japanese_date

db = firestore.Client()
jobs = db.collection("scrape_jobs").stream()

total = 0
updated = 0

for job_doc in jobs:
    job_id = job_doc.id
    reviews = db.collection("scrape_jobs").document(job_id).collection("reviews").stream()
    
    batch = db.batch()
    count = 0
    for rev_doc in reviews:
        data = rev_doc.to_dict()
        old_date = data.get("date", "")
        new_date = parse_japanese_date(old_date)
        
        if new_date != old_date:
            ref = db.collection("scrape_jobs").document(job_id).collection("reviews").document(rev_doc.id)
            batch.update(ref, {"date": new_date})
            count += 1
            updated += 1
        total += 1
        
        if count >= 450:
            batch.commit()
            batch = db.batch()
            count = 0
    
    if count > 0:
        batch.commit()
    
    print(f"Job {job_id}: {count} dates updated")

print(f"\nTotal: {total} reviews, {updated} dates updated")
