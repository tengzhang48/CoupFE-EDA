# Distributed solvers and scaling records

CoupFE-EDA contains several PETSc/MPI research drivers. The code, correctness
checks, example commands, and performance records serve different purposes:

- **Code** implements a distributed assembly or solve path.
- **Tests** compare selected small distributed runs with serial results.
- **Examples** show how to invoke a driver.
- **Solver-scaling benchmarks** measure one fixed-size solve at several rank
  counts under a recorded environment.
- **Results** are retained output bundles. A timing table without its bundle is
  historical context, not current performance evidence.

## Implemented distributed paths

| Driver | Path exercised | Current public evidence | Important limit |
|---|---|---|---|
| `pdn_distributed` | Resistor-network PDN assembled and solved with PETSc | Small serial-versus-MPI checks | The edge list is replicated; no current scaling record is bundled |
| `etv_distributed` | Coupled electrothermal solve with ASM/GMRES | Runnable research driver | No current retained rank sweep |
| `etv_distributed_fs` | Coupled electrothermal solve with FieldSplit and GAMG per field | Size-24 comparisons at two and four ranks in `tests/test_toolchain.py` | The nonlinear loop replicates the global solution vector |
| `etv_distributed`/`etv_distributed_fs` validation modes | MPI result compared with an independent serial solve | Checked only for the documented small cases | Agreement is a correctness check, not a performance result |

The documented Core baseline is revision
`454f73ce2de284262b214a2b37bd676c6aca3c0a`.

## Requirements for distributed runs

Use a mutually compatible MPI launcher, `mpi4py`, PETSc, and `petsc4py`.
Generated-kernel cases additionally require the compiler and build tools used
by CoupFE code generation. FieldSplit and direct-solver availability depends on
the PETSc build.

A reviewable measurement needs all of the following:

- fixed problem input and revision, including both EDA and Core commits;
- MPI, PETSc, Python, NumPy/SciPy, and package versions;
- matrix/grid size, rank count, solver/preconditioner, and stopping rules;
- CPU model and socket/core/thread/NUMA topology;
- physical rank placement or scheduler allocation, with no oversubscription;
- all thread settings; the retained harness forces common OpenMP, BLAS, and
  NumExpr controls to one thread per rank;
- at least three fresh launches at every rank count (five or more when run
  variability is material); and
- complete standard output/error and a machine-readable result for each
  launch.

Do not compare measurements collected under different hardware, allocation,
software, solver options, stopping rules, or problem sizes as one scaling
sweep.

## Correctness examples

PDN grid with CG/GAMG:

```bash
OMP_NUM_THREADS=1 mpirun -n 4 \
  python -m eda_multiphysics.pdn_distributed 120
```

Caller-provided SPICE export:

```bash
OMP_NUM_THREADS=1 mpirun -n 4 \
  python -m eda_multiphysics.pdn_distributed path/to/pdn.sp
```

`--direct` requests LU with `superlu_dist`, which is not present in every
PETSc build.

Small coupled FieldSplit comparison:

```bash
OMP_NUM_THREADS=1 mpirun -n 2 \
  python -m eda_multiphysics.etv_distributed_fs 24 --validate
```

Run the distributed toolchain checks with:

```bash
python -m pytest -q -m toolchain
```

These are correctness runs. They do not establish strong scaling.

## Retained solver-scaling benchmark

`eda_multiphysics.scaling_bench` preserves the existing fixed-size rank sweep
and adds repeats and a retained measurement bundle. For every rank and repeat,
it starts a fresh `mpirun`, invokes `etv_distributed_fs` once, and accepts
exactly one line with this schema:

```text
SCALEFS <ndof> <ranks> <wall_seconds> <last_ksp_iterations>
```

The measurement grain is **one fixed-size coupled solve per rank count and
repeat**. After every rank completes setup, a barrier starts the timed region.
A final barrier closes it, and `wall_seconds` is the maximum MPI wall-clock
elapsed time across ranks. The interval includes Newton assembly and linear
solves; it excludes MPI process launch, Python imports, grid creation, and
generated-kernel build. Each fresh launch currently builds a kernel on every
rank before the start barrier. That work is outside the reported metric but is
part of the run protocol and can affect machine state. The benchmark reports
the median and retains every sample and its range.

The harness fails, with a nonzero exit, if `mpirun` fails or times out, if the
driver emits zero or multiple `SCALEFS` lines, or if the reported DOF/rank
metadata differs from the requested grid and rank count. A failed launch is
not silently turned into a table row.

Example local smoke, using oversubscription only to exercise the path:

```bash
OMP_NUM_THREADS=1 python -m eda_multiphysics.scaling_bench \
  --n 24 --ranks 1,2 --repeats 1 --oversubscribe \
  --output-dir /tmp/coupfe-eda-scaling-smoke
```

Example measurement protocol on an allocation with at least 48 physical
cores:

