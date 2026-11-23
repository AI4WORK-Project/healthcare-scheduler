# Human-Aware Task Planner – Nurse Rostering

Repository: `healthcare-scheduler`

The Nurse Rostering variant of the AI4Work Human-Aware Task Planner computes nurse rosters: the assignment of shifts to nurses over a planning horizon of several weeks.
It is exposed as a REST service (`server.py`) on top of the `healthcare` Python package, and it is distributed as a Docker image.

The roster satisfies hard constraints and minimizes the weighted penalty of the violated soft constraints:

- **Hard constraints**: shift cover for each role, shift rotation (shifts that cannot follow each other), maximum shifts and working minutes (total and weekly), minimum and maximum consecutive shifts, minimum consecutive days off, maximum worked weekends, days off, blocked weekdays.
- **Soft constraints**: shift on/off requests of the nurses, minimum working minutes (total and weekly).
- **Human-aware workload**: each shift has a workload weight and each nurse a current workload level; the accumulated workload of each nurse over the horizon is kept below a workload threshold, and nurses whose workload level already reaches it are not assigned any shift.

The optimization model is written with [CPMpy](https://github.com/CPMpy/cpmpy) and solved with the OR-Tools CP-SAT solver.

## Quick start

Run the published Docker image:

```sh
docker run -p 5000:5000 ghcr.io/ai4work-project/healthcare-scheduler:latest
```

Or build the image from source:

```sh
docker build -t healthcare-scheduler .
docker run -p 5000:5000 healthcare-scheduler
```

Or install the package and run the server directly (Python 3.10 or later; the image and CI use 3.12):

```sh
pip install .
python server.py
```

The service listens on port 5000. The interactive API documentation is available at <http://localhost:5000/docs>.

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/schedule` | Computes a roster for the given problem |
| `GET` | `/last_schedule_gantt` | HTML visualization of the last computed roster |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Interactive API documentation (Swagger UI) |
| `GET` | `/openapi.json` | OpenAPI specification |

### POST `/schedule`

Computes a roster for the problem described by the JSON request body.

#### Query parameters

- `time_limit` (optional, int): time limit in seconds for the solver. If not provided, the solver runs without a time limit.

#### Request body

A JSON object describing the problem: horizon, shifts, staff, days off, shift requests, cover requirements and workload threshold.
See:

- [instance1_description.md](examples/instances/instance1_description.md): description of every field, using `instance1.json` as an example;
- [instance1.json](examples/instances/instance1.json) and [instance1_annotated.json](examples/instances/instance1_annotated.json): example request;
- [schema.json](examples/instances/schema.json): JSON schema of the request.

Unknown fields are ignored.

#### Responses

- **200**: the roster (`shift_schedule`: the shift of each nurse on each day, `-` for a day off) and the underallocations of the minimum working minutes (`underallocations`). See [instance1_solution.json](examples/instances/instance1_solution.json).
- **400**: no solution has been found: `{"message": "No solution has been found for the given problem"}`.
- **422**: the input is not valid, including a body that is not valid JSON: `{"message": "Validation error", "detail": "<reason>"}`.
- **500**: internal server error: `{"message": "<reason>"}`.

### GET `/last_schedule_gantt`

Returns an HTML table with the shifts assigned to each nurse on each day in the last roster computed by `/schedule`.

- **200**: the HTML page, to be viewed in a browser.
- **404**: no roster has been computed yet: `{"message": "Gantt html not found"}`.

### GET `/health`

Returns `{"status": "healthy", "version": "<version>"}` if the service is up and reachable.
The Docker image uses it as its `HEALTHCHECK`.

## Examples

With the server running:

```sh
# compute a roster
curl -X POST --json @examples/instances/instance1.json "http://localhost:5000/schedule?time_limit=60"

# save the visualization of the last roster and open it in a browser
curl "http://localhost:5000/last_schedule_gantt" > roster.html
```

The [examples](examples) folder also contains:

- [client_example.py](examples/client_example.py): sends a request to the server and prints the response;
- [client_example_with_visualization.py](examples/client_example_with_visualization.py): sends a request and opens the visualization of the roster;
- [example.py](examples/example.py): solves an instance using the `healthcare` package directly, without the server.

The client examples need `requests`: `pip install .[example]`.

## Development

```sh
pip install .[test]
python -m pytest tests
```

The API tests start the server on port 5000 themselves, so the port must be free.

The CI runs the tests on every pull request. Every push to `main` publishes the Docker image `ghcr.io/ai4work-project/healthcare-scheduler:latest`, and every tag `vX.Y.Z` publishes `ghcr.io/ai4work-project/healthcare-scheduler:X.Y.Z`.

## License

Copyright (c) 2025-2026 Fondazione Bruno Kessler and other contributors.

This software is distributed under the [Eclipse Public License 2.0](LICENSE) (`EPL-2.0`). See [NOTICE](NOTICE).

## Acknowledgements

This software has been developed within the AI4Work project, which has received funding from the European Union's Horizon Europe research and innovation programme under grant agreement No 101135990.
