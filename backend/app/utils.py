from typing import Optional

def parse_date_flexible(date_str: str) -> Optional[str]:
    """Parse various date formats and return YYYY-MM-DD format."""
    if not date_str:
        return None
    
    date_str = date_str.strip().lower()
    
    from datetime import datetime
    
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%dth %b %Y",
        "%dth %B %Y",
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except:
            continue
    
    return None

def date_in_range(date_str: str, start_date: str, end_date: str) -> bool:
    """Check if a date falls within a range."""
    try:
        from datetime import datetime
        date = datetime.strptime(date_str, "%Y-%m-%d")
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        return start <= date <= end
    except:
        return False

