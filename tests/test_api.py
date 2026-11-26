import json
import logging
import os
import pathlib
import socket
import threading
import time
from typing import Dict

import pytest
import requests

import server
import service


URL = "http://0.0.0.0:5000/schedule"
HEALTH_URL = "http://0.0.0.0:5000/health"
GANTT_URL = "http://0.0.0.0:5000/last_schedule_gantt"
OPENAPI_URL = "http://0.0.0.0:5000/openapi.json"
INSTANCES_PATH = os.path.join(pathlib.Path(__file__).parent.resolve(), "instances")

logger = logging.getLogger("test_api")


@pytest.fixture(scope="module", autouse=True)
def start_server():
    logger.info("[Setup] starting server...")
    # do not run the tests against another server already listening on the port
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1", 5000)) != 0, "Port 5000 is already in use"
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()

    # wait until the server answers, failing if it could not start
    deadline = time.monotonic() + 30
    while True:
        assert server_thread.is_alive(), "The server could not start"
        try:
            requests.get(HEALTH_URL, timeout=1).raise_for_status()
            break
        except requests.RequestException:
            assert time.monotonic() < deadline, "The server did not start in time"
            time.sleep(0.2)

    # yield control to the test suite
    yield

    logger.info("[Teardown] stopping server...")


def load_instance_json(instance_name: str) -> Dict:
    instance_path = os.path.join(INSTANCES_PATH, instance_name)
    with open(instance_path, "r") as f:
        instance = json.load(f)
    return instance


def test_health():
    response = requests.get(HEALTH_URL)
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert len(response.json()["version"]) > 0


def test_invalid_instance():
    response = requests.post(URL, json="")
    assert response.status_code == 422
    assert response.json()["message"] == "Validation error"
    assert len(response.json()["detail"]) > 0


@pytest.mark.parametrize("data", ['{"horizon": 7,', "", " "])
def test_malformed_json(data):
    response = requests.post(
        URL, data=data, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["message"] == "Validation error"
    assert response.json()["detail"].startswith("Invalid JSON")


@pytest.mark.parametrize(
    "data, content_type",
    [(None, None), ("{}", "text/plain"), ("{}", "application/x-www-form-urlencoded")],
)
def test_body_not_json(data, content_type):
    # e.g. curl -d, which does not send the JSON Content-Type
    headers = {"Content-Type": content_type} if content_type else {}
    response = requests.post(URL, data=data, headers=headers)
    assert response.status_code == 422
    assert response.json()["message"] == "Validation error"


@pytest.mark.parametrize("time_limit", ["60s", "10.5", "0", "-3"])
def test_invalid_time_limit(time_limit: str):
    instance = load_instance_json("instance0.json")
    response = requests.post(URL, params={"time_limit": time_limit}, json=instance)
    assert response.status_code == 422
    assert response.json()["message"] == "Validation error"
    assert "time_limit" in response.json()["detail"]


def test_missing_field():
    instance = load_instance_json("instance0.json")
    del instance["horizon"]
    response = requests.post(URL, json=instance)
    assert response.status_code == 422
    assert response.json()["detail"] == "Missing field 'horizon'"


def test_invalid_field_value():
    instance = load_instance_json("instance0.json")
    instance["horizon"] = 0
    response = requests.post(URL, json=instance)
    assert response.status_code == 422
    assert response.json()["detail"] == "The horizon must be greater than 0"


@pytest.mark.parametrize(
    "requirements, detail",
    [
        ({}, "Cover role requirements must not be empty"),
        (None, "Cover role requirements must not be empty"),
    ],
)
def test_invalid_nested_field(requirements, detail: str):
    instance = load_instance_json("instance0.json")
    instance["cover"][0]["role_requirements"] = requirements
    response = requests.post(URL, json=instance)
    assert response.status_code == 422
    assert response.json()["detail"] == detail


def test_unknown_identifier(monkeypatch):
    def scheduling_problem(self):
        raise KeyError("night")

    monkeypatch.setattr(service.Instance, "scheduling_problem", scheduling_problem)
    response = server.app.test_client().post(
        "/schedule", json=load_instance_json("instance0.json")
    )
    assert response.status_code == 422
    assert response.json["detail"] == "Unknown identifier 'night'"


def test_unknown_fields():
    instance = load_instance_json("instance0.json")
    assert service.unknown_fields(instance) == []

    instance["blocked_weekday"] = []
    instance["staff"][1]["max_shift"] = []
    instance["cover"][0]["role_requirements"]["nurse"] = 1
    instance["shift_on_requests"][0]["wieght"] = 1
    instance["shift_off_requests"][0]["wieght"] = 1
    assert service.unknown_fields(instance) == [
        "blocked_weekday",
        "shift_off_requests.0.wieght",
        "shift_on_requests.0.wieght",
        "staff.1.max_shift",
    ]


def test_openapi_ignores_unknown_fields():
    # each dataclass has a single schema, which does not reject unknown fields
    schemas = requests.get(OPENAPI_URL).json()["components"]["schemas"]
    assert "ShiftRequest1" not in schemas
    for name in ("Instance", "ShiftRequest", "Staff", "Cover"):
        assert "additionalProperties" not in schemas[name]


def test_instance_not_solvable():
    instance = load_instance_json("instance_not_solvable.json")
    response = requests.post(URL, json=instance)
    assert response.status_code == 400
    assert len(response.json()["message"]) > 0


def test_valid_instance():
    instance = load_instance_json("instance0.json")
    response = requests.post(URL, params={"time_limit": 10 * 60}, json=instance)
    assert response.status_code == 200

    body = response.json()
    assert "shift_schedule" in body
    assert "underallocations" in body

    response = requests.get(GANTT_URL)
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    for employee in body["shift_schedule"]:
        assert employee["employee_id"] in response.text


def test_gantt_render_error(monkeypatch):
    def render(problem, solution):
        raise RuntimeError("cannot render")

    gantt = server.LastScheduleGantt(render)
    monkeypatch.setattr(server, "last_schedule_gantt_html", gantt)
    client = server.app.test_client()

    response = client.get("/last_schedule_gantt")
    assert response.status_code == 404

    gantt.update(None, None)
    response = client.get("/last_schedule_gantt")
    assert response.status_code == 500
    assert response.json["message"] == "The last schedule could not be visualized"
