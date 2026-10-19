import logging
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pymysql
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Database
from app.embeddings import Embedder
from app.llm import KimiClient, ModelError
from app.rag import RagService
from app.router import IntentRouter
from app.schemas import ChatRequest, ChatResponse
from app.sql_agent import SQLAgent

logger = logging.getLogger(__name__)
settings = get_settings()
database = Database(settings)
llm = KimiClient(settings)
rag = RagService(settings, Embedder(settings), llm)
router = IntentRouter(settings, llm)
agent = SQLAgent(settings, database, llm)
build_lock = threading.Lock()
build_state = {"status": "idle", "error": None}
static = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app):
    try:
        rag.load()
    except Exception:
        logger.exception("Index load failed")
        build_state.update(status="failed", error="索引无法加载或与配置不兼容，请重新构建。")
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=static), name="static")


def authorize(x_api_key: str = Header(default="")):
    if settings.service_api_key and not secrets.compare_digest(x_api_key, settings.service_api_key):
        raise HTTPException(401, "需要有效的 X-API-Key")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(static / "index.html")


@app.get("/api/health", dependencies=[Depends(authorize)])
def health():
    try:
        database.query("SELECT 1")
        connected = True
    except pymysql.MySQLError:
        connected = False
    return {"status": "ok" if connected else "degraded", "database": connected,
            "mode": "live" if settings.llm_ready else "demo" if settings.allow_demo else "unconfigured",
            "model": settings.kimi_model if settings.llm_ready else None,
            "embedding_provider": settings.embedding_provider, "index": rag.status(), "build": dict(build_state)}


@app.get("/api/overview", dependencies=[Depends(authorize)])
def overview():
    try:
        return database.overview()
    except pymysql.MySQLError as exc:
        raise HTTPException(503, "数据库连接或查询失败，请检查 .env 中的 MySQL 配置。") from exc


@app.get("/api/schema", dependencies=[Depends(authorize)])
def schema():
    try:
        return {"table": settings.mysql_table, "columns": database.schema()}
    except pymysql.MySQLError as exc:
        raise HTTPException(503, "数据库暂不可用") from exc


@app.post("/api/index/rebuild", status_code=202, dependencies=[Depends(authorize)])
def rebuild():
    if not build_lock.acquire(blocking=False):
        raise HTTPException(409, "索引正在构建，请等待完成。")
    build_state.update(status="building", error=None)

    def work():
        try:
            rag.build(database.jobs())
            build_state.update(status="ready", error=None)
        except Exception:
            logger.exception("Index build failed")
            build_state.update(status="failed", error="索引构建失败，请检查数据库、Embedding 配置和服务日志。")
        finally:
            build_lock.release()

    threading.Thread(target=work, daemon=True, name="index-builder").start()
    return {"status": "building"}


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(authorize)])
def chat(request: ChatRequest):
    question = request.question.strip()
    if len(question) < 2:
        raise HTTPException(422, "请输入至少两个有效字符")
    started = time.perf_counter()
    try:
        route, reason = router.route(question, request.mode)
        if route == "rag":
            answer, sources = rag.answer(question)
            data = {"answer": answer, "sources": sources}
        else:
            data = agent.run(question)
    except ModelError as exc:
        raise HTTPException(502, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except pymysql.MySQLError as exc:
        raise HTTPException(503, "数据库查询失败，请检查数据库连接与服务日志。") from exc
    return ChatResponse(route=route, route_reason=reason,
                        mode="live" if settings.llm_ready else "demo",
                        elapsed_ms=int((time.perf_counter() - started) * 1000), **data)
