import json
import os
from typing import Dict, Any

def search_hotels(city: str, area: str = None, checkin: str = None, 
                  checkout: str = None, max_budget: float = None, 
                  rating_min: float = None) -> Dict[str, Any]:
    file_path = os.path.join(os.path.dirname(__file__), "..", "mocks", "hotels.json")
    
    with open(file_path, "r") as f:
        hotels = json.load(f)
    
    results = []
    for hotel in hotels:
        if hotel["city"].lower() != city.lower():
            continue
        
        if area and hotel.get("area", "").lower() != area.lower():
            continue
        
        if max_budget and hotel["price_per_night"] > max_budget:
            continue
        
        if rating_min and hotel.get("rating", 0) < rating_min:
            continue
        
        results.append(hotel)
    
    results.sort(key=lambda x: (-x.get("rating", 0), x["price_per_night"]))
    
    return {
        "count": len(results),
        "hotels": results[:5]
    }

