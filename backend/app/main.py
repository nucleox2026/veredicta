from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import Base, engine
from . import models  # registra os modelos no metadata do SQLAlchemy
from .routers.searches import router as searches_router
from .routers.processes import router as processes_router
from .settings import get_settings

settings = get_settings()
from .routers import internal_monitor as internal_monitor_router_module

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.on_event("startup")
def startup():
    # Conveniente para o MVP. Em produção madura, substituir por Alembic migrations.
    Base.metadata.create_all(bind=engine)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


app.include_router(searches_router)
app.include_router(processes_router)

app.include_router(internal_monitor_router_module.router)
