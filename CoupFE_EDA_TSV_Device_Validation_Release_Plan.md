# CoupFE-EDA Multilevel TSV-to-Device Validation and Release Plan

**Proposed release scope:** experimentally anchored, one-way multilevel analysis from TSV thermomechanics to silicon near-surface stress, compact mobility/keep-out-zone (KOZ) mapping, and EDA back-annotation.

**Target public claim after every mandatory gate passes:**
*CoupFE-EDA provides a validated research workflow for multilevel TSV thermomechanics and
device-impact screening.* This is not a claim for the current release candidate.

**Claims that should not be made in the first release:** foundry signoff, quantitative transistor-delay prediction for an arbitrary process, Cu protrusion prediction, interface-fracture prediction, or fatigue-life prediction.

## Implementation status amendment — 13 July 2026

The architecture and release gates below are accepted as the target contract, with two clarifications:

1. completing WP0–WP7 is a release program, not a single implementation increment; and
2. the repository must remain labeled an **alpha numerical/device-screening prototype** until every
   mandatory scorecard category passes. A device-scale preview is valuable, but it does not satisfy
   the Raman or curvature experimental gates.

The first implemented tranche now provides:

- packaged schema-v1 TSV scene, material, and validation-manifest definitions;
- frozen source/geometry/thermal-history manifests for curvature, Raman, mobility/KOZ, and the
  planned MORE-Stress comparison, with missing digitized curves explicitly blocking release;
- cubic (001) silicon stiffness and crystal-rotation utilities with fourfold-symmetry and
  thermal-free-expansion tests;
- the exact Raman stress-sum observable and the published n/p piezoresistive tensor-rotation model;
- a conformal blind Cu/oxide-cup/anisotropic-Si Tet4 local solver foundation with zero direct Cu/Si
  contact, full stress recovery, exact-depth Raman sampling, and frame/input provenance, still
  labeled non-validation;
- a full 40/50 µm Jiang periodic-cell foundation with matching opposite faces, exact serial affine
  MPC, homogeneous free-expansion/fixed-box controls, and heterogeneous equilibrium; the
  source-equivalent macro/bottom BC, corrected-scene convergence, and distributed TSV MPC remain
  open. CoupFE's smaller bulk/history-free MPI reference is independently 1/2/4-rank gated but is
  not yet a scalable or TSV-consumer claim;
- stable upstream source-object/device/TSV ID back-annotation, user-selected KOZ thresholds, and
  channel-orientation screening; and
- a device-scale-dimension 10 µm TSV / −250 °C / 32-site synthetic demonstration with CSV/JSON/SVG back-annotation,
  driven by the validated classical Lamé far-field stress proxy.

The demonstration is intentionally labeled a proxy. Matching periodic geometry and serial exact-MPC
assembly are now qualified foundations. Release remains blocked on a source-equivalent macro/bottom
setup and corrected-scene mesh/domain qualification of the anisotropic free-surface 3-D FE,
digitized curvature and specimen-C/D Raman curves, conservative global-local
transfer, full-versus-reduced array comparison, external comparison, and OpenDB round-trip evidence.
Machine-readable status is in `benchmarks/tsv_release_scorecard.json`.
The concise periodic-support matrix and latest execution record are in
`docs/PERIODIC_MPC_STATUS.md`.
The ordered implementation plan for the next tranche is
`docs/TSV_ANISOTROPIC_3D_PLAN.md`; the reusable core/EDA periodic-constraint design is
`docs/PERIODIC_BOUNDARY_CONDITION_PLAN.md`.

---

## 1. Executive decision

The TSV example is promising because it can exercise the part of CoupFE-EDA that is currently missing but most valuable: model hierarchy, global-local transfer, device-level interpretation, and EDA back-annotation. The first release should not attempt a fully coupled package-to-TCAD solution. It should implement a controlled one-way hierarchy:

\[
\text{die / TSV-array loading}
\rightarrow
\text{global thermomechanics}
\rightarrow
\text{local TSV submodel}
\rightarrow
\text{near-surface Si stress}
\rightarrow
\text{mobility / KOZ proxy}
\rightarrow
\text{EDA constraint}.
\]

The release must be blocked unless the implementation passes both **independent experimental validation** and **numerical multiscale validation**. Reproducing only a published finite-element contour is insufficient.

