import json
import logging
from flask import Flask, request, Response
from healthcare import Instance, Solution, NurseSchedulingFactory
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)

app = Flask("NurseRostering-API")
CORS(app)


def json_response(body: dict, status: int) -> Response:
    return Response(
        json.dumps(body, separators=(",", ":")),
        mimetype="application/json",
        status=status,
    )


@app.route("/health", methods=["GET"])
def health_check():
    """
    Check if the service is alive and reachable.
    """
    logging.info("Health check pinged.")
    return json_response({"status": "healthy"}, 200)


@app.route("/schedule", methods=["POST"])
def schedule():
    try:
        logging.info("Request received!")

        instance: Instance = Instance.from_dict(request.json)
        problem = instance.scheduling_problem()

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
