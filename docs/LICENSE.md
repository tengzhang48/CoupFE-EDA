# Documentation and code license boundary

Project-authored executable material is licensed under
[Apache License 2.0](../LICENSE). This includes Python source, tests, schemas,
configuration, build files, executable command snippets, and the bundled
project-authored synthetic PDN fixture.

Project-authored prose, diagrams, and generated documentation figures are
licensed under
[Creative Commons Attribution 4.0 International](../LICENSES/CC-BY-4.0.txt).
This includes the explanatory portions of the root guides, `docs/`,
`examples/`, and `benchmarks/` unless a file states otherwise.

These licenses apply to material for which the project authors can grant
rights. They do not relicense:

- third-party software or datasets;
- product or project names and trademarks;
- literature citations, quoted material, or equations outside copyright scope;
- caller-supplied designs, PDKs, package files, or generated outputs; or
- external fixtures whose terms must be established by the caller.

The Python distributions do not bundle OpenROAD. The optional container uses a
pinned OpenROAD binary and retains its BSD-3-Clause notice; see
[THIRD_PARTY.md](../THIRD_PARTY.md) and
`LICENSES/OpenROAD-BSD-3-Clause.txt`. The bundled `synthetic_pdn` data is
project-authored, is not derived from GCD or a PDK, and is labeled as synthetic
integration material.

When redistributing adapted documentation, credit “CoupFE-EDA contributors,”
link to this repository when practicable, identify changes, and retain
applicable third-party notices. When redistributing executable material, follow
the Apache-2.0 conditions and retain `NOTICE`.
