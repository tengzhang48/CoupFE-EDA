# 526,338-DOF local rank sweep, 2026-08-01

This retained record measures one fixed-size `etv_distributed_fs` solve at
1, 2, 4, and 8 MPI ranks. It is a local solver-region measurement on one
nonexclusive KVM virtual machine, not a general performance or cluster-scaling
claim.

## Result

| MPI ranks | 1 | 2 | 4 | 8 |
|---|---:|---:|---:|---:|
| Repeats | 3 | 3 | 3 | 3 |
| Median wall time (s) | 26.0718 | 14.2711 | 7.29017 | 3.93986 |
| Range (s) | 25.9295–26.1043 | 13.9319–14.8189 | 7.26777–7.37178 | 3.89778–3.96028 |
| Speedup from 1-rank median | 1.00× | 1.83× | 3.58× | 6.62× |
| Parallel efficiency | 100% | 91.3% | 89.4% | 82.7% |
| Last-step KSP iterations | 12 | 12 | 12 | 13 |

All twelve launches returned zero, emitted exactly one accepted `SCALEFS`
record, completed six Newton steps, and reported the same rounded peak
temperature change, `0.9762`. The rank-dependent KSP sequence and every timing
sample are retained in [`summary.json`](summary.json) and the complete standard
streams under [`runs/`](runs/).

## Fixed configuration

- Structured `512 × 512` Quad4 grid, two fields per node: 526,338 DOF.
- Additive PETSc FieldSplit with GAMG for each scalar field and GMRES.
- One process per selected virtual processor; common OpenMP and BLAS thread
  controls forced to one.
- Three fresh launches per rank count; no discarded warm-up.
- The timed interval starts after a pre-solve MPI barrier and ends after a
  final barrier. It includes Newton assembly and linear solves but excludes
  process launch, imports, grid construction, and generated-kernel build.
- Clean CoupFE-EDA source `5d34894e05b597baba3dcffaad0b2f097b2f7117`
  with clean pinned CoupFE Core
  `454f73ce2de284262b214a2b37bd676c6aca3c0a`.

The retained command was equivalent to:

```bash
OMP_NUM_THREADS=1 OMP_PROC_BIND=true OMP_PLACES=cores \
python -m eda_multiphysics.scaling_bench \
  --n 512 --ranks 1,2,4,8 --repeats 3 --bind-cores \
  --cpu-list 48-55 \
  --machine-label cpu-vm-kvm-single-vm-nonexclusive \
  --output-dir <new-directory-outside-the-source-tree>
```

For each launch, the harness generated and retained an Open MPI rankfile that
maps rank `i` to virtual processor `48 + i`. The `--report-bindings` output in
each stderr record confirms those placements.

## Machine and interpretation boundary

The environment record identifies a 64-vCPU AMD EPYC-Milan KVM guest with one
reported NUMA node and 64 launcher-visible logical processors. The allocation
was not exclusive, and the virtual topology reports one core per socket. The
result therefore describes this VM, revision, solver, problem, rank placement,
and measurement window only.

Open MPI also reported that its PMIx `gds/shmem` component was unavailable,
that the shared-memory transport could not use Linux CMA under the guest's
ptrace settings, and in some launches an ORTE help-message unpack warning. It
fell back to another shared-memory mechanism, and every measured launch still
returned successfully. These complete warnings are retained because they may
affect timing and reinforce the local, non-qualified interpretation.

[`environment.json`](environment.json), [`provenance.json`](provenance.json),
and [`run_manifest.json`](run_manifest.json) record the reviewed environment,
source state, and protocol. Paths, hostname, credentials, and the complete
process environment are not published.
