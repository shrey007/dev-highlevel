import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.utils import parse_date_flexible, date_in_range

def search_flights(from_city: str, to_city: str, depart_date: str, 
                   return_date: str = None, stops: int = None, 
                   max_price: float = None, cabin: str = None) -> Dict[str, Any]:
    file_path = os.path.join(os.path.dirname(__file__), "..", "mocks", "flights.json")
    
    with open(file_path, "r") as f:
        flights = json.load(f)
    
    results = []
    for flight in flights:
        if flight["from"].lower() != from_city.lower() or flight["to"].lower() != to_city.lower():
            continue
        
        if stops is not None and flight["stops"] != stops:
            continue
        
        if max_price and flight["price"] > max_price:
            continue
        
        if cabin and flight.get("cabin") != cabin:
            continue
        
        if depart_date and flight.get("depart_date"):
            flight_date = flight.get("depart_date", "")
            user_date = parse_date_flexible(depart_date) or depart_date.strip()
            
            if flight_date and user_date:
                if user_date != flight_date:
                    continue
        
        results.append(flight)
    
    results.sort(key=lambda x: x["price"])
    
    return {
        "count": len(results),
        "flights": results[:5]
    }

