import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import (
    BodySizeLimitMiddleware,
    LogRedactionFilter,
    RateLimitMiddleware,
    RequestIdAndStructuredLoggingMiddleware,
    SecurityHeadersMiddleware,
    register_exception_handlers,
)
from app.api.routes import router
from app.infrastructure.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager; starts background reconciler when enabled."""
    reconcile_task = None
    if settings.reconciler_enabled:

        async def _reconcile_loop() -> None:
            from app.api.dependencies import get_reconciler_service

            loop_logger = logging.getLogger("phalanx.reconciler.loop")
            loop_logger.info(
                "Starting background reconciler loop (interval=%ds)",
                settings.reconcile_interval_seconds,
            )
            while True:
                try:
                    reconciler = get_reconciler_service()
                    reconciler.reconcile_all(force=False)
                except asyncio.CancelledError:
                    break
                except Exception as err:
                    loop_logger.warning("Error during background reconcile run: %s", err)
                await asyncio.sleep(settings.reconcile_interval_seconds)

        reconcile_task = asyncio.create_task(_reconcile_loop())

    yield

    if reconcile_task:
        reconcile_task.cancel()
        with suppress(asyncio.CancelledError):
            await reconcile_task


def create_app() -> FastAPI:
    """Application factory for PHALANX."""
    # Configure logging with redaction
    logging.basicConfig(level=logging.INFO)
    root_logger = logging.getLogger()
    root_logger.addFilter(LogRedactionFilter())

    app = FastAPI(
        title="PHALANX",
        description="Authorization & Governance Layer for Autonomous Financial Agents",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Security & observability middlewares
    app.add_middleware(RequestIdAndStructuredLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # Restrictive CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(router)

    from pathlib import Path

    dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
    if dist_dir.exists():
        from starlette.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static_frontend")

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
