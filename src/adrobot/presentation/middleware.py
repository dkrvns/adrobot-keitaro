from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class LocalWriteMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope['method'] not in {
            'POST',
            'PATCH',
            'PUT',
            'DELETE',
        }:
            await self._app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get('origin')
        if origin and origin != f'{scope["scheme"]}://{headers.get("host")}':
            await JSONResponse(
                {'detail': 'Cross-origin write was rejected.'},
                status_code=403,
            )(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > 16 * 1024:
                await JSONResponse(
                    {'detail': 'Request body is too large.'},
                    status_code=413,
                )(scope, receive, send)
                return
            if not message.get('more_body'):
                break

        received = False

        async def buffered_receive() -> Message:
            nonlocal received
            if received:
                return await receive()
            received = True
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}

        await self._app(scope, buffered_receive, send)
