import json
import logging
from importlib.metadata import PackageNotFoundError, version

from apiflask import APIFlask, Schema
from apiflask.fields import Integer, String
from marshmallow import EXCLUDE
from flask import request, Response
from flask_cors import CORS
from marshmallow_dataclass import class_schema

from healthcare import Instance, Solution, NurseSchedulingFactory

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


@app.post("/schedule")
@app.input(ScheduleQuerySchema, location="query", validation=False)
@app.input(InstanceSchema, location="json", validation=False)
@app.output(SolutionSchema)
@app.doc(summary="Compute a nurse roster", responses=ERROR_RESPONSES)
def schedule(query_data, json_data):
    logging.info("Request received!")

    try:
        instance: Instance = Instance.from_dict(request.json)
        problem = instance.scheduling_problem()
    except Exception as e:
        return validation_error_response(e)

    try:
        factory = NurseSchedulingFactory(problem)
        model, nurse_view = factory.get_optimization_model()

        time_limit = request.args.get("time_limit", None, type=int)
        logging.info(f"Time limit: {time_limit}")

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

    return Response(solution.to_json(), mimetype="application/json", status=200)


if __name__ == "__main__":
    from waitress import serve

    serve(app, host="0.0.0.0", port=5000)