```bash
OMP_NUM_THREADS=1 OMP_PROC_BIND=true OMP_PLACES=cores \
python -m eda_multiphysics.scaling_bench \
  --n 1580 --ranks 4,8,16,32,48 --repeats 5 --bind-cores \
  --cpu-list 0-47 \
  --machine-label documented-allocation \
  --output-dir /path/outside/the/source/tree/coupfe-eda-scaling-5m
```

With `--cpu-list`, the harness retains the exact selected processor IDs and a
generated one-processor-per-rank Open MPI rankfile for every launch.

The output directory must not already exist and contains:

```text
environment.json        selected hardware/software/thread metadata
provenance.json         EDA/Core revisions and dirty state, without paths
run_manifest.json       fixed input, ranks, repeats, and metric grain
summary.json            status, every sample, medians, ranges, and speedups
table.md                human-readable view of the same summary
runs/
  rank-####-repeat-###.stdout.txt
  rank-####-repeat-###.stderr.txt
```

With Open MPI, `--bind-cores` adds `--bind-to core --map-by core
--report-bindings`; the per-run stderr records then retain the actual mapping.
The current protocol discards no warm-up: every fresh launch is retained and
included in the median and range.

Only allowlisted environment fields are recorded. The hostname, complete
environment, scheduler identifiers, repository paths, and credentials are not
written. Retained streams are scrubbed for the checkout/home paths and common
credential forms. Review a bundle before publishing it; automatic scrubbing
does not replace human review.

The static benchmark definition is in
`benchmarks/solver_scaling/manifest.json`. No current hardware-scaling bundle
is committed in this repository.

## Historical observations—not current evidence

The following tables are restored from repository snapshot `f961f5f`. A
2026-08-01 recovery search covered current and historical Git refs, the
attached original and companion EDA checkouts, and project coordination notes.
It found these tables, related prose, and a generated figure, but no raw
stdout/stderr, hardware/topology inventory, exact runtime environment, repeat
policy, or per-run records. Consequently, these numbers are
**unqualified historical observations** and must not be mixed with or cited as
current-revision performance results.

### Historical distributed PDN observations

| Case | Nodes | Edges | Ranks | Reported iterations | Reported solve wall | Reported serial/MPI difference |
|---|---:|---:|---:|---:|---:|---:|
| Grid 120 x 120 | 14,400 | 28,560 | 1/2/4 | 13/13/12 | 0.13 to 0.07 s | about 3e-11 |
| Grid 400 x 400 | 160,000 | 319,200 | 1/2/4 | 16/15/15 | 1.57 to 0.67 s | about 3e-11 |
| Grid 1000 x 1000 | 1,000,000 | 1,998,000 | 4 | 18 | 4.3 s | 9e-11 |
| External AES-derived PDN, input not bundled | 3,089 | 3,447 | 1/2 | 20/16 | 0.02 s | 3e-11 |

The old note described the wall value as solve-only and the 400-grid endpoint
ratio as 2.3x. Those interpretations require a new retained run before reuse.

### Historical 526,338-DOF ASM/GMRES observations

The earlier `etv_distributed` table described a 2D Quad4 coupled solve with
ASM/GMRES:

| Ranks | 8 | 16 | 32 |
|---|---:|---:|---:|
| Reported wall (s) | 88.8 | 47.4 | 27.8 |
| Reported speedup from 8 ranks | 1.00x | 1.87x | 3.19x |

That snapshot also mentioned serial/MPI agreement near `5.2e-11` and growing
iterations with problem size. Neither statement has a retained record at this
revision.

### Historical 4,999,122-DOF FieldSplit observations

The earlier `etv_distributed_fs` table described an `n=1580` 2D Quad4 problem,
nonlinear coefficient `alpha=0.05`, FieldSplit with GAMG per scalar field, and
solve-only timing:

| Ranks | 4 | 8 | 16 | 32 | 48 |
|---|---:|---:|---:|---:|---:|
| Reported wall (s) | 87.7 | 48.3 | 26.1 | 18.2 | 14.7 |
| Reported speedup from 4 ranks | 1.00x | 1.81x | 3.36x | 4.80x | 5.98x |
| Reported last KSP iterations | 18 | 19 | 18 | 18 | 18 |

The old note also reported serial/MPI agreement near `1e-16`. The table and
agreement value are rerun targets, not current claims.

## Interpretation limits

- Oversubscribed runs are functional checks, not hardware-scaling evidence.
- A fixed-size rank sweep measures strong scaling only for that fixed problem.
- A median speedup does not establish parallel efficiency outside the measured
  ranks and machine.
- Small serial/MPI agreement does not qualify another mesh, solver tolerance,
  partition, material model, or rank count.
- The replicated solution in `etv_distributed_fs` bounds memory scalability.
- No distributed stateful Anand joint solver or qualified distributed
  periodic-TSV consumer is included.
