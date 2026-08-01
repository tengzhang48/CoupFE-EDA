"""Retained rank-sweep measurements for the distributed FieldSplit solve.

Each measurement launches exactly one fixed-size
``eda_multiphysics.etv_distributed_fs`` solve and accepts exactly one
``SCALEFS <ndof> <ranks> <wall> <last_ksp_iterations>`` record. The
command-line interface
retains a JSON summary, the two streams from every launch, and sanitized
environment/source provenance.  It is a measurement harness, not by itself a
performance qualification.

Example (the output directory must not already exist)::

    OMP_NUM_THREADS=1 python -m eda_multiphysics.scaling_bench \
      --n 120 --ranks 1,2,4 --repeats 3 --oversubscribe \
      --output-dir /tmp/coupfe-eda-scaling-120

Oversubscription is useful only as a functional smoke exercise.  Use physical
cores, a stable allocation, repeated runs, and the retained records before
making a scaling statement.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
DRIVER_MODULE = "eda_multiphysics.etv_distributed_fs"
METRIC_GRAIN = "one fixed-size coupled solve per rank count and repeat"
SOLVER_CONFIGURATION = {
    "nonlinear": {
        "maximum_steps": 8,
        "convergence_metric": "maximum absolute solution increment",
        "convergence_tolerance": 1e-11,
    },
    "linear": {
        "ksp": "gmres",
        "relative_tolerance": 1e-10,
        "maximum_iterations": 500,
        "preconditioner": "additive fieldsplit with GAMG per scalar field",
    },
}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SAFE_ENVIRONMENT_KEYS = (
    "OMP_NUM_THREADS",
    "OMP_PROC_BIND",
    "OMP_PLACES",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "SLURM_CPUS_PER_TASK",
)
_FORCED_SINGLE_THREAD_KEYS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL)"
    r"[A-Z0-9_]*)\s*=\s*([^\s]+)"
)
_GITHUB_TOKEN = re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")
_OPENAI_TOKEN = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
_URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+:[^/@\s]+@")


class BenchmarkRunError(RuntimeError):
    """A launch or its machine-readable metadata failed validation."""

    def __init__(self, message: str, record: dict[str, Any]):
        super().__init__(message)
        self.record = record


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _expected_ndof(n: int) -> int:
    """Two fields on the ``(n + 1) x (n + 1)`` structured node grid."""
    return 2 * (n + 1) ** 2


@lru_cache(maxsize=1)
def _redaction_paths() -> dict[str, str]:
    paths = {
        str(_REPOSITORY_ROOT): "[repository]",
        str(Path.home()): "[home]",
    }
    hostname = platform.node().strip()
    if hostname and len(hostname) >= 3:
        paths[hostname] = "[host]"
    try:
        spec = importlib.util.find_spec("coupfe")
    except (ImportError, AttributeError, ValueError):
        spec = None
    if spec is not None and spec.origin is not None:
        for parent in Path(spec.origin).resolve().parents:
            if (parent / ".git").exists():
                paths[str(parent)] = "[coupfe-core-source]"
                break
    return paths


def _redact(text: str | bytes | None) -> str:
    """Remove known local paths and common credential forms from retained text."""
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode(errors="replace")
    replacements = _redaction_paths()
    for source in sorted(replacements, key=len, reverse=True):
        if source and source != "/":
            text = text.replace(source, replacements[source])
    text = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}=[redacted]", text)
    text = _GITHUB_TOKEN.sub("[redacted-github-token]", text)
    text = _OPENAI_TOKEN.sub("[redacted-api-token]", text)
    return _URL_CREDENTIALS.sub(r"\1[redacted]@", text)


def _write_text(
    path: Path, text: str, *, record_path: str | None = None
) -> dict[str, Any]:
    clean = _redact(text)
    path.write_text(clean, encoding="utf-8")
    return {
        "path": record_path or path.name,
        "sha256": hashlib.sha256(clean.encode("utf-8")).hexdigest(),
        "bytes": len(clean.encode("utf-8")),
    }


def _write_json(path: Path, value: Any) -> None:
    serialized = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(_redact(serialized), encoding="utf-8")


def _command_output(command: list[str], timeout: int = 15) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return _redact(result.stdout.strip() or result.stderr.strip())


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for distribution in ("coupfe-eda", "coupfe", "numpy", "scipy", "mpi4py", "petsc4py"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = None
    return versions


def _compiler_versions() -> dict[str, str | None]:
    """Record first-line compiler identities without executable paths."""
    versions: dict[str, str | None] = {}
    for name, command in {
        "c_compiler": ["cc", "--version"],
        "fortran_compiler": ["gfortran", "--version"],
        "mpi_c_wrapper": ["mpicc", "--version"],
    }.items():
        output = _command_output(command)
        versions[name] = output.splitlines()[0] if output else None
    return versions


def _git_record(path: Path) -> dict[str, Any]:
    """Return revision state without retaining a checkout path or diff content."""
    commit = _command_output(["git", "-C", str(path), "rev-parse", "HEAD"])
    if commit is None:
        return {"commit": None, "dirty": None}
    try:
        dirty_check = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        dirty: bool | None = bool(dirty_check.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        dirty = None
    return {"commit": commit, "dirty": dirty}


def _core_git_record() -> dict[str, Any]:
    try:
        spec = importlib.util.find_spec("coupfe")
    except (ImportError, AttributeError, ValueError):
        spec = None
    if spec is None or spec.origin is None:
        return {"commit": None, "dirty": None}
    return _git_record(Path(spec.origin).resolve().parent)


def _cpu_topology() -> dict[str, Any]:
    topology: dict[str, Any] = {
        "architecture": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
    }
    try:
        topology["launcher_process_available_cpu_count"] = len(
            os.sched_getaffinity(0)
        )
    except (AttributeError, OSError):
        topology["launcher_process_available_cpu_count"] = None
    try:
        topology["physical_memory_bytes"] = os.sysconf("SC_PAGE_SIZE") * os.sysconf(
            "SC_PHYS_PAGES"
        )
    except (AttributeError, OSError, ValueError):
        pass
    raw = _command_output(["lscpu", "--json"])
    if raw is None:
        return topology
    try:
        items = json.loads(raw).get("lscpu", [])
    except (json.JSONDecodeError, AttributeError):
        return topology
    allowed = {
        "Architecture": "architecture",
        "CPU(s)": "logical_cpu_count_reported",
        "Model name": "cpu_model",
        "Thread(s) per core": "threads_per_core",
        "Core(s) per socket": "cores_per_socket",
        "Socket(s)": "sockets",
        "NUMA node(s)": "numa_nodes",
        "Hypervisor vendor": "hypervisor_vendor",
        "Virtualization type": "virtualization_type",
    }
    for item in items:
        field = str(item.get("field", "")).rstrip(":")
        if field in allowed:
            topology[allowed[field]] = item.get("data")
    return topology


def _mpi_library_version() -> str | None:
    try:
        from mpi4py import MPI

        return _redact(MPI.Get_library_version().strip())
    except (ImportError, RuntimeError):
        return None


def _petsc_version() -> dict[str, Any] | None:
    try:
        import numpy as np
        from petsc4py import PETSc

        info = PETSc.Sys.getVersionInfo()
        result = {str(key): value for key, value in info.items()}
        scalar_type = np.dtype(PETSc.ScalarType)
        index_type = np.dtype(PETSc.IntType)
        result.update(
            scalar_type=scalar_type.name,
            scalar_bytes=scalar_type.itemsize,
            index_type=index_type.name,
            index_bytes=index_type.itemsize,
        )
        return result
    except (ImportError, RuntimeError, AttributeError):
        return None


def _environment_record(mpirun_version: str, machine_label: str | None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_utc": _utc_now(),
        "machine_label": machine_label,
        "hostname_recorded": False,
        "launcher_scope": "single launcher-visible host; no hostfile arguments",
        "operating_system": {
            "system": platform.system(),
            "kernel_release": platform.release(),
            "architecture": platform.machine(),
        },
        "cpu_topology": _cpu_topology(),
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "packages": _package_versions(),
        "compilers": _compiler_versions(),
        "mpi_launcher_version": _redact(mpirun_version),
        "mpi_library_version": _mpi_library_version(),
        "petsc_version": _petsc_version(),
        "thread_environment": {
            **{key: os.environ[key] for key in _SAFE_ENVIRONMENT_KEYS if key in os.environ},
            **{key: "1" for key in _FORCED_SINGLE_THREAD_KEYS},
        },
        "thread_environment_note": (
            "the harness forces common OpenMP/BLAS/NumExpr thread controls to 1 "
            "for every launch"
        ),
        "environment_policy": (
            "allowlisted thread/allocation settings only; paths, the complete environment, "
            "host name, scheduler job identifiers, and credentials are not retained"
        ),
    }


def _provenance_record() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_utc": _utc_now(),
        "benchmark_driver": DRIVER_MODULE,
        "metric_grain": METRIC_GRAIN,
        "coupfe_eda": _git_record(_REPOSITORY_ROOT),
        "coupfe_core": _core_git_record(),
        "source_paths_recorded": False,
    }


def _parse_scalefs(stdout: str, expected_dof: int, requested_ranks: int) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.startswith("SCALEFS ")]
    if len(lines) != 1:
        raise ValueError(f"expected exactly one SCALEFS line, received {len(lines)}")
    fields = lines[0].split()
    if len(fields) != 5:
        raise ValueError(f"SCALEFS line has {len(fields)} fields instead of 5")
    try:
        ndof, observed_ranks, wall_seconds, ksp_iterations = (
            int(fields[1]),
            int(fields[2]),
            float(fields[3]),
            int(fields[4]),
        )
    except ValueError as exc:
        raise ValueError("SCALEFS fields are not numeric") from exc
    if ndof != expected_dof:
        raise ValueError(f"SCALEFS ndof={ndof} does not match expected ndof={expected_dof}")
    if observed_ranks != requested_ranks:
        raise ValueError(
            f"SCALEFS ranks={observed_ranks} does not match requested ranks={requested_ranks}"
        )
    if not math.isfinite(wall_seconds) or wall_seconds <= 0.0:
        raise ValueError(f"SCALEFS wall={wall_seconds!r} is not finite and positive")
    if ksp_iterations < 0:
        raise ValueError(f"SCALEFS last-step iterations={ksp_iterations} is negative")
    return {
        "ndof": ndof,
        "ranks": observed_ranks,
        "wall_seconds": wall_seconds,
        "last_ksp_iterations": ksp_iterations,
    }


def _mpirun_version() -> str:
    try:
        result = subprocess.run(
            ["mpirun", "--version"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"cannot execute mpirun --version: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"mpirun --version exited with status {result.returncode}")
    return result.stdout.strip() or result.stderr.strip()


def run_one(
    n: int,
    ranks: int,
    repeat: int,
    run_directory: Path,
    *,
    oversubscribe: bool = False,
    timeout: int = 3600,
    open_mpi: bool = False,
    bind_cores: bool = False,
    cpu_list: str | None = None,
) -> dict[str, Any]:
    """Run and retain one solve, failing closed on process or metadata errors."""
    stem = f"rank-{ranks:04d}-repeat-{repeat:03d}"
    stdout_path = run_directory / f"{stem}.stdout.txt"
    stderr_path = run_directory / f"{stem}.stderr.txt"
    command = ["mpirun"]
    rankfile_meta: dict[str, Any] | None = None
    if oversubscribe and open_mpi:
        command.append("--oversubscribe")
    if bind_cores and open_mpi:
        if cpu_list is not None:
            selected_cpus = _expand_cpu_list(cpu_list)[:ranks]
            rankfile_path = run_directory / f"{stem}.rankfile.txt"
            rankfile_text = "".join(
                f"rank {rank}=localhost slot={cpu}\n"
                for rank, cpu in enumerate(selected_cpus)
            )
            rankfile_meta = _write_text(
                rankfile_path,
                rankfile_text,
                record_path=f"runs/{rankfile_path.name}",
            )
            command += ["--rankfile", str(rankfile_path), "--report-bindings"]
        else:
            command += ["--bind-to", "core", "--map-by", "core", "--report-bindings"]
    command += [
        "-n",
        str(ranks),
        sys.executable,
        "-m",
        DRIVER_MODULE,
        str(n),
    ]
    display_command = ["python" if item == sys.executable else item for item in command]
    if rankfile_meta is not None:
        rankfile_argument = display_command.index("--rankfile") + 1
        display_command[rankfile_argument] = rankfile_meta["path"]
    env = dict(os.environ)
    env.update({key: "1" for key in _FORCED_SINGLE_THREAD_KEYS})
    started = _utc_now()
    timed_out = False
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        stdout, stderr, returncode = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, returncode, timed_out = exc.stdout, exc.stderr, None, True
    except OSError as exc:
        stdout, stderr, returncode = "", str(exc), None

    stdout_meta = _write_text(
        stdout_path, stdout or "", record_path=f"runs/{stdout_path.name}"
    )
    stderr_meta = _write_text(
        stderr_path, stderr or "", record_path=f"runs/{stderr_path.name}"
    )
    record: dict[str, Any] = {
        "requested_n": n,
        "requested_ranks": ranks,
        "repeat": repeat,
        "started_utc": started,
        "finished_utc": _utc_now(),
        "command": display_command,
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout": stdout_meta,
        "stderr": stderr_meta,
    }
    if rankfile_meta is not None:
        record["rankfile"] = rankfile_meta
    if timed_out:
        record.update(status="failed", error=f"mpirun exceeded {timeout} seconds")
        raise BenchmarkRunError(record["error"], record)
    if returncode != 0:
        record.update(status="failed", error=f"mpirun exited with status {returncode}")
        raise BenchmarkRunError(record["error"], record)
    try:
        observed = _parse_scalefs(str(stdout or ""), _expected_ndof(n), ranks)
    except ValueError as exc:
        record.update(status="failed", error=str(exc))
        raise BenchmarkRunError(record["error"], record) from exc
    record.update(status="passed", observed=observed)
    return record


def _aggregate(records: Iterable[dict[str, Any]], rank_order: list[int]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {rank: [] for rank in rank_order}
    for record in records:
        if record.get("status") == "passed":
            grouped[record["requested_ranks"]].append(record)
    result: list[dict[str, Any]] = []
    for rank in rank_order:
        group = grouped[rank]
        if not group:
            continue
        walls = [item["observed"]["wall_seconds"] for item in group]
        iterations = [item["observed"]["last_ksp_iterations"] for item in group]
        result.append(
            {
                "ranks": rank,
                "ndof": group[0]["observed"]["ndof"],
                "repeat_count": len(group),
                "wall_seconds": {
                    "median": statistics.median(walls),
                    "minimum": min(walls),
                    "maximum": max(walls),
                    "samples": walls,
                },
                "last_ksp_iterations": {
                    "minimum": min(iterations),
                    "maximum": max(iterations),
                    "samples": iterations,
                },
            }
        )
    if result:
        baseline = result[0]["wall_seconds"]["median"]
        for row in result:
            row["speedup_from_smallest_rank_median"] = (
                baseline / row["wall_seconds"]["median"]
            )
    return result


def _summary(
    records: list[dict[str, Any]],
    rank_order: list[int],
    config: dict[str, Any],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "error": error,
        "updated_utc": _utc_now(),
        "metric": {
            "name": "driver_reported_synchronized_max_rank_solve_wall_seconds",
            "unit": "seconds",
            "grain": METRIC_GRAIN,
            "aggregation": "median; minimum, maximum, and every sample retained",
            "rank_aggregation": "maximum synchronized MPI wall time across ranks",
        },
        "configuration": config,
        "runs": records,
        "aggregate": _aggregate(records, rank_order),
        "interpretation": (
            "Local measurement only. A public performance statement additionally requires "
            "physical cores, a stable allocation, adequate repeats, reviewed retained records, "
            "and appropriate problem-size and rank coverage."
        ),
    }


def markdown_table(records: list[dict[str, Any]], rank_order: list[int] | None = None) -> str:
    """Format the median and range of retained runs as a local-measurement table."""
    if not records:
        raise ValueError("cannot format an empty rank sweep")
    if not isinstance(records[0], dict):
        # Compatibility with the former list of (ndof, ranks, wall, iterations) rows.
        records = [
            {
                "requested_ranks": row[1],
                "status": "passed",
                "observed": {
                    "ndof": row[0],
                    "ranks": row[1],
                    "wall_seconds": row[2],
                    "last_ksp_iterations": row[3],
                },
            }
            for row in records
        ]
    order = rank_order or list(dict.fromkeys(row["requested_ranks"] for row in records))
    rows = _aggregate(records, order)
    ndof = rows[0]["ndof"]
    ranks = " | ".join(str(row["ranks"]) for row in rows)
    separator = "|---" * (len(rows) + 1) + "|"
    medians = " | ".join(f"{row['wall_seconds']['median']:.4g}" for row in rows)
    ranges = " | ".join(
        f"{row['wall_seconds']['minimum']:.4g}–{row['wall_seconds']['maximum']:.4g}"
        for row in rows
    )
    speedups = " | ".join(
        f"{row['speedup_from_smallest_rank_median']:.2f}x" for row in rows
    )
    iterations = " | ".join(
        (
            str(row["last_ksp_iterations"]["minimum"])
            if row["last_ksp_iterations"]["minimum"] == row["last_ksp_iterations"]["maximum"]
            else f"{row['last_ksp_iterations']['minimum']}–{row['last_ksp_iterations']['maximum']}"
        )
        for row in rows
    )
    repeats = " | ".join(str(row["repeat_count"]) for row in rows)
    return "\n".join(
        [
            f"**Local fixed-size measurement, {ndof:,} DOF** "
            "(`etv_distributed_fs`; synchronized maximum rank solve wall time):",
            "",
            f"| ranks | {ranks} |",
            separator,
            f"| repeats | {repeats} |",
            f"| median wall (s) | {medians} |",
            f"| wall range (s) | {ranges} |",
            f"| median speedup | {speedups} |",
            f"| last-step KSP iteration range | {iterations} |",
        ]
    )


def _rank_list(value: str) -> list[int]:
    try:
        ranks = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ranks must be comma-separated integers") from exc
    if not ranks or any(rank <= 0 for rank in ranks):
        raise argparse.ArgumentTypeError("rank counts must be positive")
    if len(set(ranks)) != len(ranks):
        raise argparse.ArgumentTypeError("rank counts must not be repeated")
    if ranks != sorted(ranks):
        raise argparse.ArgumentTypeError("rank counts must be in ascending order")
    return ranks


def _cpu_list(value: str) -> str:
    """Validate an Open MPI CPU-list expression and return it unchanged."""
    if not re.fullmatch(r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*", value):
        raise argparse.ArgumentTypeError(
            "CPU list must contain comma-separated IDs or ascending ranges"
        )
    seen: set[int] = set()
    for item in value.split(","):
        if "-" in item:
            start, stop = (int(part) for part in item.split("-", 1))
            if stop < start:
                raise argparse.ArgumentTypeError("CPU-list ranges must be ascending")
            values = range(start, stop + 1)
        else:
            values = [int(item)]
        for cpu in values:
            if cpu in seen:
                raise argparse.ArgumentTypeError("CPU list must not repeat an ID")
            seen.add(cpu)
    return value


def _cpu_list_size(value: str) -> int:
    return len(_expand_cpu_list(value))


def _expand_cpu_list(value: str) -> list[int]:
    result: list[int] = []
    for item in value.split(","):
        if "-" in item:
            start, stop = (int(part) for part in item.split("-", 1))
            result.extend(range(start, stop + 1))
        else:
            result.append(int(item))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retain a repeated rank sweep for etv_distributed_fs."
    )
    parser.add_argument("--n", type=int, default=1580, help="n x n element grid")
    parser.add_argument(
        "--ranks", type=_rank_list, default=_rank_list("4,8,16,32,48"),
        help="comma-separated rank counts",
    )
    parser.add_argument("--repeats", type=int, default=3, help="launches per rank count")
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="new directory for summary, streams, environment, and provenance",
    )
    parser.add_argument("--oversubscribe", action="store_true")
    parser.add_argument(
        "--bind-cores",
        action="store_true",
        help=(
            "with Open MPI, bind/map ranks to cores and retain --report-bindings "
            "output; recommended for non-oversubscribed measurements"
        ),
    )
    parser.add_argument(
        "--cpu-list",
        type=_cpu_list,
        help=(
            "optional Open MPI processor-ID list (for example 16-23); requires "
            "--bind-cores and must provide at least the largest requested rank count"
        ),
    )
    parser.add_argument("--timeout", type=int, default=3600, help="per-launch timeout in seconds")
    parser.add_argument(
        "--machine-label",
        help="optional non-secret allocation/machine label; the hostname is not recorded",
    )
    args = parser.parse_args()
    if args.n <= 0:
        parser.error("--n must be positive")
    if args.repeats <= 0:
        parser.error("--repeats must be positive")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.cpu_list is not None and not args.bind_cores:
        parser.error("--cpu-list requires --bind-cores")
    if args.cpu_list is not None and _cpu_list_size(args.cpu_list) < max(args.ranks):
        parser.error("--cpu-list must contain at least the largest requested rank count")
    try:
        args.output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f"--output-dir already exists: {args.output_dir}")
    run_directory = args.output_dir / "runs"
    run_directory.mkdir()

    config = {
        "n": args.n,
        "expected_ndof": _expected_ndof(args.n),
        "rank_order": args.ranks,
        "repeats_per_rank": args.repeats,
        "oversubscribed": args.oversubscribe,
        "mpi_rank_binding": (
            (
                "Open MPI: retained explicit rankfile, one selected processor per rank, "
                "plus --report-bindings"
                if args.cpu_list is not None
                else "Open MPI: --bind-to core --map-by core --report-bindings"
            )
            if args.bind_cores
            else "launcher default; inspect retained streams and allocation record"
        ),
        "mpi_cpu_list": args.cpu_list,
        "warmup_policy": "no discarded warm-ups; every fresh launch is retained and aggregated",
        "timeout_seconds_per_launch": args.timeout,
        "forced_single_thread_environment": {
            key: "1" for key in _FORCED_SINGLE_THREAD_KEYS
        },
        "driver": DRIVER_MODULE,
        "launcher_scope": "single launcher-visible host; no hostfile arguments",
        "kernel_protocol": (
            "fresh per-rank generated-kernel build before the synchronized timed "
            "region of every launch"
        ),
        "solver_configuration": SOLVER_CONFIGURATION,
    }
    _write_json(args.output_dir / "run_manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "created_utc": _utc_now(),
        "metric_grain": METRIC_GRAIN,
        "configuration": config,
    })
    records: list[dict[str, Any]] = []
    summary_path = args.output_dir / "summary.json"
    try:
        version = _mpirun_version()
        _write_json(
            args.output_dir / "environment.json",
            _environment_record(version, args.machine_label),
        )
        _write_json(args.output_dir / "provenance.json", _provenance_record())
        open_mpi = "Open MPI" in version or "OpenRTE" in version
        if args.oversubscribe and not open_mpi:
            raise RuntimeError("--oversubscribe is currently supported only with Open MPI")
        if args.bind_cores and not open_mpi:
            raise RuntimeError("--bind-cores is currently supported only with Open MPI")
        for rank in args.ranks:
            for repeat in range(1, args.repeats + 1):
                record = run_one(
                    args.n,
                    rank,
                    repeat,
                    run_directory,
                    oversubscribe=args.oversubscribe,
                    timeout=args.timeout,
                    open_mpi=open_mpi,
                    bind_cores=args.bind_cores,
                    cpu_list=args.cpu_list,
                )
                records.append(record)
                observed = record["observed"]
                print(
                    f"rank={rank:>3} repeat={repeat:>2}: {observed['ndof']:,} DOF, "
                    f"wall={observed['wall_seconds']:.4g}s, "
                    f"last-step KSP iterations={observed['last_ksp_iterations']}",
                    flush=True,
                )
                _write_json(summary_path, _summary(records, args.ranks, config, "running"))
    except BenchmarkRunError as exc:
        records.append(exc.record)
        _write_json(summary_path, _summary(records, args.ranks, config, "failed", str(exc)))
        raise SystemExit(f"benchmark failed: {exc}") from exc
    except Exception as exc:
        _write_json(summary_path, _summary(records, args.ranks, config, "failed", str(exc)))
        raise

    _write_json(summary_path, _summary(records, args.ranks, config, "complete"))
    table = markdown_table(records, args.ranks)
    _write_text(args.output_dir / "table.md", table + "\n")
    print("\n" + table)
    print(f"\nretained measurement bundle: {args.output_dir}")


if __name__ == "__main__":
    main()
