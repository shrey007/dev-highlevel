import json
import os
from typing import Dict, Any, List

def suggest_activities(city: str, interests: List[str] = None, 
                      days: int = None, budget_tier: str = None) -> Dict[str, Any]:
    file_path = os.path.join(os.path.dirname(__file__), "..", "mocks", "activities.json")
    
    with open(file_path, "r") as f:
        activities = json.load(f)
    
    results = []
    for activity in activities:
        if activity["city"].lower() != city.lower():
            continue
        
        if interests:
            activity_tags = [tag.lower() for tag in activity.get("tags", [])]
            if not any(interest.lower() in activity_tags for interest in interests):
                continue
        
        if budget_tier:
            activity_budget = activity.get("budget_tier", "medium")
            if activity_budget != budget_tier:
                continue
        
        results.append(activity)
    
    return {
        "count": len(results),
        "activities": results[:3]
    }