---

## 2. Validation evidence available

### 2.1 Global experimental anchor: bending-beam curvature

Ryu et al. measured curvature during thermal cycling of periodic blind Cu TSV arrays. The specimen used 10 micrometer diameter, 55 micrometer deep TSVs in a 700 micrometer Si wafer, with 40 and 50 micrometer pitches in the two in-plane crystal directions. Stabilized cooling and subsequent cycles were approximately linear, while the first heating cycle contained stress relaxation and microstructural evolution.

**Use in CoupFE-EDA:** validate the global averaged thermomechanical response and the chosen stress-free/reference temperature. The first release should use the stabilized linear branch only.

### 2.2 Local experimental anchor: micro-Raman stress

Jiang et al. measured the near-surface silicon stress around the same class of TSV arrays using micro-Raman spectroscopy and compared the measurements with 3D FEA. Under the (001) backscattering configuration, the reported observable is

\[
\sigma_r+\sigma_\theta\;(\mathrm{MPa})=-470\,\Delta\omega_3\;(\mathrm{cm}^{-1}).
\]

The Raman penetration depth was approximately 0.2 micrometers, so the numerical observable must be extracted 0.2 micrometers below the free surface. For a thermal load of -270 degrees C, the paper reports a positive peak of about 90 MPa roughly 10 micrometers from the Cu/Si interface along [110].

**Use in CoupFE-EDA:** this is the most important release-blocking experiment because it validates the local field that drives the device metric.

### 2.3 Device-impact benchmark: piezoresistive mobility and KOZ

The Jiang/Ryu studies provide silicon piezoresistive coefficients, tensor-rotation rules, mobility maps, and KOZ examples. In the primary Ryu 2012 paper, the stated isolated 10 µm TSV case at -250 degrees C gives approximately 61% maximum change for n-type [100], p-type [100] below the 5% threshold, n-type [110] below 5%, and up to approximately 63% for p-type [110]. The array example with pitch/diameter = 3 shows interaction and merged, anisotropic n-type KOZ regions. The previously proposed 67.94%/3.45% pair could not be traced to the cited primary paper and is not a release oracle.

**Use in CoupFE-EDA:** reproduce the published mobility/KOZ calculation as a model-verification benchmark. This is not an independent transistor experiment and must be labeled accordingly.

### 2.4 Multiscale numerical benchmarks

Three useful comparisons are available:

- Jung et al. compared linear stress superposition with full FEA and documented where simple superposition is accurate and where it deteriorates.
- Wu et al. proposed an inter-scale method using local-model sharing and reported stress errors below 1.63% for a representative test while using a small fraction of the full-FEA cost.
- MORE-Stress is open source and reports less than 1% error, 153-504x time reduction, and 39-115x memory reduction relative to ANSYS for large TSV arrays.

**Use in CoupFE-EDA:** full resolved CoupFE-EDA models remain the primary numerical oracle; at least one canonical case should also be compared with an independent open implementation such as MORE-Stress.

### 2.5 Important scope warning: Cu process history and plasticity

NIST synchrotron measurements on 3, 5, and 8 micrometer Cu TSVs show that internal Cu stress and protrusion do not follow a simple monotonic diameter law. Microstructure, defects, annealing, plasticity, and stress relaxation matter. Therefore, a linear thermoelastic model can support stabilized silicon stress and KOZ screening, but it should not claim general prediction of Cu internal stress or protrusion.

---

## 3. Release architecture

### Level 0 - EDA and geometry semantics

Inputs:
- TSV identities, coordinates, diameters, pitches, and array membership;
- die surface and crystal orientation;
- transistor/cell coordinates and channel orientation;
- material and thermal-history manifest;
- global temperature or package displacement field.

Outputs:
- stable object IDs preserved through all levels;
- unit and coordinate metadata;
- a reproducible benchmark manifest.

### Level 1 - Global die / array model

Purpose:
- capture nonuniform die-scale thermal loading and background deformation;
- avoid explicit fine resolution of every TSV;
- identify regions requiring detailed local analysis.

Models:
- homogenized TSV-array region, reduced basis, or response library;
- anisotropic silicon;
- coarse Hex8/Tet4 thermomechanics.

### Level 2 - Detailed TSV submodel

