"""Docker Compose helpers for the Postgres, Redpanda and Debezium stack."""

from __future__ import annotations

import os
import subprocess
import time

from agedcare.paths import ROOT


def compose_base() -> list[str]:
    docker = os.environ.get("DOCKER")
    if not docker:
        probe = subprocess.run(["docker", "info"], capture_output=True, text=True)
        docker = "docker" if probe.returncode == 0 else "sudo docker"
    return [*docker.split(), "compose", "-p", "agedcare", "-f", str(ROOT / "docker-compose.yml")]


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*compose_base(), *args], cwd=ROOT, text=True, capture_output=True, check=check)


def wait_for_streaming(timeout: int = 180) -> None:
    """Block until Debezium is tailing the Postgres slot."""
    deadline = time.time() + timeout
    last = ""
    markers = (
        "Starting streaming",
        "streaming requested",
        "Streaming requested",
        "Processing messages",
        "keep-alive",
    )
    while time.time() < deadline:
        logs = compose("logs", "debezium", "--no-color", check=False)
        last = (logs.stdout or "") + (logs.stderr or "")
        if any(marker in last for marker in markers):
            return
        time.sleep(3)
    tail = "\n".join(last.splitlines()[-40:])
    raise RuntimeError(f"Debezium did not reach streaming within {timeout}s.\n{tail}")


def main() -> None:
    wait_for_streaming()
    print("Debezium is streaming.")


if __name__ == "__main__":
    main()
