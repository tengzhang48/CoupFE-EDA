# Synthetic PDN integration fixture

This case is a deterministic, project-authored 3×3 resistor grid used as the
a small placement → PDN → thermal → reliability demonstration without
bundling third-party design data. It starts exercising the intended interfaces;
it is not a complete framework, real-chip benchmark, or signoff case.
The next scientific milestone is validation against a lawfully shareable real
device with traceable geometry, materials, loads, boundary conditions, raw
solver evidence, and measured electrical, thermal, or stress observables.

Run `python eda_multiphysics/cases/synthetic_pdn/generate_case.py` from the
repository root to regenerate every CSV, JSON, and SPICE file in this
directory. Generation is deterministic and uses no random seed. The
closed-form voltage reference follows from grid symmetry:
edge-node voltage is `Vdd - 2IR`, and corner voltage is `Vdd - 5IR/2`.
Per-instance power is `Vnode × 1 mA`; the resulting 8.9982 mW load
power plus 1.8 µW grid loss exactly closes to the 9 mW source power.
During the bundled temperature-dependent-resistance demonstration, the solver
recomputes each load's `Vnode × I` heat and resistor loss so that the coupled
thermal input continues to close to the same 9 mW source.
All files are covered by the repository's Apache-2.0 license.

The same versioned file interface accepts caller-supplied exports from
[OpenROAD/OpenDB](https://openroad.readthedocs.io/en/latest/main/src/odb/README.html)
and PDN networks emitted by
[PDNSim `write_pg_spice`](https://openroad.readthedocs.io/en/latest/main/src/psm/README.html).
The plain JSON/CSV/SPICE files show one possible boundary, not a required
standard or a compatibility promise. Other projects may reuse the idea or build
independent workflows around entirely different FEM packages and data models.
For example, users who are entitled to use an upstream design can run and
export the small
[ORFS GCD sanity design](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/c9c22caf9bf9cfe46c5a4236c6ec7e7ae9863cc3/flow/designs/src/gcd)
themselves. We credit the OpenROAD/ORFS contributors for that workflow and the
PyMTL/OpenCelerity contributors identified by its upstream README. CoupFE-EDA
does not bundle that design or its generated outputs.
