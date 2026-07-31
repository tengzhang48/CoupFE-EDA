# Distributed / MPI — scaling the EDA-multiphysics electrical solve on PETSc

Detailed companion to `RESULTS.md`. The serial `eda_multiphysics` suite (53 gates) is the
trust layer; this document covers running the EDA application's electrical solve
**distributed on PETSc/MPI**, why it is correct (the 1-vs-N invariant), how it scales, and
how to extend it.

> **Public-release boundary (2026-07-30):** checked-size correctness is covered at 2 and 4 ranks.
> Historical machine timings and larger-rank records below lack retained raw output and a locked
> environment; they are context, not current performance claims.

---

## 1. Motivation

The power-delivery-network (PDN) IR-drop problem is a sparse SPD linear system — a resistor
graph Laplacian `G V = J` with Dirichlet supply/ground nodes. The serial `pdn_graph.py`
solver (scipy direct) is fine for one block (GCD: 112 nodes; AES: 3 k nodes), but a flagship
SoC PDN is **millions of nodes**. That is exactly the regime PETSc/MPI targets, and it is the
"scale on PETSc/MPI" claim at the heart of CoupFE's positioning (`docs/DESIGN.md`,
`skills/distributed.md`). `eda_multiphysics/pdn_distributed.py` integrates the EDA electrical
solve with that distributed substrate.

---

## 2. The MPI stack (this machine)

| Component | Version / note |
|---|---|
| MPI | Open MPI 4.1.6 (`/usr/bin/mpirun`, `mpicc`); 64 cores; use `--oversubscribe` |
| `mpi4py` | pip, built against the system Open MPI (instant) |
| `petsc4py` | 3.25, built from source into the `coupfe-eda` venv |

PETSc build (minimal, iterative-only — sufficient for CG+GAMG):
```
PETSC_CONFIGURE_OPTIONS="--with-debugging=0 --with-fc=0 --download-f2cblaslapack" \
  pip install petsc petsc4py
```
For the **direct** path (`superlu_dist`, `--direct`), do **not** build PETSc from source —
**conda-forge ships a prebuilt `petsc4py` that already bundles superlu_dist / MUMPS / hypre**:
```
conda install -p <env> -c conda-forge petsc4py mpi4py scipy   # prebuilt, no compile
```
This is the recommended route (the from-source build with `--with-fc=0`/f2c-BLAS does *not*
build superlu_dist cleanly — it wants a real Fortran BLAS). Demonstrated with conda-forge
`petsc4py 3.19` + superlu_dist: `--direct` matches the serial scipy solve to **~6e-13 on the
real AES PDN** (the direct-solver roundoff floor; on a *large ill-conditioned* grid two
different direct factorizations — scipy SuperLU vs superlu_dist — agree only to ~5e-11, a
conditioning limit, not a solver bug).

> When running from a conda env that has coupfe pip-installed editable, the editable finder can
> shadow the sibling `eda_multiphysics/` package — run with `PYTHONPATH=<repo root>` (exposes
> both `coupfe/` and `eda_multiphysics/`) and `mpiexec -x PYTHONPATH`.
`pdn_distributed` needs the `[petsc]` extra (`petsc4py` + `mpi4py`); the **53 self-contained
gates do not** — they stay numpy+scipy+coupfe so CI/anyone can run them anywhere.

---

## 3. The distributed algorithm (`pdn_distributed.py`)

Mirrors CoupFE's `coupfe/assembly/distributed.py` pattern (`skills/distributed.md`):

1. **Partition** — PETSc owns a contiguous node range per rank (`A.getOwnershipRange()`).
2. **Assemble, memory-distributed** — each rank stamps only the resistor edges whose *first*
   node it owns (so every edge is added exactly once). Off-process stencil entries (the other
   endpoint on another rank) are routed by PETSc on `A.assemble()` via `ADD_VALUES`. No rank
   builds the global matrix.
3. **Symmetric Dirichlet** — `A.zeroRowsColumns(rows, diag=1, x, b)` eliminates the supply and
   ground rows *and columns*, keeping the Laplacian **SPD** (so CG is valid) and folding the
   prescribed potentials into the RHS. (A plain `zeroRows` would break symmetry → CG fails.)
4. **Solve** — `KSP`:
   - default: **CG + GAMG** (algebraic multigrid) — the right iterative solver for a PDN
     Laplacian; final-revision size/rank sweeps are required before claiming
     mesh- or rank-independent iterations.
   - `--direct`: **`preonly` + LU + `superlu_dist`** — a reproducible distributed direct solve
     for exact (machine-precision) 1-vs-N.
