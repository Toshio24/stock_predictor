from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import signals, news, tickers, search, health

settings = get_settings()
app = FastAPI(title="Signal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(signals.router, prefix="/api/v1")
app.include_router(news.router, prefix="/api/v1")
app.include_router(tickers.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
