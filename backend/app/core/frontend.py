"""Serve the built POS and its browser history routes from the API process."""
from pathlib import PurePosixPath

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class PosFrontend(StaticFiles):
    async def get_response(self, path: str, scope: Scope):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            wants_page = "text/html" in Headers(scope=scope).get("accept", "")
            if error.status_code != 404 or not wants_page or PurePosixPath(path).suffix:
                raise
            response = await super().get_response("index.html", scope)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response