5. **Gather + compare** — `Scatter.toZero` brings the solution to rank 0, where it is checked
   against the serial scipy solve.

---

## 4. The 1-vs-N invariant (why it is the gate)

A distributed result must equal the serial result. This is the single most important
correctness signal for distributed FE (`skills/distributed.md`): *"Never claim parallel works
from a single rank count, a loose tolerance, or a serial-only test."* So every run gathers the
N-rank solution and compares to the independent serial scipy solve at multiple rank counts.

Two tolerance regimes:
- **Iterative (CG+GAMG):** matches serial to the **KSP `rtol`** (~1e-11 here) — the iterative
  method converges to the same solution regardless of rank count.
- **Direct (`superlu_dist`):** matches serial to **machine precision** (~1e-15) — a reproducible
  factorization. Use this for the tight gate; MUMPS is *not* reproducible run-to-run on
  near-singular modes (`skills/distributed.md`), so `superlu_dist` is the right direct solver.

A **rank-independent iteration count** is the healthy preconditioner signal; a rank-*dependent*
count flags a distributed-state or PC bug.

---

## 5. Results

**CoupFE's own distributed path** (verified first, machine precision):

| smoke | what | serial == 2-rank |
|---|---|---|
| `examples/mpi_smoke/distributed_residual.py` | distributed assembly | **1.78e-15** |
| `examples/mpi_smoke/distributed_solve.py` | PETSc KSP solve | **1.67e-15** (16 CG its) |

**Distributed PDN** (`pdn_distributed.py`, CG+GAMG):

| case | nodes | edges | ranks | iters | wall | serial == N-rank |
|---|---|---|---|---|---|---|
| grid 120² | 14 400 | 28 560 | 1/2/4 | 13/13/12 | 0.13→0.07 s | ~3e-11 |
| grid 400² | 160 000 | 319 200 | 1/2/4 | 16/15/15 | 1.57→0.67 s (**2.3×**) | ~3e-11 |
| **grid 1000²** | **1 000 000** | 1 998 000 | 4 | 18 | **4.3 s** | 9e-11 |
| external AES PDN (historical; inputs not bundled) | 3 089 | 3 447 | 1/2 | 20/16 | 0.02 s | 3e-11 |

Notes:
- The historical AES-derived run recorded serial/MPI agreement at
  8.0099e-4 V. Because the input and raw logs are absent, it is not current
  real-device validation.
- The historical 1M-node run is a rerun target, not a current performance claim.
- Wall time is the distributed-*solve* only (the serial oracle is computed afterwards on rank 0).

---

## 6. Run it

```
conda activate coupfe-eda
mpirun -n 4 python -m eda_multiphysics.pdn_distributed 400        # 160k-node grid
mpirun -n 4 python -m eda_multiphysics.pdn_distributed 1000       # 1M-node grid
mpirun -n 2 python -m eda_multiphysics.pdn_distributed \
       /path/to/pdn_vdd.sp                                        # caller-supplied exported PDN
mpirun -n 4 python -m eda_multiphysics.pdn_distributed 400 --direct  # superlu_dist, exact
```

---

## 7. How to extend

- **Machine-precision gate** — with `superlu_dist` (Section 2), `--direct` gives exact 1-vs-N;
  wrap a small case as a `[petsc]`-gated regression test.
- **Distributed coupled electrothermal** — the staggered scheme already distributes (each
  single-field stage is a distributed Laplacian solve like this one); the *monolithic* coupled
  solve wants PETSc `PCFieldSplit` (tracked in `docs/capabilities.md`).
- **Real flagship PDN** — run a larger OpenROAD design (Ibex/SKY130) through the flow, export
  `write_pg_spice`, and feed it here; the loader (`build_from_spice`) already handles real nets.
- **Memory-local generation** — for true multi-million-node scaling, generate each rank's block
  on the fly (never build the global edge list), as CoupFE's mesh distribution does
  (`docs/dev/distributed_mesh.md`). The current loader replicates the edge list per rank (fine
  to ~1M; the assembly loop, not memory, is then the bottleneck).

---

## 8. Honest limitations

- Two builds were used: a from-source `petsc4py` in the pip venv (iterative-only — superlu_dist
  did not build under the minimal no-Fortran config), and the **conda-forge `petsc4py`** (bundles
  superlu_dist) in the EDA conda env, which runs the `--direct` path (Section 2). The conda route
  is the recommended one for the direct solver.
- The edge list is **replicated per rank** and the assembly loop is `O(edges)` per rank (a
  serialization); the KSP solve scales, the assembly does not. True scaling beyond ~1M nodes
  needs memory-local generation (Section 7).
- Single-field (electrical) only in *this* module; the coupled solve is below.

