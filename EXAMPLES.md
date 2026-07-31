# Examples — runnable demos

Most demos are the `__main__` of an `eda_multiphysics` module; release-oriented composed cases live
under `examples/` with reviewable inputs and expected evidence. This catalogs them by theme, with
what each shows and what it needs. The per-entry-point provenance and public-claim status are in
[`examples/REFERENCES.md`](examples/REFERENCES.md). **Setup:** create/activate `environment.yml`,
run `./setup.sh`, and invoke commands from the repository root. No machine-specific `PYTHONPATH`
is required.

**Dependency tiers:** 🟢 numpy/scipy/coupfe only · 🟠 needs the compiled/mesh toolchain
(`gmsh` + `petsc4py` + `gfortran`) · 🔴 needs the EDA toolchain (OpenROAD/PDNSim — easiest via the
[container](CONTAINER.md)).

## Start here — the trust suite
| Command | Shows | Tier |
|---|---|---|
| `python -m eda_multiphysics.run` | **53 fast gates** — published/analytic oracles, independent comparisons, invariants, and contracts, with broken controls where meaningful (~30 s historical local runtime) | 🟢 |
| `pytest -m toolchain` | **19 toolchain tests** — compiled 3D, conformal geometry, anisotropic TSV, thermo-mechanical, reliability, and MPI paths (~5 min) | 🟠 |
| `python -m eda_multiphysics.validate` | The 11-check electrothermal validation ladder | 🟢 |

## Capstone & design integration
| Command | Shows | Tier |
|---|---|---|
| `python -m eda_multiphysics.reliability_pipeline` | Capstone IR→ΔT→stress→life→EM chain on a bundled project-authored synthetic case; graph voltage checked against a closed-form reference | 🟢 |
| `python -m eda_multiphysics.reliability_3d [design] [--shape cylinder\|barrel\|hourglass] [--package]` | Parametric joint or conformal solder/underfill/UBM/pad model → 3D-FE fatigue; bundled design mode uses a labeled nine-point synthetic proxy | 🟠 |
| `python examples/tsv_00_device_screening/run.py` | Fixed 10 µm TSV → 32 synthetic stable device IDs → published n/p mobility proxy → KOZ flags and an orientation action; Lamé stress preview, explicitly not Raman validation | 🟢 |
| `python -m eda_multiphysics.electrothermal_chip` / `.chip_vtu` | Coupled R(T) and full V–T–u chain on a caller-supplied, lawfully sourced case | 🔴 |
| `python -m eda_multiphysics.case_thermal [-o output.csv]` / `.design_loop_demo` | Synthetic or caller-supplied placement case → thermal map with provenance-tagged back-annotation; the separate synthetic design-loop demo checks a same-current hotspot/IR improvement | 🟢 |

The bundled case contains no third-party design data. The same case interface accepts
caller-owned OpenROAD/OpenDB placement and PDNSim `write_pg_spice` exports; see
[`THIRD_PARTY.md`](THIRD_PARTY.md).

## 3D FE on generated device-relevant geometry (gmsh-meshed)
| Command | Shows | Tier |
|---|---|---|
| `python -m eda_multiphysics.tsv_3d` | Hex8 electro-thermal on a cylindrical TSV / annular via / layer stack (heat-gen + composite-cylinder oracles) | 🟠 |
| `python -m eda_multiphysics.tet_3d` | Tet4 electro-thermal on generated all-tet box + cylinder; claim withheld until the final core pin contains both native Tet4 and MPC and is requalified | 🟠 |
| `python -m eda_multiphysics.thermomech_3d` / `.thermomech_tsv` | Monolithic u+T Hex8; Cu/Si TSV thermal-mismatch stress vs composite-cylinder | 🟠 |
| `python -m eda_multiphysics.etv_3d` | 3D Hex8 coupled electro-thermal (FieldSplit-solved) | 🟠 |

## Distributed / scaling (PETSc/MPI)
| Command | Shows | Tier |
|---|---|---|
| `mpirun -n 4 python -m eda_multiphysics.pdn_distributed 1000` | Requests a synthetic **1M-node** PDN electrical solve; runtime/performance is machine-specific | 🟠 |
| `mpirun -n 8 python -m eda_multiphysics.etv_distributed_fs 512 --validate` | Generates a new distributed FieldSplit solve and serial-versus-rank comparison | 🟠 |
| `python -m eda_multiphysics.scaling_bench --n 1580 --ranks 4,8,16,32,48` | Generates a new machine-specific scaling table; the historical 5M-DOF timing claim is withheld until raw output and environment evidence are archived | 🟠 |
| `python -m eda_multiphysics.etv_fieldsplit` / `.etv_distributed` | Serial FieldSplit and ASM distributed research drivers; performance requires a retained final-revision rerun | 🟠 |

## Viscoplastic reliability
| Command | Shows | Tier |
|---|---|---|
| `python -m eda_multiphysics.anand` / `.anand_3d` | Anand model vs closed-form saturation; the 3D Hex8 element (transient and BVP); in-sample reproduction of the measured 4719-cycle calibration case | 🟢 |
| `python -m eda_multiphysics.solder_joint` | 2D plane-strain viscoplastic joint → volume-averaged damage and calibration-specific Darveaux life | 🟢 |
| `python -m eda_multiphysics.etv_solder` | Electro-thermo-viscoplastic study (the τ/period coupling finding) | 🟢 |
| `python -m eda_multiphysics.creep` / `.electromigration` | Stress-controlled creep; Black + Blech EM reliability | 🟢 |

## Individual physics (each vs its oracle)
`capacitance` (ε·A/d) · `thermal_runaway` (saddle-node) · `transient` ((π/L)²α) · `thermomech`
(Timoshenko / T&G) · `tsv_stress` (Lamé) · `pdn_graph` (vs scipy) — all 🟢,
`python -m eda_multiphysics.<name>`.

## Codegen internals (build a compiled element from a weak form)
`etv_kernel` / `thermomech_kernel` (generate + f2py-compile the coupled element), `etv_fe`
(monolithic FE element on the operator contract) — 🟠. See [`skills/SKILL.md`](skills/SKILL.md) for
the authoring recipe.

---
Core numerical claims are pinned by gates in `eda_multiphysics/gates.py` (fast) or
`tests/test_toolchain.py` (toolchain). Integration/CLI and TSV-device behavior have additional coverage in
`tests/test_integration_regressions.py` and `tests/test_tsv_device.py`; a green kernel gate does not imply that every line of CLI
formatting is frozen. See [`docs/VALIDATION_GUIDE.md`](docs/VALIDATION_GUIDE.md) and the
[reference/status map](examples/REFERENCES.md).
