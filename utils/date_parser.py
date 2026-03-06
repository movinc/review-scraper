"""Parse Japanese date strings into ISO datetime format."""
import re
from datetime import datetime, timedelta


def parse_japanese_date(text: str) -> str:
    """Convert Japanese date string to ISO 8601 (YYYY-MM-DD).
    
    Supports:
    - Relative: "1 か月前", "2 週間前", "3 日前", "1 年前"
    - Absolute: "2024年3月", "2024年3月15日"
    - Already ISO: "2024-03-15"
    """
    if not text:
        return ""
    
    text = text.strip()
    
    # Already ISO format
    if re.match(r'\d{4}-\d{2}-\d{2}', text):
        return text[:10]
    
    now = datetime.utcnow()
    
    m = re.search(r'(\d+)\s*年前', text)
    if m:
        dt = now - timedelta(days=int(m.group(1)) * 365)
        return dt.strftime('%Y-%m-%d')
    
    m = re.search(r'(\d+)\s*か月前', text)
    if m:
        dt = now - timedelta(days=int(m.group(1)) * 30)
        return dt.strftime('%Y-%m-%d')
    
    m = re.search(r'(\d+)\s*週間前', text)
    if m:
        dt = now - timedelta(weeks=int(m.group(1)))
        return dt.strftime('%Y-%m-%d')
    
    m = re.search(r'(\d+)\s*日前', text)
    if m:
        dt = now - timedelta(days=int(m.group(1)))
        return dt.strftime('%Y-%m-%d')
    
    m = re.search(r'(\d+)\s*時間前', text)
    if m:
        dt = now - timedelta(hours=int(m.group(1)))
        return dt.strftime('%Y-%m-%d')
    
    # "2024年3月15日"
    m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    
    # "2024年3月"
    m = re.match(r'(\d{4})年(\d{1,2})月', text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    
    # English
    m = re.search(r'(\d+)\s*months?\s*ago', text)
    if m:
        dt = now - timedelta(days=int(m.group(1)) * 30)
        return dt.strftime('%Y-%m-%d')
    
    m = re.search(r'(\d+)\s*weeks?\s*ago', text)
    if m:
        dt = now - timedelta(weeks=int(m.group(1)))
        return dt.strftime('%Y-%m-%d')
    
    m = re.search(r'(\d+)\s*days?\s*ago', text)
    if m:
        dt = now - timedelta(days=int(m.group(1)))
        return dt.strftime('%Y-%m-%d')
    
    m = re.search(r'(\d+)\s*years?\s*ago', text)
    if m:
        dt = now - timedelta(days=int(m.group(1)) * 365)
        return dt.strftime('%Y-%m-%d')
    
    return text