## 9. Distributed NONLINEAR COUPLED solve (`etv_distributed.py`)

The PDN above is one linear scalar field. The harder case — done with CoupFE's full
compiled+distributed machinery — is the **two-field, nonlinear, coupled electro-thermal** solve:

- element: a **compiled f2py kernel generated from the weak form** by `coupfe.codegen`
  (`etv_kernel.py`; φ flux = σ(T)∇φ, T flux = −k∇T, storage = −σ|∇φ|² Joule), driven **batched** via
  `ElementGroup` — no Python element loop, full coupled complex-step tangent.
- solve: CoupFE's `solve_distributed` (load-stepped Newton + KSP, ghosted U via VecScatter).
- correctness: **serial==N-rank to 5.2e-11** at 526k DOF; σV0²/8k to 2e-16.

**Strong scaling** (526,338 DOF, 2D Quad4, ASM+GMRES):

| ranks | 8 | 16 | 32 |
|---|---|---|---|
| wall (s) | 88.8 | 47.4 | 27.8 |
| speedup | 1.0× | 1.87× | **3.19×** |

The historical snapshot interpreted ASM as giving near rank-independent
iterations and 80% efficiency to 32 ranks; this must be rerun. **PC note:**
scalar-elliptic **GAMG mis-coarsens the interleaved 2-field block** (the serial==N-rank gate caught
it); ASM works but has no coarse grid, so iterations grow with problem size (~340@132k → ~1200@526k).
**FieldSplit (GAMG per field)** is the implementation intended for the next
scaling study; 1M+ behavior is not currently qualified. All recorded runs were
**2D**; 3D Hex8 is a later step.
Run: `OMP_NUM_THREADS=1 mpirun -n 8 python -m eda_multiphysics.etv_distributed 512 [--validate]`.
- `etv_distributed` above uses ASM (the PC `solve_distributed` offers for coupled fields);
  use the FieldSplit driver below for future retained scaling measurements.

### Historical distributed FieldSplit 5M-DOF record (`etv_distributed_fs.py`)

The FieldSplit implementation is wired into a custom distributed solve
(`solve_distributed` is single-field/ASM; this driver uses vectorized assembly
and its own KSP). Two design points:

- **PCFIELDSPLIT, GAMG per scalar field** — splits the interleaved (φ,T) system
  so GAMG sees a scalar elliptic operator. The historical record reported about
  18 iterations; mesh/rank independence and the comparison with ASM require a
  retained final-revision rerun.
- **Fully vectorized assembly, no Python per-element loop.** Node-aligned row partition; each rank
  evaluates the elements touching its owned nodes (owned + 1 ghost layer) in one batched
  `element_rk_batch` call; keeps owned-row triplets; builds a local CSR with `scipy` and
  `createAIJ(csr=)` → plain AIJ, no off-process routing. The obvious `setValuesCOO` shortcut is
  **avoided** — it corrupts global PETSc state across repeated solves (1st solve converges, 2nd+
  fail; Newton diverges), a confirmed upstream bug reproduced pure-petsc4py on PETSc 3.24.2 +
  3.25.2 (`docs/petsc_coo_gamg_bug_repro.py`). The historical record measured
  **7× faster** assembly than the per-element `setValues` stamp loop; that
  performance number is also a rerun target.

**Historical, unqualified strong-scaling record — fixed 4,999,122 DOF**
(2D Quad4, nonlinear α=0.05; wall = solve only):

| ranks | 4 | 8 | 16 | 32 | 48 |
|---|---|---|---|---|---|
| wall (s) | 87.7 | 48.3 | 26.1 | 18.2 | 14.7 |
| speedup (vs 4) | 1.0× | 1.81× | 3.36× | 4.80× | **5.98×** |
| KSP iters | 18 | 19 | 18 | 18 | 18 |

The table records a reported 14.7 s solve at 48 cores and serial/MPI agreement to 1e-16.
The raw stdout, machine inventory, and locked environment were not retained, so timing, speedup,
and the 1–48-rank headline are **withheld as public-release claims**. The values remain historical
context only.
Run: `OMP_NUM_THREADS=1 mpirun -n 48 python -m eda_multiphysics.etv_distributed_fs 1580`.

> `scaling_bench` can run a new `mpirun` sweep and parse the driver's
> `SCALEFS <ndof> <ranks> <wall> <iters>` line:
> `OMP_NUM_THREADS=1 python -m eda_multiphysics.scaling_bench --n 1580 --ranks 4,8,16,32,48`
> (quick smoke: `--n 120 --ranks 1,2,4 --oversubscribe`). Archive its raw output, hardware and
> topology, tool versions, and locked environment before replacing this historical record.
