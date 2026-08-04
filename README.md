# VPP Dispatch

**vpp-dispatch** is a Python service for solving Virtual Power Plant (VPP) dispatch optimization problems. It models a fleet of distributed energy resources (e.g. batteries, generation, flexible load) as an optimization problem using [Pyomo](https://www.pyomo.org/) and solves it with the [HiGHS](https://highs.dev/) solver, exposing the results through a [FastAPI](https://fastapi.tiangolo.com/) web API.

> This project is an early-stage scaffold. This README documents what's set up so far — update the sections below as the model and API take shape.

## Tech Stack

- **Language:** Python 3.13+
- **API:** FastAPI (served via Uvicorn)
- **Optimization:** Pyomo, solved with the HiGHS solver (`highspy`)
- **Validation:** Pydantic
- **Dependency management:** [uv](https://docs.astral.sh/uv/)
- **Testing / linting:** pytest, ruff
- **Containerization:** Docker (multi-stage build)
- **Deployment:** Kubernetes manifests under `infra/k8s`

## Project Structure

```
vppdispatch/
├── src/
│   └── vpp_dispatch/     # Application package (FastAPI app, dispatch model, etc.)
├── tests/                # Test suite (pytest)
├── infra/
│   └── k8s/              # Kubernetes deployment manifests
├── Dockerfile            # Multi-stage build → uvicorn vpp_dispatch.api:app
├── main.py               # Entry-point script
├── pyproject.toml        # Project metadata & dependencies
└── uv.lock                # Locked dependency versions
```

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed

### Install dependencies

```bash
git clone https://github.com/MainakDanOpRes/vppdispatch.git
cd vppdispatch
uv sync
```

This installs both runtime and dev dependencies (FastAPI, Pyomo, HiGHS, pytest, ruff, etc.) into a local virtual environment.

### Run the API locally

```bash
uv run uvicorn vpp_dispatch.api:app --reload --port 8000
```

The API will be available at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`.

### Run tests

```bash
uv run pytest
```

### Lint

```bash
uv run ruff check .
```

## Running with Docker

Build and run the containerized service:

```bash
docker build -t vpp-dispatch .
docker run -p 8000:8000 vpp-dispatch
```

The image uses a multi-stage build to keep the runtime image lean, and serves the FastAPI app via Uvicorn on port `8000`.

## Deployment

Kubernetes manifests for deploying the service live in [`infra/k8s`](./infra/k8s). Update image references and environment-specific config there before applying to a cluster:

```bash
kubectl apply -f infra/k8s/
```

## Configuration

The project depends on `python-dotenv`, so runtime configuration can be supplied via a `.env` file in the project root (not committed to version control). Document required environment variables here as they're introduced.

## Contributing

1. Fork the repo and create a feature branch.
2. Make your changes, adding or updating tests as needed.
3. Run `uv run ruff check .` and `uv run pytest` before opening a PR.
4. Open a pull request describing your changes.

## License

No license has been specified yet. Add a `LICENSE` file to clarify how others may use this code.
