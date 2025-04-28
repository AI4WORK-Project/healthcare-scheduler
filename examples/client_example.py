import json
import requests


url = "http://0.0.0.0:5000/schedule"

instance_path = "instances/instance1.json"
with open(instance_path, "r") as f:
    instance = json.load(f)

response = requests.post(url, params={"time_limit": 10 * 60}, json=instance)

print("Status Code:", response.status_code)
if response.ok:
    print("Response JSON:", response.json())
