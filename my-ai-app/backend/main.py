import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api import agent, chat, document, goals, image_chat, knowledge, memories, ocr, personality, progress, proactive, relationship, research, screen, self_learning, tools, websocket
from agent.runtime import agent_loop, output_bus, proactive_scheduler
from services.health_service import check_health
from core.database import DatabaseUnavailable
from core.migrations import run_migrations

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="VTuber API")


@app.exception_handler(DatabaseUnavailable)
async def database_error_handler(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Không thể kết nối hoặc lưu dữ liệu MySQL. Hãy kiểm tra MySQL rồi thử lại."})


@app.on_event("startup")
async def startup_event():
    migration_report = await asyncio.to_thread(run_migrations)
    app.state.migration_report = migration_report
    if not migration_report.get("ok"):
        if migration_report.get("code") == "migration_failed":
            raise RuntimeError(f"Database migration failed: {migration_report.get('reason')}")
        logger.warning("[database] migration pending: %s", migration_report.get("reason"))
    agent_loop.start()
    proactive_scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    await proactive_scheduler.stop()
    await agent_loop.stop()
    output_bus.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chat.router, prefix="/api")
app.include_router(ocr.router, prefix="/api")
app.include_router(image_chat.router, prefix="/api")
app.include_router(memories.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(websocket.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(screen.router, prefix="/api")
app.include_router(document.router, prefix="/api")
app.include_router(goals.router, prefix="/api")
app.include_router(research.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(progress.router, prefix="/api")
app.include_router(proactive.router, prefix="/api")
app.include_router(self_learning.router, prefix="/api")
app.include_router(relationship.router, prefix="/api")
app.include_router(personality.router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Server AI ready!"}


@app.get("/health")
async def health_check():
    report = await check_health()
    return JSONResponse(
        content=report,
        status_code=200 if report["status"] == "ok" else 503,
    )
