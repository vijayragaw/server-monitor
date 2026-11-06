"""Read-only host metrics; run with uvicorn agent:create_app --factory."""
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse


def create_app():
    token_path = Path(os.environ.get('MONITOR_TOKEN_FILE', '/etc/server-monitor-agent/token'))
    token = token_path.read_text(encoding='utf-8').strip()
    if len(token) < 32 or len(token) > 512 or not token.isascii() or any(c.isspace() for c in token):
        raise RuntimeError('Token file must contain 32–512 non-whitespace ASCII characters')
    disk_path = os.environ.get('MONITOR_DISK_PATH', '/')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get('/v1/metrics')
    def metrics(authorization: str = Header(default='')):
        if not secrets.compare_digest(authorization.encode(), ('Bearer ' + token).encode()):
            raise HTTPException(401, 'Agent authentication required', headers={'WWW-Authenticate': 'Bearer'})
        try:
            disk = psutil.disk_usage(disk_path)
            data = {
                'version': 1,
                'collected_at': datetime.now(timezone.utc).isoformat(),
                'cpu_percent': psutil.cpu_percent(interval=0.25),
                'ram_percent': psutil.virtual_memory().percent,
                'disk_percent': disk.percent,
                'disk_free_bytes': disk.free,
                'disk_total_bytes': disk.total,
                'uptime_seconds': max(0, int(time.time() - psutil.boot_time())),
            }
        except (OSError, ValueError, psutil.Error):
            raise HTTPException(503, 'Host metrics unavailable')
        return JSONResponse(data, headers={'Cache-Control': 'no-store'})

    return app