Required geometry:
- Cu core;
- oxide liner;
- anisotropic (001) Si;
- free surface;
- neighboring TSVs when interaction is important.

Required outputs:
- full stress tensor at the device layer;
- Raman observable at 0.2 micrometers below the surface;
- displacement and reaction balance;
- uncertainty and mesh-convergence data.

### Level 3 - Device proxy

Required functions:
- stress-tensor rotation into channel coordinates;
- n-type and p-type piezoresistive mapping;
- user-selectable mobility threshold;
- anisotropic KOZ boundary extraction.

The first release should not contain a foundry-specific delay model. It should expose an API through which a client can supply a calibrated stress-to-device model.

### Level 4 - EDA back-annotation

Outputs:
- per-cell/device stress tensor;
- mobility-change proxy;
- KOZ violation flag;
- distance and direction to governing TSV;
- JSON/CSV/VTK results and an OpenDB-compatible adapter;
- one deterministic design-action demonstration.

---

## 4. Work packages and release gates

## WP0. Evidence freeze and benchmark manifest

**Tasks**
1. Create versioned benchmark definitions for the curvature, Raman, isolated-TSV mobility, TSV-array KOZ, and multiscale cases.
2. Record DOI, figure/table number, geometry, material properties, thermal history, coordinate conventions, extraction depth, digitization uncertainty, and excluded regions.
3. Store only machine-readable values and scripts needed for comparison; do not redistribute copyrighted page images.
4. Define a calibration/validation split before solving the cases.

**Mandatory release gates**
- Every benchmark quantity has units, source, uncertainty, and a machine-readable schema.
- All benchmark plots can be regenerated from a clean checkout.
- No parameter is silently fitted after viewing a validation result.
- A benchmark manifest hash is written into every result directory.

**Block release if**
- the exact thermal reference state or coordinate convention cannot be reconstructed;
- published curves are compared visually without digitized data and an error metric.

---

## WP1. Isolated TSV numerical foundation

**Tasks**
1. Implement anisotropic silicon elasticity with explicit crystal-to-global rotation.
2. Construct a 3D Cu/oxide/Si TSV with a free surface.
3. Add structured Hex8 and independent Tet4 meshes.
4. Add exact patch, rigid-body, thermal-expansion, and cylindrical far-field tests.
5. Add serial-versus-MPI invariance tests.

**Mandatory release gates**
- Constant-strain and uniform-thermal-expansion tests: relative residual and field error <= 1e-10.
- Rigid-body mode produces no spurious stress to <= 1e-10 of the characteristic stress.
- Mesh refinement changes the Raman stress observable by <= 2% on the two finest meshes.
- Hex8 and Tet4 results differ by <= 3% for the same device-layer quantity of interest.
- Serial and N-rank values of all reported scalar quantities differ by <= 1e-9 relative.
- Rotating the cubic crystal by 90 degrees produces the expected fourfold symmetry to <= 1%.

**Stretch target**
- device-layer stress quantity converges within 1% and exhibits the expected element-order trend.

---

## WP2. Global experimental validation by curvature

**Tasks**
1. Reproduce the Ryu/Jiang bending-beam specimen and TSV-array geometry.
2. Model the measured reference specimen consistently.
3. Use the measured stress-free/reference temperature.
4. Compare only stabilized cooling/subsequent-cycle branches in the first release.
5. Report sensitivity to beam thickness, TSV volume fraction, oxide thickness, and reference temperature.

**Mandatory release gates**
- Correct curvature sign and correct zero-crossing behavior.
- Reference-temperature prediction within 10 degrees C of the measured zero-curvature temperature when it is not imposed; if imposed from experiment, clearly label it as an input.
- Normalized root-mean-square error of the stabilized curvature branch <= 20%.
- Predicted stabilized slope within 25% of the digitized experimental slope.
- Refining the global model changes the slope by <= 5%.
- No material parameter is retuned separately for different thermal cycles.

**Stretch target**
- curvature-branch NRMSE <= 10%.

**Block release if**
- agreement requires modeling the first heating cycle as linear elastic;
- each specimen requires a different fitted Cu modulus, CTE, or arbitrary reference temperature.

---

## WP3. Local experimental validation by micro-Raman stress

