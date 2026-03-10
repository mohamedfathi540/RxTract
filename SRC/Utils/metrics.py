
from prometheus_client import Counter, Histogram, generate_latest , CONTENT_TYPE_LATEST
from fastapi import Request, Response,FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import time

logger = logging.getLogger("uvicorn.error")

#Define metrics

REQUEST_COUNT = Counter(
    'http_request_count',
    'Total HTTP request count',
    ['method', 'endpoint', 'status_code']
)

REQUEST_LATENCY = Histogram(
    'http_request_latency',
    'HTTP request latency',
    ['method', 'endpoint']
)


#Middleware

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request,call_next) -> Response:

        #Record request start time
        request_start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("Unhandled error during request %s %s: %s", request.method, request.url.path, exc)
            response = Response(
                content='{"detail":"Internal server error"}',
                status_code=500,
                media_type="application/json",
            )
        end_point = request.url.path
        #Update metrics
        REQUEST_COUNT.labels(method= request.method, endpoint= end_point, status_code= response.status_code).inc()
        duration = time.time() - request_start_time
        REQUEST_LATENCY.labels(method= request.method, endpoint= end_point).observe(duration)
        
        return response

def setup_metrics(app: FastAPI):
    """
    Setup prometheus metrics middleware and endpoint
    """
    #Add Prometheus middleware
    app.add_middleware(PrometheusMiddleware)
    #Add metrics endpoint
    @app.get('/kfgndfkk4464_fubfd555',include_in_schema=False) 
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)