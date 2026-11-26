import json
import logging
import os
import signal
import sys
import threading
from importlib.metadata import PackageNotFoundError, version

from apiflask import APIFlask, HTTPError, Schema
from apiflask.fields import Integer, String
from apiflask.validators import Range
from flask import Response, request
from flask_cors import CORS
from marshmallow import EXCLUDE
from marshmallow_dataclass import class_schema
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

import kafka_worker
import service
from healthcare import Instance, Solution
from healthcare.visualize import visualize

logging.basicConfig(level=logging.INFO)

try:
    __version__ = version("healthcare")
except PackageNotFoundError:
    __version__ = "unknown"

app = APIFlask(
    "NurseRostering-API",
    title="Human-Aware Task Planner – Nurse Rostering",
    version=__version__,
)
app.openapi_version = "3.0.2"
CORS(app)


class DocSchema(Schema):
    """The schemas only document the API: the input is parsed and validated by
    the dataclasses, so validation is disabled and unknown fields are ignored."""

    class Meta:
        unknown = EXCLUDE


InstanceSchema = class_schema(Instance, base_schema=DocSchema)
SolutionSchema = class_schema(Solution, base_schema=DocSchema)


class ScheduleQuerySchema(Schema):
    time_limit = Integer(
        required=False,
        validate=Range(min=1),
        metadata={
            "description": "Time limit in seconds for the solver. "
            "If not provided, the solver runs without a time limit."
        },
    )


class HealthSchema(Schema):
    status = String(metadata={"example": "healthy"})
    version = String(metadata={"example": __version__})
    kafka = String(
        metadata={
            "example": "running",
            "description": "running, connecting or stopped, only if the Kafka consumer "
            "is enabled",
        }
    )


ERROR_RESPONSES = {
    400: "No solution has been found for the given problem",
    422: 'Invalid input: {"message": "Validation error", "detail": "..."}',
    500: 'Internal server error: {"message": "..."}',
}


class LastScheduleGantt:
    """Last computed schedule, kept in memory and rendered as an HTML page
    only when it is requested."""

    def __init__(self, render):
        self._render = render
        self._lock = threading.Lock()
        self._schedule = None
        self._html = None

    def update(self, *schedule):
        with self._lock:
            self._schedule = schedule
            self._html = None

    def html(self):
        """Return the HTML page, None if no schedule has been computed yet.

        Raise the rendering error if the page cannot be rendered."""
        with self._lock:
            if self._html is None and self._schedule is not None:
                self._html = self._render(*self._schedule)
            return self._html


def render_roster(problem, solution) -> str:
    return visualize(problem, solution).to_html(doctype_html=True)


last_schedule_gantt_html = LastScheduleGantt(render_roster)

# Kafka consumer and its thread, if it has been started
kafka_consumer: kafka_worker.KafkaWorker | None = None
kafka_thread: threading.Thread | None = None

# called with the exit code when the Kafka consumer stops on its own (replaced
# in the tests)
exit_process = os._exit


def json_response(body: dict, status: int) -> Response:
    return Response(
        json.dumps(body, separators=(",", ":")),
        mimetype="application/json",
        status=status,
    )


def result_response(result: service.ScheduleResult) -> Response:
    return Response(result.body, mimetype="application/json", status=result.status)


@app.get("/health")
@app.output(HealthSchema)
@app.doc(
    summary="Check if the service is alive and reachable",
    responses={503: "The Kafka consumer is not connected to the broker or has stopped"},
)
def health_check():
    logging.debug("Health check pinged.")
    body = {"status": "healthy", "version": __version__}
    if kafka_thread is not None:
        if not kafka_thread.is_alive():
            body.update(status="unhealthy", kafka="stopped")
            return json_response(body, 503)
        if kafka_consumer is None or not kafka_consumer.connected.is_set():
            body.update(status="unhealthy", kafka="connecting")
            return json_response(body, 503)
        body["kafka"] = "running"
    return json_response(body, 200)


def validation_error_response(error: Exception) -> Response:
    return result_response(service.validation_error(error))


