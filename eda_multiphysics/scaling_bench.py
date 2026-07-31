"""Strong-scaling harness for the distributed FieldSplit coupled solve.

The historical strong-scaling table in ``DISTRIBUTED.md`` was transcribed from manual ``mpirun``
runs without retaining raw stdout and a complete environment record. This script can generate a
new table from the driver's machine-parseable
``SCALEFS <ndof> <ranks> <wall> <iters>`` line, but printing a table alone is not archival evidence.
Retain raw output, hardware/topology, MPI/PETSc versions, and a locked environment before making a
public performance claim.

    # generate a new 5M-DOF, 4->48-core measurement (needs >= 48 physical cores):
    OMP_NUM_THREADS=1 python -m eda_multiphysics.scaling_bench --n 1580 --ranks 4,8,16,32,48

    # a quick smoke anywhere (oversubscribes cores):
    OMP_NUM_THREADS=1 python -m eda_multiphysics.scaling_bench --n 120 --ranks 1,2,4 --oversubscribe

Each row is one ``mpirun -n R`` of :mod:`eda_multiphysics.etv_distributed_fs`; speedup is relative
to the smallest rank count. Treat the emitted table as a local measurement until its evidence
bundle is retained.
"""
import argparse
import os
import subprocess
import sys


def run_one(n, ranks, oversubscribe=False, timeout=3600):
    """One distributed run; returns (ndof, ranks, wall_s, ksp_iters) parsed from SCALEFS."""
    cmd = ["mpirun"]
    if oversubscribe:
        ver = subprocess.run(["mpirun", "--version"], capture_output=True, text=True,
                             timeout=10).stdout
        if "Open MPI" in ver:
            cmd += ["--oversubscribe"]
    cmd += ["-n", str(ranks), sys.executable, "-m", "eda_multiphysics.etv_distributed_fs", str(n)]
    env = dict(os.environ, OMP_NUM_THREADS="1")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    for line in proc.stdout.splitlines():
        if line.startswith("SCALEFS "):
            _, ndof, r, wall, its = line.split()
            return int(ndof), int(r), float(wall), int(its)
    raise RuntimeError(f"no SCALEFS line from `-n {ranks}`:\n{proc.stdout}\n{proc.stderr}")


def sweep(n, rank_list, oversubscribe=False, timeout=3600):
    rows = []
    for r in rank_list:
        row = run_one(n, r, oversubscribe, timeout)
        rows.append(row)
        print(f"  ran -n {r:>3}: {row[0]:,} DOF  wall={row[2]:.2f}s  KSP iters={row[3]}", flush=True)
    return rows


def markdown_table(rows):
    """Format sweep rows exactly like DISTRIBUTED.md's strong-scaling table."""
    ndof = rows[0][0]
    base = rows[0][2]
    ranks = " | ".join(str(r[1]) for r in rows)
    sep = "|---" * (len(rows) + 1) + "|"
    walls = " | ".join(f"{r[2]:.1f}" for r in rows)
    spd = " | ".join(f"{base / r[2]:.2f}x" for r in rows)
    its = " | ".join(str(r[3]) for r in rows)
    return "\n".join([
        f"**Strong scaling, fixed {ndof:,} DOF** (`etv_distributed_fs`, FieldSplit GAMG/field; "
        "wall = solve only):",
        "",
        f"| ranks | {ranks} |",
        sep,
        f"| wall (s) | {walls} |",
        f"| speedup | {spd} |",
        f"| KSP iters | {its} |",
    ])


def main():
    ap = argparse.ArgumentParser(description="Reproducible strong-scaling table for etv_distributed_fs.")
    ap.add_argument("--n", type=int, default=1580, help="grid size n (n x n); n=1580 ~ 5M DOF")
    ap.add_argument("--ranks", default="4,8,16,32,48", help="comma-separated rank counts")
    ap.add_argument("--oversubscribe", action="store_true", help="pass --oversubscribe to mpirun")
    ap.add_argument("--timeout", type=int, default=3600, help="per-run timeout (s)")
    a = ap.parse_args()
    rank_list = [int(x) for x in a.ranks.split(",")]
    print(f"strong-scaling sweep: n={a.n}, ranks={rank_list}", flush=True)
    rows = sweep(a.n, rank_list, a.oversubscribe, a.timeout)
    print("\n" + markdown_table(rows))


if __name__ == "__main__":
    main()
