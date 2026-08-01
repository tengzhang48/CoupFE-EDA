# Recovered historical solver and scaling observations

These records preserve performance and iteration observations made during the
development of CoupFE-EDA. They show the original direction of the package:
EDA-oriented sparse solves, compiled coupled elements, distributed
electrothermal analysis, and three-dimensional thermo-mechanical extensions.

They are **not current benchmark results**. The raw stdout/stderr, exact machine
allocation, complete software environment, rank placement, and repeat samples
were not retained. A 2026-08-01 recovery search covered current and historical
Git refs, the attached original and companion EDA checkouts, and project
coordination notes. It found the tables, explanatory prose, and a generated
figure, but not the missing run records. The values therefore remain visible as
rerun targets and historical design context.

The old presentation graphic was not republished unchanged because its labels
called these observations “scaling evidence” and “mesh-independent solver
behavior,” claims that the missing run records cannot support. The underlying
numbers are preserved in the tables and machine-readable JSON here; a current
figure should be generated only from a reviewed retained bundle.

## Distributed PDN observations

| Case | Nodes | Edges | Ranks | Reported iterations | Reported solve wall | Reported serial/MPI difference |
|---|---:|---:|---:|---:|---:|---:|
| Grid 120 × 120 | 14,400 | 28,560 | 1/2/4 | 13/13/12 | 0.13 to 0.07 s | about 3e-11 |
| Grid 400 × 400 | 160,000 | 319,200 | 1/2/4 | 16/15/15 | 1.57 to 0.67 s | about 3e-11 |
| Grid 1000 × 1000 | 1,000,000 | 1,998,000 | 4 | 18 | 4.3 s | 9e-11 |
| External AES-derived PDN, input not bundled | 3,089 | 3,447 | 1/2 | 20/16 | 0.02 s | 3e-11 |

The historical note described the wall value as solve-only and reported a
distributed direct comparison near 6e-13 on the AES-derived input. The input,
raw output, and exact environment are absent, so those values cannot serve as a
current real-design or performance result.

## Coupled 2-D electrothermal ASM/GMRES

The `etv_distributed` records used a compiled Quad4 coupled element and an
ASM/GMRES distributed solve. The 132,098-DOF sweep was reported as:

| Ranks | 1 | 2 | 4 | 8 |
|---|---:|---:|---:|---:|
| Wall (s) | 55.2 | 36.2 | 19.3 | 10.5 |
| Speedup from one rank | 1.00x | 1.52x | 2.86x | 5.26x |
| KSP iterations | 232 | 350 | 341 | 336 |

The larger 526,338-DOF sweep was reported as:

| Ranks | 8 | 16 | 32 |
|---|---:|---:|---:|
| Wall (s) | 88.8 | 47.4 | 27.8 |
| Speedup from eight ranks | 1.00x | 1.87x | 3.19x |
| KSP iterations | 1121 | 1363 | 1263 |

The associated serial/MPI difference was reported near 5.2e-11. The original
interpretation was that ASM still reduced wall time while its lack of a coarse
grid caused iteration growth from roughly 340 at 132k DOF to roughly 1200 at
526k DOF. That interpretation is plausible context for the later FieldSplit
work, but it needs a retained rerun before being treated as a measured claim.

## Serial FieldSplit iteration comparison

The serial `etv_fieldsplit` study split potential and temperature and applied
GAMG to each scalar field. Its recorded comparison was:

| DOF | 33k | 132k | 296k | 526k |
|---|---:|---:|---:|---:|
| FieldSplit KSP iterations | 16 | 17 | 17 | 19 |
| ASM comparison | not recorded | about 340 | not recorded | about 1200 |

This was the numerical motivation for the custom distributed FieldSplit
driver. It is not a current mesh-independence or complexity result.

## Distributed FieldSplit electrothermal solve

For an `n=1580` structured Quad4 case with 4,999,122 DOF, the historical
`etv_distributed_fs` record reported:

| Ranks | 4 | 8 | 16 | 32 | 48 |
|---|---:|---:|---:|---:|---:|
| Wall (s) | 87.7 | 48.3 | 26.1 | 18.2 | 14.7 |
| Speedup from four ranks | 1.00x | 1.81x | 3.36x | 4.80x | 5.98x |
| Last KSP iterations | 18 | 19 | 18 | 18 | 18 |

The note described the timed region as solve-only and the serial/MPI difference
as near 1e-16. The current benchmark harness was added to reproduce this kind
of sweep with retained rank bindings, complete sanitized streams, environment,
revisions, and repeats.

## Serial 3-D Hex8 electrothermal size study

The `etv_3d` FieldSplit/GAMG study on a synthetic cube recorded:

| DOF | 9.8k | 31k | 72k | 138k | 235k |
|---|---:|---:|---:|---:|---:|
| KSP iterations | 16 | 17 | 17 | 17 | 17 |
| Solve wall (s) | 0.07 | 0.25 | 0.62 | 1.24 | 2.37 |
| µs/DOF | 7.4 | 7.9 | 8.6 | 9.0 | 10.1 |

These numbers motivated the compiled 3-D path. They do not establish current
linear complexity, distributed 3-D scaling, or performance on device geometry.

## Serial thermo-mechanical FieldSplit study

The generated Cu/Si TSV study in `thermomech_tsv` split displacement from a
prescribed-temperature field, used GAMG on displacement with a rigid-body
near-null space, and used Jacobi on temperature. It recorded:

| DOF | 16k | 23k | 49k | 89k | 145k |
|---|---:|---:|---:|---:|---:|
| KSP iterations | 20 | 19 | 17 | 21 | 20 |
| Solve wall (s) | 2.7 | 1.9 | 5.2 | 14.6 | 19.1 |

An ablation was described as roughly 565 iterations without the rigid-body
near-null space and roughly 20 with it. A separate direct-solve observation
reported growth from about 4.2 s at 15k DOF to about 95 s at 62k DOF. These are
useful solver-design observations, not retained timing or mesh-independence
evidence.

## Assembly-path observation

At `n=350` and four ranks, the historical development note reported reducing
the per-step assembly wall from about 0.55 s to 0.074 s by replacing Python
element stamping with batched element evaluation and owned-row CSR creation.
The reported 7.4x ratio is a rerun target. The current driver retains the
owned-row CSR design; the old raw profiler output is absent.

The same work recorded a PETSc `MatSetValuesCOO`/GAMG repeated-solve failure on
PETSc/petsc4py 3.24.2 and 3.25.2. The recovered standalone reproducer is kept as
[`petsc_coo_gamg_reproducer.py`](petsc_coo_gamg_reproducer.py). Its outcome is
version/build dependent and is not part of the CoupFE-EDA pass/fail suite.

## Source trail

The principal transcribed sources are snapshot `f961f5f` versions of
`docs/capabilities.md`, `eda_multiphysics/DISTRIBUTED.md`, and
`docs/lessons_learned.md`. Git preserves the full original prose. This file
keeps the numerical content discoverable without presenting development-era
measurements as results from the current revision.