**Tasks**
1. Reproduce specimens C and D using the published geometry and thermal references.
2. Compute the exact measured quantity, not von Mises stress.
3. Extract the field 0.2 micrometers below the free surface.
4. Compare along the same crystallographic scan direction and pitch geometry.
5. Quantify uncertainty from digitization, Raman spatial resolution, mesh size, and uncertain material parameters.
6. Keep an isotropic-silicon calculation as a negative control.

**Mandatory release gates**
- Correct sign and qualitative shape of the stress curve for both thermal loads.
- Peak location within 2 micrometers of the digitized experimental peak.
- Peak magnitude within 20% of experiment for each specimen.
- Curve NRMSE <= 20% over the resolvable silicon region.
- Ratio of the high-load to low-load response within 15% of the experimental ratio.
- Fourfold symmetry error <= 3% for the ideal symmetric geometry.
- The isotropic-Si negative control must be distinguishable from the accepted anisotropic result.
- All comparison masks, including exclusions close to the Cu/Si interface, are fixed before calculating the error.

**Stretch target**
- peak and curve errors <= 10-12%.

**Block release if**
- the model is tuned to specimen C and separately retuned to specimen D;
- comparison is made at the surface rather than the Raman sampling depth;
- only von Mises stress is reported.

---

## WP4. Multilevel global-local transfer and reduced model

**Tasks**
1. Define independent global and local meshes.
2. Implement temperature, displacement, and traction transfer with explicit unit and coordinate metadata.
3. Implement one reduced representation: response basis, reduced-order model, or shared local TSV library.
4. Test isolated, regular-array, irregular-array, and nonuniform-background-loading cases.
5. Compare against fully resolved CoupFE-EDA models.
6. Run one external comparison with MORE-Stress or another independent implementation.

**Mandatory release gates**
- Rigid translation, rigid rotation, and affine displacement transfer reproduce the exact field to <= 1e-10.
- Constant and linear temperature fields transfer to <= 1e-10.
- Global-local virtual-work mismatch <= 1e-6 relative.
- Resultant force and moment mismatch <= 1e-6 relative.
- Device-layer stress-tensor L2 error <= 5% outside a predeclared interface/singularity mask.
- 95th-percentile pointwise stress error <= 10% outside the mask.
- Mobility-proxy L2 error <= 5%.
- KOZ-boundary Hausdorff distance <= max(1 micrometer, 0.1 TSV diameter).
- Submodel-boundary enlargement changes the device metric by <= 3%.
- For a 20x20 array, wall-time speedup >= 10x and peak-memory reduction >= 5x relative to the fully resolved reference at matched local fidelity.

**Stretch target**
- <2% device-metric error, >=50x speedup, and >=10x memory reduction.

**Block release if**
- stresses are transferred by nearest-neighbor copying without a conservation or virtual-work test;
- accuracy is reported only as a contour-image comparison;
- speedup is obtained by reducing local mesh fidelity in the reduced model.

---

## WP5. Device mobility and KOZ mapping

**Tasks**
1. Implement the published n-type and p-type piezoresistive coefficients with strict unit tests.
2. Implement full tensor and coefficient rotation for [100], [010], [110], and [1-10] channel directions.
3. Reproduce the isolated-TSV mobility maps.
4. Reproduce the pitch/diameter = 3 array-interaction and merged-KOZ example.
5. Add threshold-independent output, so users can choose their own allowed mobility change.

**Mandatory release gates**
- Coefficient and stress-unit conversions are exact to machine precision.
- Symmetry and rotation identities pass to <= 1e-10.
- Published isolated-TSV maximum mobility changes are reproduced within 5% after matching the stated model.
- KOZ threshold-crossing distances are reproduced within max(1 micrometer, 10%).
- The merged n-type KOZ topology for pitch/diameter = 3 is reproduced.
- The p-type case correctly remains below the 5% threshold for the published [100] example.
- Documentation labels this stage as literature-model reproduction, not independent transistor validation.

**Stretch target**
- reproduce additional channel orientations or an independent electrical-sensor study without refitting.

---

## WP6. EDA-aware example and closed design action

**Tasks**
1. Import or create an OpenDB/DEF block containing a TSV array and nearby standard-cell instances.
2. Preserve cell ID, location, orientation, TSV identity, layer, and coordinate transform.
3. Back-annotate stress and mobility proxies.
4. Implement one design action: move, reorient, or exclude cells; alternatively alter TSV pitch/placement.
5. Re-run the analysis and verify the improvement.

