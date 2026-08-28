"""
AI-Ops Project - Phase 1
Simple Python backend exposing intentional endpoints used later to
generate observability incidents (metrics, logs, traces).

Endpoints:
    /        -> basic identity response
    /health  -> health check
    /slow    -> intentionally delayed response (~5s) to demonstrate latency
    /error   -> intentionally raises an error to generate error logs
"""

import time
import logging

from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aiops-backend")

# Define prometheus metrics matching the dashboard queries
HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total HTTP requests count',
    ['endpoint', 'http_status']
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['endpoint']
)

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    # Only track API endpoints, avoid infinite loops if metrics is hit, or track everything
    # Let's track everything since path-based routing is standard.
    endpoint = request.path
    status_code = str(response.status_code)
    
    # Increment total requests counter
    HTTP_REQUESTS_TOTAL.labels(endpoint=endpoint, http_status=status_code).inc()
    
    # Record duration in histogram
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        HTTP_REQUEST_DURATION_SECONDS.labels(endpoint=endpoint).observe(duration)
        
    return response


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}



@app.route("/")
def index():
    logger.info("GET / - root endpoint hit")
    return jsonify(message="AI-Ops Demo Application"), 200


@app.route("/health")
def health():
    logger.info("GET /health - health check")
    return jsonify(status="healthy"), 200


@app.route("/slow")
def slow():
    logger.info("GET /slow - simulating latency")
    time.sleep(5)
    return jsonify(message="This was a slow response"), 200


@app.route("/error")
def error():
    logger.error("GET /error - simulating an application error")
    raise Exception("Intentional error triggered at /error")


@app.errorhandler(Exception)
def handle_error(e):
    logger.exception("Unhandled exception: %s", e)
    return jsonify(error=str(e)), 500


if __name__ == "__main__":
    # Bind to all interfaces so it's reachable inside the Docker network
    app.run(host="0.0.0.0", port=8000)
