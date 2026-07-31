# Distributed run guide

This repository contains PETSc/MPI paths for a resistor-network PDN and
selected coupled electrothermal examples. Public evidence is limited to the
size-24 serial-versus-MPI output comparisons in `tests/test_toolchain.py`. No
general performance, memory, iteration-scaling, or production-size claim is
made here.

## Requirements

Distributed runs require a mutually compatible MPI launcher, `mpi4py`, PETSc,
and `petsc4py`. Coupled generated-kernel cases also require the compiler and
build tools used by CoupFE code generation. Record:

- Python, NumPy/SciPy, CoupFE, CoupFE-EDA, compiler, MPI, and PETSc versions;
- the full EDA and Core Git revisions and imported Core path;
- PETSc configuration and solver options;
- matrix/grid size, rank count, thread count, host/topology, and partition;
- complete standard output/error and exit code; and
- repeated-run policy for any timing statement.

The documented baseline uses Core revision
`454f73ce2de284262b214a2b37bd676c6aca3c0a`.

## PDN graph

Run the generated resistor grid with CG/GAMG:

```bash
OMP_NUM_THREADS=1 mpirun -n 4 \
  python -m eda_multiphysics.pdn_distributed 120
```

Or pass a supported SPICE export:

```bash
OMP_NUM_THREADS=1 mpirun -n 4 \
  python -m eda_multiphysics.pdn_distributed path/to/pdn.sp
```

`--direct` requests LU with `superlu_dist`. That factor package is not present
in every PETSc build; availability is an environment property and should be
checked before selecting the option.

Rank zero compares the gathered result with the independent SciPy assembly and
reports the maximum difference. This driver remains a research path until a
current-revision rank record is retained; the metric is not a scaling result.

## Coupled electrothermal FieldSplit path

For a small comparison run:

```bash
OMP_NUM_THREADS=1 mpirun -n 2 \
  python -m eda_multiphysics.etv_distributed_fs 24 --validate
```

The driver uses interleaved electric-potential and temperature unknowns,
owned-row CSR assembly, and PETSc FieldSplit with a GAMG sub-preconditioner per
field. `--validate` computes the serial SciPy/CoupFE result on rank zero and
prints a relative difference. The public toolchain tests exercise selected
rank counts and a small grid.

The implementation keeps a replicated global solution vector during its
Newton loop. That design bounds its current memory/scaling interpretation even
though matrix rows are distributed.

`eda_multiphysics.etv_distributed` is a separate ASM/GMRES research driver. It
can emit a serial comparison with `--validate`, but it is not the retained
multi-rank release-regression path.

## Local scaling measurements

`eda_multiphysics.scaling_bench` launches repeated FieldSplit runs and formats
their machine-readable `SCALEFS` lines:

```bash
OMP_NUM_THREADS=1 python -m eda_multiphysics.scaling_bench \
  --n 120 --ranks 1,2,4 --oversubscribe
```

The emitted Markdown table is a local measurement. It becomes shareable
performance evidence only when the raw runs and full environment/hardware
metadata are retained. Oversubscribed runs are useful for exercising code paths
and should not be presented as hardware scaling.

## Test command

```bash
python -m pytest -q -m toolchain
```

The toolchain suite covers more than distributed execution, so retain the full
test report and note skips. For a release checkpoint, use the recorder in
`docs/RELEASE_EVIDENCE.md`.

## Current limits

- No public distributed periodic-TSV consumer is qualified.
- No stateful distributed Anand joint solver is included.
- FieldSplit and direct-solve availability depends on the PETSc build.
- Checked-size agreement does not establish convergence for another mesh,
  nonlinear tolerance, material law, or partition.
- Historical timing observations without retained raw output and environment
  metadata are not release evidence.