**Mandatory release gates**
- 100% of TSV and cell IDs round-trip through the workflow.
- Coordinate round-trip error <= 0.1 micrometers or 0.01 TSV diameter, whichever is larger.
- Total mapped-device count and violation count are deterministic across repeated runs.
- The redesigned case reduces the weighted KOZ-violation metric by >= 50%.
- The maximum mobility-change proxy is reduced by >= 25%, unless the example explicitly demonstrates a Pareto tradeoff.
- The redesign introduces no overlaps or invalid placement.
- Any area, displacement, or wirelength-proxy penalty is reported; no uncalibrated timing claim is made.
- A quick version completes in <= 15 minutes on a documented workstation, while a full validation version is separately provided.

---

## WP7. Release engineering and evidence package

**Tasks**
1. Provide a one-command environment or container.
2. Separate quick tests from long validation/regression tests.
3. Generate a machine-readable evidence report.
4. Document assumptions, known limitations, and failure modes.
5. Publish exact commands for reproducing every figure.
6. Add release artifact checks and API stability tests.

**Mandatory release gates**
- Clean Linux installation succeeds from the published instructions.
- All quick tests pass in CI.
- All release-blocking validation cases pass on a clean machine.
- Every published result carries code revision, mesh revision, material-manifest revision, and benchmark-manifest hash.
- No proprietary or unlicensed benchmark asset is included.
- Documentation explicitly states: experimental research workflow, not foundry signoff.
- The release contains a failure report template; failed evidence is not hidden.

---

## 5. Release tiers

### v0.1 - TSV multilevel technical preview

**Required**
- WP0 through WP7 completed at the mandatory-gate level.
- One global curvature experiment passed.
- Two Raman thermal-load cases passed without retuning.
- Full-FE versus multilevel comparison passed.
- Mobility/KOZ literature reproduction passed.
- One EDA back-annotation and redesign example passed.

**Allowed public claims**
- experimentally anchored global and local silicon stress;
- verified multilevel TSV analysis;
- literature-based mobility and KOZ screening;
- EDA-aware back-annotation.

### v0.5 - Research release

**Additional requirements**
- comparison with MORE-Stress or another independent code;
- at least one second geometry/pitch not used in development;
- uncertainty propagation for reference temperature, material properties, and geometry;
- distributed 3D array/submodel demonstration;
- one external user reproduces the benchmark suite.

### v1.0 - Industry-facing research platform

**Additional requirements**
- a partner-provided measured test vehicle or independent electrical-sensor dataset;
- calibrated technology-specific stress-to-device model;
- documented parameter-identification and held-out validation;
- qualification levels and provenance for all properties;
- stable plugin API for proprietary device models.

---

## 6. Explicitly postponed items

The following should not block v0.1:

- Cu crystal plasticity;
- Cu protrusion;
- interface delamination or fracture;
- fatigue life;
- full TCAD coupling;
- foundry-specific cell delay;
- full-package CAD;
- monolithic package-to-device coupling.

A later Cu-plasticity extension should use the NIST synchrotron and AFM measurements as experimental anchors. It must be released as a separate capability because it requires process-history, microstructure, and annealing information that are not part of the first thermoelastic scope.

---

## 7. Failure and claim-downgrade rules

The release should be delayed or relabeled as an alpha numerical prototype if any of the following occurs:

1. The Raman stress curves fail the mandatory error limits.
2. Validation requires independent parameter tuning for each experiment.
3. Global-local transfer violates force, moment, or virtual-work conservation.
4. Device metrics change by more than 3% when the submodel boundary is moved outward.
5. Mobility results are generated without tensor rotation for the stated crystal/channel orientation.
6. The multilevel model is not faster than the full model at equal local fidelity.
7. Published benchmark data or assumptions cannot be traced to their source.
8. Results depend materially on undocumented process history.

---

## 8. Recommended repository structure

```text
examples/
  tsv_00_patch_and_rotation/
  tsv_01_isolated_analytical/
  tsv_02_curvature_experiment/
  tsv_03_raman_experiment/
  tsv_04_array_full_vs_multilevel/
  tsv_05_mobility_koz/
  tsv_06_openroad_backannotation/

benchmarks/
  tsv_curvature_ryu2012/
  tsv_raman_jiang2013/
  tsv_mobility_koz_jiang2013/
  tsv_more_stress_2025/

schemas/
  physical_scene_tsv.schema.json
  tsv_material_manifest.schema.json
  validation_manifest.schema.json

tests/
  unit/
  transfer/
  validation_quick/
  validation_full/
  mpi/
```

