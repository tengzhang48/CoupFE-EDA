# CoupFE-EDA container

This optional image recipe is not required to install, test, or release the
source package; the documented conda + `setup.sh` path runs those gates
directly. It is a convenience for bundling the scientific stack, the open-EDA
front-end, PETSc/MPI, and the exact CoupFE core used by CoupFE-EDA. The core
commit and OpenROAD artifact digest are fixed in the recipe. Most conda-forge packages
are resolved from rolling channels, so archive `conda list --explicit` when a
byte-for-byte environment is required.

From the repository root:

```bash
./build.sh
docker run --rm -it coupfe-eda
```

## What the recipe installs

| Component | Selection | Notes |
|---|---|---|
| Base OS | `ubuntu:22.04` | Matches the OpenROAD binary ABI |
| Python | 3.11 | Pinned in `environment.yml`; patch release comes from the conda solve |
| OpenROAD | `v2.0-17598-ga008522d8` (2024-12-14) | URL and SHA-256 pinned |
| yosys, PETSc, mpi4py, gmsh | conda-forge solve | Record resolved versions for each release |
| volare | rolling pip dependency | Open-PDK manager |
| CoupFE | `454f73ce2de284262b214a2b37bd676c6aca3c0a` | Must be reachable from public `main` |

Inspect a built image:

```bash
docker run --rm coupfe-eda openroad -version
docker run --rm coupfe-eda yosys --version
docker run --rm coupfe-eda python -c \
  "import petsc4py, mpi4py, coupfe, eda_multiphysics; print('ok')"
docker inspect --format '{{ index .Config.Labels "coupfe.ref" }}' coupfe-eda
```

## Building

Prerequisites:

- Docker; the classic builder is sufficient.
- Unauthenticated HTTPS access to the public CoupFE branch.
- Approximately 3–4 GB free on the Docker root filesystem.

Verify the public dependency before building:

```bash
git ls-remote https://github.com/tengzhang48/CoupFE.git \
  refs/heads/main
```

`build.sh`:

1. checks that the public branch is reachable;
2. passes the source URL, branch, and exact commit into Docker;
3. lets the Dockerfile check that the commit is reachable from the branch and
   check it out detached;
4. verifies the pinned OpenROAD download digest; and
5. runs the standalone component/reference harness and then the default pytest
   tier. Those tiers overlap because pytest wraps the standalone gates.

### Build settings

| Variable | Default | Purpose |
|---|---|---|
| `COUPFE_URL` | `https://github.com/tengzhang48/CoupFE.git` | Public core source |
| `COUPFE_BRANCH` | `main` | Branch required to contain the pin |
| `COUPFE_REF` | `454f73ce2de284262b214a2b37bd676c6aca3c0a` | Exact qualified core commit |
| `TAG` | `coupfe-eda` | Image tag |
| `OPENROAD_DEB_URL` | pinned 2024-12-14 asset | Override together with its digest |
| `OPENROAD_DEB_SHA256` | pinned SHA-256 | Digest for the OpenROAD asset |
| `RUN_TOOLCHAIN_TESTS` | `0` | Set to `1` for the compiled/mesh/MPI tier |

Examples:

```bash
TAG=coupfe-eda:dev ./build.sh
RUN_TOOLCHAIN_TESTS=1 ./build.sh
OPENROAD_DEB_URL=<asset-url> \
OPENROAD_DEB_SHA256=<sha256> ./build.sh
```

Changing `COUPFE_REF` is a qualification action, not a routine update. The
Dockerfile refuses a ref that is absent from the documented branch.

## Running

```bash
# Re-run the fast checks already executed at build time.
docker run --rm coupfe-eda python -m eda_multiphysics.run
docker run --rm coupfe-eda python -m pytest -q

# Distributed PDN; the conda environment uses MPICH.
docker run --rm coupfe-eda \
  mpirun -n 4 python -m eda_multiphysics.pdn_distributed 400 --direct

# Mount a separate output directory for OpenROAD work.
docker run --rm -it -v "$PWD/work:/work" -w /work coupfe-eda
```

MPICH does not accept the OpenMPI-only `--oversubscribe` or
`--allow-run-as-root` options.

## Design decisions

### Exact public CoupFE source

The periodic mechanics path depends on generic affine MPC and native Tet4 in
the qualified Core release root. The image clones public `main`, checks
that exact commit `454f73ce2de284262b214a2b37bd676c6aca3c0a` is its ancestor,
and checks out the commit detached. This avoids SSH aliases, credentials, mutable
branch-tip installs, and accidental resolution of an unrelated `coupfe`
package from PyPI.

### Pinned OpenROAD artifact

The URL and SHA-256 select the Ubuntu 22.04 `2.0-17598` asset dated
2024-12-14. This is a compatibility baseline. Qualify a replacement, then
override both URL and digest together.

### Scope of build-time verification

The Dockerfile runs the standalone component/reference harness and then the
default pytest tier. The tiers overlap because pytest contains wrappers for the
standalone gates. The gmsh/PETSc/MPI/Fortran tier is opt-in because it adds
several minutes. Successful build-time checks retain the claim boundaries in
the validation guide.

## Release verification

Before publishing an image, build the selected recipe and record:

- the image digest and `coupfe.ref` label;
- `conda list --explicit` and all tool versions;
- standalone component/reference output and default-tier pytest output;
- toolchain output with `RUN_TOOLCHAIN_TESTS=1`; and
- distributed serial-versus-2/4-rank checks.

See `docs/VALIDATION_GUIDE.md` for the checked claim boundaries and
`THIRD_PARTY.md` for binary and fixture notices.

## Troubleshooting

| Symptom | Cause / response |
|---|---|
| Public CoupFE branch is not found | Verify that the core HTTPS URL and branch are public and reachable without credentials |
| Audited core commit is not reachable | Do not change the pin silently; publish/merge the audited commit or qualify a new pin |
| OpenROAD digest check fails | The asset and digest differ; set both override variables from a trusted release |
| `curl: (6) Could not resolve host` | Retry after Docker bridge DNS recovers |
| `mpiexec: unrecognized argument oversubscribe` | Drop OpenMPI-only flags; use plain `mpirun -n N` |
| No space left on device | Free Docker storage and confirm the Docker root filesystem has several GB available |

## File map

```text
Dockerfile        Ubuntu -> conda env -> pinned OpenROAD -> pinned CoupFE -> tests
build.sh          checks public branch reachability and passes exact pins
environment.yml   supported scientific/open-EDA/MPI dependency recipe
.dockerignore     excludes local caches and generated build artifacts
```
