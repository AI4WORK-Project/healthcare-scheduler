import json
import logging
import threading
from importlib.metadata import PackageNotFoundError, version

from apiflask import APIFlask, HTTPError, Schema
from apiflask.fields import Integer, String
from apiflask.validators import Range
from marshmallow import EXCLUDE
from flask import request, Response
from flask_cors import CORS
from marshmallow_dataclass import class_schema
from werkzeug.exceptions import BadRequest

from healthcare import Instance, Solution, NurseSchedulingFactory
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


def json_response(body: dict, status: int) -> Response:
    return Response(
        json.dumps(body, separators=(",", ":")),
        mimetype="application/json",
        status=status,
    )


@app.get("/health")
@app.output(HealthSchema)
@app.doc(summary="Check if the service is alive and reachable")
def health_check():
    logging.debug("Health check pinged.")
    return json_response({"status": "healthy", "version": __version__}, 200)


def validation_error_response(error: Exception) -> Response:
    if isinstance(error, KeyError):
        detail = f"Missing field {error}"
    else:
        detail = str(error) or type(error).__name__
    logging.error(f"Validation: {detail}")
    return json_response({"message": "Validation error", "detail": detail}, 422)


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
        instance: Instance = Instance.from_dict(request.json)
    except Exception as e:
        return validation_error_response(e)

    try:
        problem = instance.scheduling_problem()
    except Exception as e:
        # the fields are all there: a KeyError is an identifier that does not
        # exist, not a missing field
        if isinstance(e, KeyError):
            e = ValueError(f"Unknown identifier {e}")
        return validation_error_response(e)
    logging.info(f"Time limit: {time_limit}")

    try:
        factory = NurseSchedulingFactory(problem)
        model, nurse_view = factory.get_optimization_model()

        if model.solve(solver="ortools", time_limit=time_limit):
            logging.info(f"Solution penalty: {model.objective_value()}")
            solution = Solution.from_nurse_view(nurse_view.value(), factory)
        else:
            logging.info("No solution has been found for the given problem")
            return json_response(
                {"message": "No solution has been found for the given problem"}, 400
            )

    except Exception as e:
        logging.exception("Error while computing the schedule")
        return json_response({"message": str(e)}, 500)

    last_schedule_gantt_html.update(problem, solution)
    return Response(solution.to_json(), mimetype="application/json", status=200)


@app.get("/last_schedule_gantt")
@app.doc(
    summary="Visualize the last computed schedule",
    description="HTML table of the shifts assigned to each nurse on each day "
    "in the last schedule computed by /schedule.",
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


def start():
    logging.info("Starting...")
    from waitress import serve

    serve(app, host="0.0.0.0", port=5000)


if __name__ == "__main__":
    start()
