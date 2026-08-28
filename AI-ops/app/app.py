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

from flask import Flask, jsonify

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aiops-backend")


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
