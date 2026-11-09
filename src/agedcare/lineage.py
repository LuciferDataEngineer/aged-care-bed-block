"""Emit OpenLineage run events to a local file and a small graph page."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openlineage.client import OpenLineageClient
from openlineage.client.run import Dataset, Job, Run, RunEvent, RunState
from openlineage.client.transport.file import FileConfig, FileTransport

from agedcare.paths import LINEAGE_DIR

PRODUCER = "https://github.com/LuciferDataEngineer/aged-care-bed-block"
NAMESPACE = "aged-care-bed-block"
EVENTS_PATH = LINEAGE_DIR / "events.jsonl"


def _client() -> OpenLineageClient:
    LINEAGE_DIR.mkdir(parents=True, exist_ok=True)
    transport = FileTransport(FileConfig(log_file_path=str(EVENTS_PATH), append=True))
    return OpenLineageClient(transport=transport)


def emit_job(name: str, inputs: list[str], outputs: list[str], run_id: str | None = None) -> str:
    run_id = run_id or str(uuid.uuid4())
    client = _client()
    now = datetime.now(timezone.utc).isoformat()
    job = Job(namespace=NAMESPACE, name=name)
    input_sets = [Dataset(namespace=NAMESPACE, name=item) for item in inputs]
    output_sets = [Dataset(namespace=NAMESPACE, name=item) for item in outputs]
    for state in (RunState.START, RunState.COMPLETE):
        client.emit(
            RunEvent(
                eventType=state,
                eventTime=now,
                run=Run(runId=run_id),
                job=job,
                producer=PRODUCER,
                inputs=input_sets,
                outputs=output_sets,
            )
        )
    write_graph_page()
    return run_id


def _read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text().strip()
    if not text:
        return []
    events = []
    # FileTransport appends JSON objects. They may be a JSON array, one object,
    # or concatenated objects / JSON lines.
    if text.startswith("["):
        payload = json.loads(text)
        return payload if isinstance(payload, list) else [payload]
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        obj, end = decoder.raw_decode(text, index)
        events.append(obj)
        index = end
    return events


def write_graph_page(path: Path | None = None) -> Path:
    path = path or (LINEAGE_DIR / "index.html")
    events = _read_events(EVENTS_PATH)
    edges: list[tuple[str, str]] = []
    seen = set()
    for event in events:
        if event.get("eventType") not in {"COMPLETE", "complete"}:
            continue
        job = event.get("job") or {}
        job_name = f"job:{job.get('name', 'unknown')}"
        for item in event.get("inputs") or []:
            source = f"data:{item.get('name')}"
            key = (source, job_name)
            if key not in seen:
                seen.add(key)
                edges.append(key)
        for item in event.get("outputs") or []:
            target = f"data:{item.get('name')}"
            key = (job_name, target)
            if key not in seen:
                seen.add(key)
                edges.append(key)
    nodes = []
    for source, target in edges:
        if source not in nodes:
            nodes.append(source)
        if target not in nodes:
            nodes.append(target)
    width = 980
    row_h = 36
    # Place inputs left, jobs middle, gold outputs right.
    inputs = [name for name in nodes if name.startswith("data:") and not name.startswith("data:gold")]
    jobs = [name for name in nodes if name.startswith("job:")]
    outputs = [name for name in nodes if name.startswith("data:gold") or (name.startswith("data:") and name not in inputs)]
    positions = {}
    for index, name in enumerate(inputs):
        positions[name] = (30, 50 + index * row_h)
    for index, name in enumerate(jobs):
        positions[name] = (380, 50 + index * max(row_h, 64))
    for index, name in enumerate(outputs):
        positions[name] = (700, 50 + index * row_h)
    height = 80 + max(len(inputs), len(jobs), len(outputs), 1) * row_h
    lines = []
    labels = []
    for source, target in edges:
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        lines.append(f'<line x1="{x1+160}" y1="{y1+12}" x2="{x2}" y2="{y2+12}" stroke="#4cc9f0" stroke-width="2"/>')
    for name, (x, y) in positions.items():
        colour = "#1b3a4b" if name.startswith("job:") else "#243044"
        labels.append(
            f'<rect x="{x}" y="{y}" width="250" height="26" rx="6" fill="{colour}" stroke="#4cc9f0"/>'
            f'<text x="{x+8}" y="{y+17}" fill="#e7eef7" font-size="11" font-family="sans-serif">{_escape(name)}</text>'
        )
    svg = (
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Lineage graph">'
        + "".join(lines)
        + "".join(labels)
        + "</svg>"
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Lineage — aged care bed block</title>
<style>
body {{ margin: 0; background: #0f1419; color: #e7eef7; font-family: Georgia, serif; }}
main {{ max-width: 1040px; margin: 0 auto; padding: 32px 20px 64px; }}
h1 {{ font-size: 1.8rem; }}
p {{ color: #c5d2e0; line-height: 1.5; }}
</style>
</head>
<body>
<main>
<h1>How the supply-gap figures are produced</h1>
<p>OpenLineage events written by this project. Each box is a dataset or a job. The stakeholder dashboard does not use this page.</p>
<p>{len(events)} events in <code>events.jsonl</code>.</p>
{svg}
</main>
</body>
</html>
"""
    path.write_text(html)
    return path


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


if __name__ == "__main__":
    write_graph_page()
