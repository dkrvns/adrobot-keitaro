import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.middleware.trustedhost import TrustedHostMiddleware

from adrobot.application.errors import (
    AppError,
    Conflict,
    Invalid,
    Missing,
    TrackerRejected,
    TrackerUnavailable,
)
from adrobot.config import Config
from adrobot.infrastructure.keitaro.client import KeitaroClient
from adrobot.infrastructure.operation_lock import LocalOperationLock
from adrobot.ioc import Resources
from adrobot.presentation.api import router
from adrobot.presentation.middleware import LocalWriteMiddleware

logger = logging.getLogger(__name__)
static = Path(__file__).parent / 'presentation' / 'static'
error_status = {
    Missing: status.HTTP_404_NOT_FOUND,
    Conflict: status.HTTP_409_CONFLICT,
    Invalid: status.HTTP_422_UNPROCESSABLE_CONTENT,
    TrackerRejected: status.HTTP_422_UNPROCESSABLE_CONTENT,
    TrackerUnavailable: status.HTTP_502_BAD_GATEWAY,
}


def create_app(
    config: Config | None = None,
    tracker_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = config or Config()  # type: ignore[call-arg]  # Environment settings
        engine = create_async_engine(
            str(settings.database_url),
            pool_size=5,
            max_overflow=5,
            pool_timeout=5,
            pool_pre_ping=True,
            connect_args={'connect_timeout': 5},
        )
        try:
            async with httpx.AsyncClient(
                base_url=f'{settings.keitaro_origin}/admin_api/v1/',
                headers={
                    'Api-Key': settings.keitaro_api_key.get_secret_value(),
                    'Accept': 'application/json',
                },
                timeout=httpx.Timeout(12, connect=5),
                limits=httpx.Limits(max_connections=12, max_keepalive_connections=6),
                transport=tracker_transport,
            ) as client:
                app.state.resources = Resources(
                    config=settings,
                    tracker=KeitaroClient(client, settings.keitaro_timezone),
                    sessions=async_sessionmaker(engine, expire_on_commit=False),
                    locks=LocalOperationLock(),
                )
                yield
        finally:
            await engine.dispose()

    app = FastAPI(title='Adrobot · Keitaro', version='0.1.0', lifespan=lifespan)
    app.add_middleware(LocalWriteMiddleware)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=['localhost', '127.0.0.1', 'testserver'],
    )

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            {'detail': str(exc)},
            status_code=error_status[type(exc)],
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            {
                'detail': [
                    {'loc': error['loc'], 'msg': error['msg'], 'type': error['type']}
                    for error in exc.errors()
                ],
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error('Database operation failed kind=%s', type(exc).__name__)
        return JSONResponse(
            {'detail': 'The local database is unavailable.'},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @app.get('/healthz', include_in_schema=False)
    async def healthz(request: Request) -> dict[str, str]:
        resources: Resources = request.app.state.resources
        async with resources.sessions() as session:
            await session.execute(text('SELECT 1 FROM stream_snapshots LIMIT 1'))
        return {'status': 'ok'}

    @app.get('/', include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(
            static / 'index.html',
            headers={
                'Cache-Control': 'no-cache',
                'Content-Security-Policy': (
                    "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
                    "form-action 'self'"
                ),
                'X-Content-Type-Options': 'nosniff',
                'Referrer-Policy': 'no-referrer',
            },
        )

    app.include_router(router)
    app.mount('/static', StaticFiles(directory=static), name='static')
    return app
