import json
import requests
import pathlib
import os
from typing import Dict


URL = "http://0.0.0.0:5000/schedule"
INSTANCES_PATH = os.path.join(pathlib.Path(__file__).parent.resolve(), "instances")


def load_instance_json(instance_name: str) -> Dict:
    instance_path = os.path.join(INSTANCES_PATH, instance_name)
    with open(instance_path, "r") as f:
        instance = json.load(f)
    return instance


def test_invalid_instance():
    response = requests.post(URL, json="")
    assert response.status_code == 500
    assert len(response.json()["message"]) > 0


def test_instance_not_solvable():
    instance = load_instance_json("instance_not_solvable.json")
    response = requests.post(URL, json=instance)
    assert response.status_code == 400
    assert len(response.json()["message"]) > 0


def test_valid_instance():
    instance = load_instance_json("instance0.json")
    response = requests.post(URL, params={"time_limit": 10 * 60}, json=instance)
    assert response.status_code == 200
