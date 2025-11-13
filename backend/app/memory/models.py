from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profile"
    
    session_id: str = Field(primary_key=True)
    hotel_max_night: Optional[float] = None
    currency: Optional[str] = "INR"
    dietary: Optional[str] = None
    nonstop_only: Optional[bool] = None
    cabin: Optional[str] = None
    home_airport: Optional[str] = None
    interests: Optional[str] = None  # JSON string
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class SessionState(SQLModel, table=True):
    __tablename__ = "session_state"
    
    session_id: str = Field(primary_key=True)
    summary: Optional[str] = None
    turns_json: Optional[str] = None  # JSON string of last N messages
    updated_at: datetime = Field(default_factory=datetime.utcnow)

