"""Production-readiness checks for G-18.

Default CI keeps these checks lightweight. Native Qdrant restart/persistence is
explicitly gated by SPEC_GRAG_PRODUCTION_READINESS because it starts a local
service process.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TRUE_VALUES = {"1", "true", "yes", "on"}


def _production_readiness_enabled() -> bool:
    return os.environ.get("SPEC_GRAG_PRODUCTION_READINESS", "").lower() in TRUE_VALUES


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_qdrant(url: str, *, timeout_sec: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/", timeout=1.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload if isinstance(payload, dict) else {}
        except Exception as exc:  # service is still booting
            last_error = exc
            time.sleep(0.2)
    raise AssertionError(f"Qdrant did not start at {url}: {last_error}")


def _start_qdrant(
    *,
    storage: Path,
    runtime: Path,
    http_port: int,
    grpc_port: int,
) -> subprocess.Popen[str]:
    binary = shutil.which("qdrant") or "/home/kazuki/.local/bin/qdrant"
    if not Path(binary).is_file():
        pytest.skip("native qdrant binary is not available")
    runtime.mkdir(parents=True, exist_ok=True)
    storage.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "QDRANT__SERVICE__HTTP_PORT": str(http_port),
            "QDRANT__SERVICE__GRPC_PORT": str(grpc_port),
            "QDRANT__STORAGE__STORAGE_PATH": storage.as_posix(),
        }
    )
    return subprocess.Popen(
        [binary, "--disable-telemetry"],
        cwd=runtime,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _stop_process(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


@pytest.mark.skipif(
    not _production_readiness_enabled(),
    reason="native Qdrant restart/persistence requires SPEC_GRAG_PRODUCTION_READINESS=1",
)
def test_t_r11_native_qdrant_persists_collection_across_restart(tmp_path: Path) -> None:
    qdrant_client = pytest.importorskip("qdrant_client")
    qdrant_models = pytest.importorskip("qdrant_client.models")

    storage = tmp_path / "qdrant-storage"
    runtime = tmp_path / "qdrant-runtime"
    http_port = _free_port()
    grpc_port = _free_port()
    url = f"http://127.0.0.1:{http_port}"
    collection = f"spec_grag_t_r11_{uuid.uuid4().hex}"

    process = _start_qdrant(
        storage=storage,
        runtime=runtime,
        http_port=http_port,
        grpc_port=grpc_port,
    )
    try:
        info = _wait_for_qdrant(url)
        assert info.get("version")
        client = qdrant_client.QdrantClient(url)
        client.recreate_collection(
            collection_name=collection,
            vectors_config={
                "dense": qdrant_models.VectorParams(
                    size=4,
                    distance=qdrant_models.Distance.COSINE,
                )
            },
            sparse_vectors_config={"sparse": qdrant_models.SparseVectorParams()},
        )
        client.upsert(
            collection_name=collection,
            points=[
                qdrant_models.PointStruct(
                    id=1,
                    vector={
                        "dense": [0.1, 0.2, 0.3, 0.4],
                        "sparse": qdrant_models.SparseVector(
                            indices=[1, 2],
                            values=[0.5, 0.6],
                        ),
                    },
                    payload={"source_section_id": "docs/spec/prod.md#persistence"},
                )
            ],
            wait=True,
        )
        assert client.count(collection).count == 1
    finally:
        _stop_process(process)

    restarted = _start_qdrant(
        storage=storage,
        runtime=runtime,
        http_port=http_port,
        grpc_port=grpc_port,
    )
    try:
        _wait_for_qdrant(url)
        client = qdrant_client.QdrantClient(url)
        collection_info = client.get_collection(collection)
        assert client.count(collection).count == 1
        vectors = getattr(collection_info.config.params, "vectors", None)
        sparse_vectors = getattr(collection_info.config.params, "sparse_vectors", None)
        assert vectors is not None
        assert sparse_vectors is not None
    finally:
        try:
            qdrant_client.QdrantClient(url).delete_collection(collection)
        except Exception:
            pass
        _stop_process(restarted)


def test_t_r15_readme_contains_production_readiness_runbook() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()

    for term in (
        "production readiness",
        "install",
        "start qdrant",
        "verify",
        "restart",
        "troubleshoot",
        "spec_grag_real_provider",
        "spec_grag_real_retrieval",
    ):
        assert term in readme


def test_t_r15_readme_fixes_production_readiness_report_sections() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    for term in (
        "Production Readiness Report Template",
        "実装済み",
        "`none` / `fake` profile で passing",
        "`local-service` / `real-smoke` で passing",
        "skipped / 未実行",
        "残 TODO",
        "証跡",
        "Do not report \"本運用可能\" while G-18",
    ):
        assert term in readme
