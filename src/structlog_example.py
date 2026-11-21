import tomllib
from pathlib import Path

import structlog
import structlog_gcp

pyproject_path = Path(__file__).resolve().parent.parent / 'pyproject.toml'
assert pyproject_path.is_file()
with pyproject_path.open('rb') as f:
    pyproject_cfg = tomllib.load(f)


structlog.configure(
    processors=structlog_gcp.build_processors(
        service=pyproject_cfg['project']['name'], version=pyproject_cfg['project']['version']
    )
)

log = structlog.stdlib.get_logger()


structlog.contextvars.bind_contextvars(route='/api/v1/orders/{id}')
log.info('http_request_completed', event2='http_request_completed', latency_ms=84)
log.error('http_request_err', latency_ms=8004)
