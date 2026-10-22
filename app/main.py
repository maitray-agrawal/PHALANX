import logging

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
