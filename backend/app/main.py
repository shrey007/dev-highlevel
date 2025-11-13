from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

from app.routes import chat

load_dotenv()

app = FastAPI(title="Travel Agent API")

origins = os.getenv("CORS_ORIGINS", "http://localhost:5176").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok"}

