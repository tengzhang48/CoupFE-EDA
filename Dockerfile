# CoupFE-EDA — repeatable conda-based container recipe.
#
# Ubuntu 22.04 base (so the Precision-Innovations OpenROAD prebuilt .deb matches), with a
# conda env for the scientific + open-EDA + MPI stack, a pinned/tested OpenROAD binary, and
# CoupFE pinned as a dependency (no CoupFE core files live in this repo).
# The core commit and OpenROAD artifact are immutable; environment.yml otherwise resolves
# rolling conda-forge packages, so this is not a byte-for-byte lock file.
#
#   docker build -t coupfe-eda .
#   docker run --rm -it coupfe-eda                       # component/reference harness plus default tier
#   docker run --rm coupfe-eda mpirun -n 4 \
#         python -m eda_multiphysics.pdn_distributed 400 --direct   # conda MPI is MPICH
#
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-lc"]

# --- system basics ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates bzip2 && \
    rm -rf /var/lib/apt/lists/*

# --- miniforge (conda + mamba) ---
RUN curl -fsSL -o /tmp/mf.sh \
      "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh" && \
    bash /tmp/mf.sh -b -p /opt/conda && rm /tmp/mf.sh
ENV PATH=/opt/conda/bin:$PATH

# --- conda env: scientific + petsc4py(+superlu_dist) + mpi4py + yosys ---
COPY environment.yml /tmp/environment.yml
RUN mamba env create -f /tmp/environment.yml && conda clean -afy
# put the env on PATH so RUN/CMD use it directly
ENV PATH=/opt/conda/envs/coupfe-eda/bin:$PATH

# --- pinned/tested OpenROAD binary (Precision Innovations, Ubuntu 22.04) ---
# The URL and digest are fixed rather than resolved live. The later 26Q1 release has no
# prebuilt .deb. Override both arguments together when deliberately qualifying another build.
ARG OPENROAD_DEB_URL=https://github.com/Precision-Innovations/OpenROAD/releases/download/2024-12-14/openroad_2.0-17598-ga008522d8_amd64-ubuntu-22.04.deb
ARG OPENROAD_DEB_SHA256=40ed178396b0276a5d5dfbbe695c9de9aac9088157a6655be02b39a0cef07207
RUN echo "Installing OpenROAD: $OPENROAD_DEB_URL" && \
    curl -fsSL --retry 5 --retry-connrefused --retry-delay 3 -o /tmp/openroad.deb "$OPENROAD_DEB_URL" && \
    echo "$OPENROAD_DEB_SHA256  /tmp/openroad.deb" | sha256sum -c - && \
    apt-get update && apt-get install -y /tmp/openroad.deb && \
    rm /tmp/openroad.deb && rm -rf /var/lib/apt/lists/* && \
    openroad -version

# --- public CoupFE core (audited branch + exact commit) + CoupFE-EDA ---
ARG COUPFE_URL=https://github.com/tengzhang48/CoupFE.git
ARG COUPFE_BRANCH=main
ARG COUPFE_REF=e2f42ed5772850a0a23a2ce434f430c287eae5c8
RUN git clone --branch "$COUPFE_BRANCH" --single-branch "$COUPFE_URL" /opt/CoupFE && \
    git -C /opt/CoupFE cat-file -e "$COUPFE_REF^{commit}" && \
    git -C /opt/CoupFE merge-base --is-ancestor "$COUPFE_REF" "origin/$COUPFE_BRANCH" && \
    git -C /opt/CoupFE checkout --detach "$COUPFE_REF" && \
    test "$(git -C /opt/CoupFE rev-parse HEAD)" = "$COUPFE_REF" && \
    python -m pip install -e /opt/CoupFE
LABEL coupfe.ref=$COUPFE_REF
COPY . /opt/CoupFE-EDA
RUN python -m pip install -e /opt/CoupFE-EDA

WORKDIR /opt/CoupFE-EDA
# Verify all default tests at build time. The compiled/mesh/MPI tier is opt-in because it
# adds several minutes and should also run in a dedicated release job.
RUN python -m eda_multiphysics.run && python -m pytest -q
ARG RUN_TOOLCHAIN_TESTS=0
RUN if [ "$RUN_TOOLCHAIN_TESTS" = "1" ]; then python -m pytest -q -m toolchain; fi
CMD ["/bin/bash"]