In the current Python package, the three schemas live under `eda_multiphysics/schemas/` so editable
and wheel installations can load them as package data. Benchmark and example artifacts remain at
repository root under `benchmarks/` and `examples/` as shown above.

Each example should include:
- `README.md`;
- `case.yaml`;
- `materials.yaml`;
- `run.py`;
- `expected_metrics.json`;
- `evidence.json`;
- plotting and comparison scripts.

---

## 9. Recommended implementation order

1. Freeze benchmark definitions and error metrics.
2. Complete anisotropic 3D isolated-TSV verification.
3. Pass global curvature validation.
4. Pass local Raman validation.
5. Implement and verify conservative global-local transfer.
6. Build and compare the reduced/multilevel array model.
7. Add mobility/KOZ mapping and reproduce literature figures.
8. Add the EDA back-annotation and redesign example.
9. Package, rerun on a clean machine, and release only after the scorecard is entirely green.

The experimental Raman gate should be completed before substantial investment in optimization or a universal scene graph. If the local field cannot be validated, the device-level application is not ready.

---

## 10. Minimum release scorecard

| Category | Release-blocking condition |
|---|---|
| Numerical mechanics | Patch, symmetry, mesh, element-family, and MPI gates pass |
| Global experiment | Stabilized curvature branch NRMSE <= 20% |
| Local experiment | Raman curve and peak gates pass for two thermal loads |
| Multilevel accuracy | Device-layer stress L2 <= 5%; KOZ boundary within tolerance |
| Conservation | Force, moment, and virtual work mismatch <= 1e-6 |
| Performance | >=10x time and >=5x memory improvement for 20x20 array |
| Device mapping | Published isolated and array KOZ cases reproduced |
| EDA semantics | 100% identity preservation and coordinate round-trip gate |
| Design action | >=50% reduction in weighted violations and >=25% reduction in peak proxy |
| Reproducibility | Clean-machine validation and complete provenance pass |

**Release rule:** all ten categories must pass. A yellow or waived result must be described as a limitation and the release must be labeled alpha; an experimental-validation failure blocks the “validated” claim.

---

## References

1. S.-K. Ryu et al., “Characterization of thermal stresses in through-silicon vias for three-dimensional interconnects by bending beam technique,” *Applied Physics Letters*, 100, 041901 (2012), DOI: 10.1063/1.3678020.
2. T. Jiang et al., “Measurement and analysis of thermal stresses in 3D integrated structures containing through-silicon-vias,” *Microelectronics Reliability*, 53, 53-62 (2013), DOI: 10.1016/j.microrel.2012.05.008.
3. S.-K. Ryu et al., “Effect of Thermal Stresses on Carrier Mobility and Keep-Out Zone Around Through-Silicon Vias for 3-D Integration,” *IEEE Transactions on Device and Materials Reliability*, 12, 255-262 (2012), DOI: 10.1109/TDMR.2012.2194784.
4. M. Jung et al., “TSV Stress-Aware Full-Chip Mechanical Reliability Analysis and Optimization for 3-D IC,” *IEEE Transactions on Computer-Aided Design of Integrated Circuits and Systems*, 31, 1194-1207 (2012), DOI: 10.1109/TCAD.2012.2188400.
5. X. Wu et al., “An inter-scale simulation method for TSV 3D IC based on linear superposition algorithm and TSV model sharing strategy,” *Microelectronics Reliability*, 144, 114957 (2023), DOI: 10.1016/j.microrel.2023.114957.
6. T. Zhu et al., “MORE-Stress: Model Order Reduction based Efficient Numerical Algorithm for Thermal Stress Simulation of TSV Arrays in 2.5D/3D IC,” DATE 2025; arXiv:2411.12690.
7. C. Okoro et al., “Experimental measurement of the effect of copper through-silicon via diameter on stress buildup using synchrotron-based X-ray source,” *Journal of Materials Science*, 50, 6236-6244 (2015), DOI: 10.1007/s10853-015-9184-9.
