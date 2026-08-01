# Solver-scaling benchmark

This directory defines the fixed-size rank sweep for
`eda_multiphysics.etv_distributed_fs`.

- `manifest.json` defines the driver, input-to-DOF relation, measured region,
  required run records, and acceptance checks.
- `historical_unqualified.md` presents all recovered solver/scaling tables and
  their original technical interpretation in one readable record.
- `historical_unqualified.json` preserves transcribed development-era numbers
  in machine-readable form.
- `petsc_coo_gamg_reproducer.py` preserves the standalone diagnostic that
  motivated the owned-row CSR assembly path.

The historical files are rerun targets and design context, not current results.

The recovery search covered the current and historical Git refs, the attached
original and companion EDA checkouts, and the project coordination notes. It
found the tables, explanatory prose, and a generated plot, but no per-run
stdout/stderr, machine inventory, or repeat record. The work is therefore kept
visible and explicitly bounded rather than removed.

No current timing bundle is committed here. Generate a new bundle outside the
source checkout so failed or unreviewed run products do not enter the package:

```bash
OMP_NUM_THREADS=1 OMP_PROC_BIND=true OMP_PLACES=cores \
python -m eda_multiphysics.scaling_bench \
  --n 1580 --ranks 4,8,16,32,48 --repeats 5 --bind-cores \
  --cpu-list 0-47 \
  --machine-label documented-allocation \
  --output-dir /path/outside/the/source/tree/coupfe-eda-scaling-5m
```

With `--cpu-list`, the harness records the exact processor IDs and the
generated Open MPI rankfile that binds each rank to one selected processor.

Before citing a new result, inspect every complete sanitized stream and confirm
the rank placement and allocation boundary. Copy only the reviewed, complete
bundle into this benchmark directory and add it to the static release
inventory. Oversubscribed output is a smoke test only.

See `eda_multiphysics/DISTRIBUTED.md` for the metric boundary, run protocol,
historical tables, and interpretation limits.
