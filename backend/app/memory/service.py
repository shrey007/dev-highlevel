import os
import json
from typing import Optional, Dict, Any, List
from sqlmodel import Session, create_engine, SQLModel
from app.memory.models import UserProfile, SessionState
from datetime import datetime

class MemoryService:
    def __init__(self):
        db_path = os.getenv("SQLITE_PATH", "data/app.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}")
        SQLModel.metadata.create_all(self.engine)
    
    def get_profile(self, session_id: str) -> Dict[str, Any]:
        with Session(self.engine) as session:
            profile = session.get(UserProfile, session_id)
            if not profile:
                return {}
            return {
                "hotel_max_night": profile.hotel_max_night,
                "currency": profile.currency,
                "dietary": profile.dietary,
                "nonstop_only": profile.nonstop_only,
                "cabin": profile.cabin,
                "home_airport": profile.home_airport,
                "interests": json.loads(profile.interests) if profile.interests else []
            }
    
    def update_profile(self, session_id: str, updates: Dict[str, Any]) -> List[Dict[str, Any]]:
        diffs = []
        with Session(self.engine) as session:
            profile = session.get(UserProfile, session_id)
            if not profile:
                profile = UserProfile(session_id=session_id)
                session.add(profile)
            
            old_values = {
                "hotel_max_night": profile.hotel_max_night,
                "currency": profile.currency,
                "dietary": profile.dietary,
                "nonstop_only": profile.nonstop_only,
                "cabin": profile.cabin,
                "home_airport": profile.home_airport,
                "interests": json.loads(profile.interests) if profile.interests else []
            }
            
            for key, value in updates.items():
                if hasattr(profile, key):
                    old_val = old_values.get(key)
                    if old_val != value:
                        if key == "interests":
                            profile.interests = json.dumps(value) if value else None
                        else:
                            setattr(profile, key, value)
                        diffs.append({
                            "key": key,
                            "old_value": old_val,
                            "new_value": value
                        })
            
            profile.updated_at = datetime.utcnow()
            session.commit()
        
        return diffs
    
    def get_conversation_summary(self, session_id: str) -> Optional[str]:
        with Session(self.engine) as session:
            state = session.get(SessionState, session_id)
            return state.summary if state else None
    
    def get_last_turns(self, session_id: str) -> List[Dict[str, Any]]:
        with Session(self.engine) as session:
            state = session.get(SessionState, session_id)
            if not state or not state.turns_json:
                return []
            try:
                return json.loads(state.turns_json)
            except Exception:
                return []
    
    def update_conversation_summary(self, session_id: str, summary: str, turns: List[Dict]):
        with Session(self.engine) as session:
            state = session.get(SessionState, session_id)
            if not state:
                state = SessionState(session_id=session_id)
                session.add(state)
            
            state.summary = summary
            state.turns_json = json.dumps(turns[-10:])  # Keep last 10 turns
            state.updated_at = datetime.utcnow()
            session.commit()

