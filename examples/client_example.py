import json
import requests
import pathlib
import os


url = "http://0.0.0.0:5000/schedule"

examples_path = pathlib.Path(__file__).parent.resolve()
instance_path = os.path.join(examples_path, "instances/instance1.json")
with open(instance_path, "r") as f:
    instance = json.load(f)

response = requests.post(url, params={"time_limit": 10 * 60}, json=instance)

print("Status Code:", response.status_code)
if response.ok:
    print("Response JSON:", response.json())
