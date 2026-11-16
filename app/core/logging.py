import json
import logging
import time
import uuid
from datetime import datetime, timezone

from app.core.utils import client_ip


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": record.levelname,
                "logger": record.name, "message": record.getMessage()}
        for key in ("request_id", "method", "path", "status", "ms", "ip"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data)


def setup_logging(debug: bool = False) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)


access_log = logging.getLogger("app.access")


async def access_middleware(request, call_next):
    start, rid = time.perf_counter(), uuid.uuid4().hex[:12]
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    if not request.url.path.startswith("/static"):
        access_log.info("request", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                                          "status": response.status_code, "ip": client_ip(request),
                                          "ms": round((time.perf_counter() - start) * 1000)})
    return response
