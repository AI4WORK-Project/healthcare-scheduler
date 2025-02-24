# healthcare-scheduler

This repository contains the `healthcare` Python package and the REST API server (`server.py`). The application is containerized using Docker.

## Building the Docker Image
To build the Docker image, run:

```sh
docker build -t healthcare-app .
```

## Running the Container
To run the container and expose the application on port 5000, execute:

```sh
docker run -p 5000:5000 healthcare-app
```

## Accessing the Application
Once the container is running, you can access the application at:

```
http://0.0.0.0:5000
```

## Calling the API

### POST `/schedule`

This endpoint accepts a JSON payload representing a scheduling problem and returns the solution.

#### Request Parameters
- `time_limit`: (Optional, int) The time limit in seconds for the solver. If not provided, the solver will run without a time constraint.

#### Response
- **Success (200)**: If a solution is found, the response will contain a JSON object representing the solution.

- **Error (400)**: If no solution is found for the given problem, a message will be returned indicating that no solution was found.

- **Error (500)**: If an internal server error occurs, an error message will be returned.

## Running an example
To test the API, you can run the `client_example.py` script:

```sh
cd examples/
python client_example.py
```

This script sends a request to the running server and prints the response.