@app.errorhandler(BadRequest)
def bad_request(error: BadRequest) -> Response:
    # the request parser attaches the decoding error to the 400 it raises for a
    # body that is not valid JSON: report it as invalid input, as documented
    decoding_error = getattr(error, "exc", None)
    if isinstance(decoding_error, (json.JSONDecodeError, UnicodeDecodeError)):
        return validation_error_response(ValueError(f"Invalid JSON: {decoding_error}"))
    return app.error_callback(HTTPError(400, message=error.name))


def time_limit_arg() -> int | None:
    """Return the time_limit query parameter, None if it is not given.

    Raise ValueError if it is not a positive integer."""
    value = request.args.get("time_limit")
    if value is None:
        return None
    try:
        time_limit = int(value)
    except ValueError:
        time_limit = 0
    if time_limit <= 0:
        raise ValueError(f"time_limit must be a positive integer, got '{value}'")
    return time_limit


@app.post("/schedule")
@app.input(ScheduleQuerySchema, location="query", validation=False)
@app.input(InstanceSchema, location="json", validation=False)
@app.output(SolutionSchema)
@app.doc(summary="Compute a nurse roster", responses=ERROR_RESPONSES)
def schedule(query_data, json_data):
    logging.info("Request received!")

    try:
        time_limit = time_limit_arg()
        data = request.json
    except (ValueError, UnsupportedMediaType) as e:
        return validation_error_response(e)
    except BadRequest:
        # the request parser decodes the body before, and leaves out only an
        # empty one: report it as invalid input, as documented
        return validation_error_response(ValueError("Invalid JSON: empty body"))

    result = service.schedule(data, time_limit)
    if result.schedule is not None:
        last_schedule_gantt_html.update(*result.schedule)
    return result_response(result)


@app.get("/last_schedule_gantt")
@app.doc(
    summary="Visualize the last computed schedule",
    description="HTML table of the shifts assigned to each nurse on each day "
    "in the last schedule computed by /schedule or for a Kafka request.",
    responses={
        200: {"description": "HTML visualization", "content": {"text/html": {}}},
        404: "No schedule has been computed yet",
        500: "The last schedule could not be visualized",
    },
)
def last_schedule_gantt():
    logging.info("Received request for the last generated schedule plot html.")
    try:
        html = last_schedule_gantt_html.html()
    except Exception:
        logging.exception("Could not visualize the last schedule")
        return json_response(
            {"message": "The last schedule could not be visualized"}, 500
        )
    if html is None:
        return json_response({"message": "Gantt html not found"}, 404)
    return Response(html, mimetype="text/html")


def start_kafka_worker(config: kafka_worker.KafkaConfig) -> kafka_worker.KafkaWorker:
    """Start the Kafka consumer in a thread: the schedules it computes are
    shown by /last_schedule_gantt too.

    If the consumer stops on its own, the process exits, so that the container
    can be restarted: the Kafka requests would not be served otherwise."""
    global kafka_consumer, kafka_thread
    worker = kafka_worker.KafkaWorker(
        config, on_schedule=last_schedule_gantt_html.update
    )

    def run():
        try:
            worker.run()
        except Exception:
            logging.exception("The Kafka consumer has failed")
        if not worker.stopping:
            logging.critical("The Kafka consumer has stopped: exiting")
            exit_process(1)

    kafka_consumer = worker
    kafka_thread = threading.Thread(target=run, name="kafka-worker", daemon=True)
    kafka_thread.start()
    return worker


def start():
    """Start the server, and the Kafka consumer if KAFKA_BOOTSTRAP_SERVER is set.

    Raise ValueError if the Kafka configuration is not valid."""
    logging.info("Starting...")
    from waitress import serve

    config = kafka_worker.KafkaConfig.from_env()
    worker = start_kafka_worker(config) if config is not None else None

    if threading.current_thread() is threading.main_thread():
        # stop as on Ctrl+C, so that the Kafka consumer leaves its group
        signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    try:
        serve(app, host="0.0.0.0", port=5000)
    finally:
        if worker is not None and kafka_thread is not None:
            logging.info("Stopping the Kafka consumer...")
            worker.stop()
            kafka_thread.join(10)


if __name__ == "__main__":
    start()
