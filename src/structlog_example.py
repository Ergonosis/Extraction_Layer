import tomllib
from pathlib import Path

import orjson
import structlog
import structlog_gcp
from structlog.processors import JSONRenderer

pyproject_path = Path(__file__).resolve().parent.parent / 'pyproject.toml'
assert pyproject_path.is_file()
with pyproject_path.open('rb') as f:
    pyproject_cfg = tomllib.load(f)


processors = structlog_gcp.build_processors(
    service=pyproject_cfg['project']['name'], version=pyproject_cfg['project']['version']
)
processors = [JSONRenderer(serializer=orjson.dumps) if isinstance(x, JSONRenderer) else x for x in processors]
structlog.configure(processors=processors)

log = structlog.stdlib.get_logger()


structlog.contextvars.bind_contextvars(route='/api/v1/orders/{id}')
log.info('http_request_completed', event2='http_request_completed', latency_ms=84)
log.error('http_request_err', latency_ms=8004)
