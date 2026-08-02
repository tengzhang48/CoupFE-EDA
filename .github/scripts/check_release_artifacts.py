"""Validate the releasable source tree and built CoupFE-EDA artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import stat
import subprocess
import tarfile
import zipfile
from collections import Counter
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Optional


PUBLIC_CORE_URL = "https://github.com/tengzhang48/CoupFE.git"
PUBLIC_CORE_BRANCH = "main"
# This exact Core release root is anonymously reachable from public ``main``.
# Keep the release guard fail-closed for any other dependency revision.
APPROVED_PUBLIC_CORE_REF: Optional[str] = (
    "e2f42ed5772850a0a23a2ce434f430c287eae5c8"
)
CORE_RELEASE_INPUTS = (
    "setup.sh",
    "build.sh",
    "Dockerfile",
    ".github/workflows/fast-ci.yml",
)

SYNTHETIC_CASE_PREFIX = "eda_multiphysics/cases/synthetic_pdn"
SYNTHETIC_CASE_ASSETS = {
    f"{SYNTHETIC_CASE_PREFIX}/{name}"
    for name in {
        "README.md",
        "generate_case.py",
        "instance_power.csv",
        "instance_power.meta.json",
        "instances.csv",
        "joints.csv",
        "joints.meta.json",
        "manifest.json",
        "pdn_vdd.sp",
        "reference_vdd_nodes.csv",
        "reference_vdd_nodes.meta.json",
    }
}
LEGACY_GCD_PREFIX = "eda_multiphysics/cases/gcd_nangate45/"
SCHEMA_ASSETS = {
    f"eda_multiphysics/schemas/{name}"
    for name in {
        "physical_scene_tsv.schema.json",
        "tsv_material_manifest.schema.json",
        "validation_manifest.schema.json",
    }
}
PUBLIC_PACKAGE_FILES = SCHEMA_ASSETS | SYNTHETIC_CASE_ASSETS | {
    f"eda_multiphysics/{name}"
    for name in {
        "DISTRIBUTED.md",
        "RESULTS.md",
        "__init__.py",
        "_coupled_solve.py",
        "_stateful_solve.py",
        "anand.py",
        "anand_3d.py",
        "capacitance.py",
        "case_thermal.py",
        "chip_vtu.py",
        "creep.py",
        "design_loop_demo.py",
        "electromigration.py",
        "electrothermal.py",
        "electrothermal_chip.py",
        "etv_3d.py",
        "etv_distributed.py",
        "etv_distributed_fs.py",
        "etv_fe.py",
        "etv_fieldsplit.py",
        "etv_kernel.py",
        "etv_solder.py",
        "fe.py",
        "gates.py",
        "joint_map.py",
        "mesh3d.py",
        "pdn_distributed.py",
        "pdn_graph.py",
        "periodic.py",
        "reliability_3d.py",
        "reliability_pipeline.py",
        "run.py",
        "scaling_bench.py",
        "solder_joint.py",
        "tet_3d.py",
        "tet_element.py",
        "thermal_runaway.py",
        "thermomech.py",
        "thermomech_3d.py",
        "thermomech_kernel.py",
        "thermomech_tsv.py",
        "transient.py",
        "tsv_3d.py",
        "tsv_device.py",
        "tsv_local_3d.py",
        "tsv_stress.py",
        "tsv_validation.py",
        "validate.py",
        "workbench.py",
        "workbench_api.py",
    }
} | {
    "eda_multiphysics/openroad/export_case.tcl",
    "eda_multiphysics/tests/test_gates.py",
}
PUBLIC_TEST_FILES = {
    "tests/conftest.py",
    "tests/test_integration_regressions.py",
    "tests/test_native_element_evaluation.py",
    "tests/test_periodic_adapter.py",
    "tests/test_toolchain.py",
    "tests/test_tsv_device.py",
    "tests/test_tsv_local_3d.py",
    "tests/test_workbench.py",
    "tests/test_workbench_api.py",
}
PUBLIC_LICENSE_FILES = {
    f"LICENSES/{name}"
    for name in {
        "CC-BY-4.0.txt",
        "OpenROAD-BSD-3-Clause.txt",
    }
}
PUBLIC_GITHUB_FILES = {
    ".github/scripts/check_release_artifacts.py",
    ".github/scripts/check_runtime_core.py",
    ".github/scripts/record_release_evidence.py",
    ".github/scripts/smoke_wheel.py",
    ".github/workflows/coupfe-workbench-pages.yml",
    ".github/workflows/fast-ci.yml",
    ".github/workflows/web-ci.yml",
}
CURRENT_SOLVER_SCALING_FILES = {
    f"benchmarks/solver_scaling/current_526338dof_20260801/{name}"
    for name in {
        "README.md",
        "environment.json",
        "provenance.json",
        "run_manifest.json",
        "summary.json",
        "table.md",
    }
} | {
    (
        "benchmarks/solver_scaling/current_526338dof_20260801/runs/"
        f"rank-{rank:04d}-repeat-{repeat:03d}.{suffix}.txt"
    )
    for rank in (1, 2, 4, 8)
    for repeat in (1, 2, 3)
    for suffix in ("rankfile", "stderr", "stdout")
}

PUBLIC_BENCHMARK_FILES = CURRENT_SOLVER_SCALING_FILES | {
    f"benchmarks/{name}/manifest.json"
    for name in {
        "tsv_curvature_ryu2012",
        "tsv_mobility_koz_ryu2012",
        "tsv_more_stress_2025",
        "tsv_raman_jiang2013",
    }
} | {
    "benchmarks/README.md",
    "benchmarks/solver_scaling/README.md",
    "benchmarks/solver_scaling/historical_unqualified.json",
    "benchmarks/solver_scaling/historical_unqualified.md",
    "benchmarks/solver_scaling/manifest.json",
    "benchmarks/solver_scaling/petsc_coo_gamg_reproducer.py",
    "benchmarks/tsv_release_scorecard.json",
}
PUBLIC_HISTORY_FILES = {
    "docs/history/PROJECT_ORIGINS.md",
    "docs/history/README.md",
    "docs/history/audits/code_examples_review_evidence_snapshot.md",
    "docs/history/audits/code_examples_review_snapshot.md",
    "docs/history/audits/tsv_physics_audit_snapshot.md",
    "docs/history/audits/validation_assessment_snapshot.md",
    "docs/history/development/electro_thermo_viscoplastic_coupling_plan_snapshot.md",
    "docs/history/development/external_collaboration_brief_snapshot.md",
    "docs/history/development/lessons_learned_snapshot.md",
    "docs/history/development/open_source_eda_multiphysics_integration_plan_snapshot.md",
    "docs/history/development/open_source_eda_multiphysics_literature_survey_snapshot.md",
    "docs/history/development/periodic_boundary_condition_plan_snapshot.md",
    "docs/history/development/refactor_contract_snapshot.md",
    "docs/history/development/tsv_anisotropic_3d_plan_snapshot.md",
    "docs/history/development/tsv_device_validation_release_plan_snapshot.md",
    "docs/history/results/eda_multiphysics_results_snapshot.md",
}
PUBLIC_DOC_FILES = PUBLIC_HISTORY_FILES | {
    f"docs/{name}"
    for name in {
        "API_MIGRATIONS.md",
        "COMPONENTS.md",
        "GEOMETRY.md",
        "LICENSE.md",
        "PERIODIC_MPC_STATUS.md",
        "README.md",
        "RELEASE_EVIDENCE.md",
        "TET_FEASIBILITY.md",
        "VALIDATION_GUIDE.md",
        "api.md",
        "capabilities.md",
        "lessons_learned.md",
        "roadmap.md",
        "theory.md",
    }
} | {
    f"docs/validation_guide/figures/{name}.png"
    for name in {
        "anand_materials",
        "capstone_pipeline",
        "etv_solver",
        "misc_gates",
        "pdn_em",
        "scalar_electrothermal",
        "thermomech",
        "toolchain_distributed",
        "toolchain_etv_3d",
        "toolchain_reliability",
        "toolchain_thermomech_3d",
        "toolchain_thermomech_tsv",
        "toolchain_tsv_3d",
        "tsv_stress",
    }
} | {
    "docs/validation_guide/generate_figures.py",
    "docs/validation_guide/README.md",
}
PUBLIC_EXAMPLE_FILES = {
    "examples/REFERENCES.md",
    "examples/design_linked_solder_screening/README.md",
    "examples/design_linked_solder_screening/expected_results.json",
    "examples/design_linked_solder_screening/run.py",
    "examples/etv_partitioned_cycle/README.md",
    "examples/etv_partitioned_cycle/expected_results.json",
    "examples/etv_partitioned_cycle/run.py",
    "examples/solder_3d_cycle/README.md",
    "examples/solder_3d_cycle/expected_results.json",
    "examples/solder_3d_cycle/run.py",
    "examples/solder_plane_cycle/README.md",
    "examples/solder_plane_cycle/expected_results.json",
    "examples/solder_plane_cycle/run.py",
    "examples/tsv_00_device_screening/README.md",
    "examples/tsv_00_device_screening/case.json",
    "examples/tsv_00_device_screening/device_sites.csv",
    "examples/tsv_00_device_screening/expected_metrics.json",
    "examples/tsv_00_device_screening/materials.json",
    "examples/tsv_00_device_screening/run.py",
}
PUBLIC_SKILL_FILES = {
    "skills/SKILL.md",
    "skills/agents/openai.yaml",
}
PUBLIC_WEB_FILES = {
    f"web/{name}"
    for name in {
        ".env.api",
        ".env.demo",
        ".env.example",
        ".gitignore",
        ".nvmrc",
        "ARCHITECTURE.md",
        "INTEGRATION.md",
        "README.md",
        "contracts/connected-project-snapshot.json",
        "contracts/retained-tsv-artifacts.json",
        "favicon.svg",
        "index.html",
        "package-lock.json",
        "package.json",
        "public/generated/tsv_device_screening/device_screening.csv",
        "public/generated/tsv_device_screening/device_screening.svg",
        "public/generated/tsv_device_screening/evidence.json",
        "scripts/check-repository-data.mjs",
        "scripts/prepare-repository-assets.mjs",
        "scripts/refresh-tsv-device-artifacts.mjs",
        "site-data.json",
        "src/App.test.tsx",
        "src/App.tsx",
        "src/SiteApp.test.tsx",
        "src/SiteApp.tsx",
        "src/backend/factory.ts",
        "src/backend/fastapi-backend.ts",
        "src/backend/interface.ts",
        "src/backend/mock-backend.test.ts",
        "src/backend/mock-backend.ts",
        "src/demo/snapshot.ts",
        "src/domain/selectors.test.ts",
        "src/domain/selectors.ts",
        "src/domain/types.ts",
        "src/hooks/use-workbench.ts",
        "src/main.tsx",
        "src/site-styles.css",
        "src/styles.css",
        "src/test/setup.ts",
        "src/vite-env.d.ts",
        "tsconfig.app.json",
        "tsconfig.json",
        "tsconfig.node.json",
        "vite.config.ts",
    }
}
PUBLIC_ROOT_FILES = {
    ".dockerignore",
    ".gitignore",
    "CONTAINER.md",
    "Dockerfile",
    "EXAMPLES.md",
    "LICENSE",
    "MANIFEST.in",
    "NOTICE",
    "README.md",
    "THIRD_PARTY.md",
    "build.sh",
    "environment.yml",
    "pyproject.toml",
    "setup.sh",
}
PUBLIC_SDIST_ROOT_FILES = PUBLIC_ROOT_FILES | {
    "PKG-INFO",
    "setup.cfg",
}
PUBLIC_SDIST_METADATA_FILES = {
    f"coupfe_eda.egg-info/{name}"
    for name in {
        "PKG-INFO",
        "SOURCES.txt",
        "dependency_links.txt",
        "entry_points.txt",
        "requires.txt",
        "top_level.txt",
    }
}
PUBLIC_SOURCE_INVENTORIES = {
    ".github": PUBLIC_GITHUB_FILES,
    "LICENSES": PUBLIC_LICENSE_FILES,
    "benchmarks": PUBLIC_BENCHMARK_FILES,
    "docs": PUBLIC_DOC_FILES,
    "eda_multiphysics": PUBLIC_PACKAGE_FILES,
    "examples": PUBLIC_EXAMPLE_FILES,
    "skills": PUBLIC_SKILL_FILES,
    "tests": PUBLIC_TEST_FILES,
    "web": PUBLIC_WEB_FILES,
}
PUBLIC_RELEASE_FILES = PUBLIC_ROOT_FILES | set().union(
    *PUBLIC_SOURCE_INVENTORIES.values()
)
OPENROAD_LICENSE_SHA256 = (
    "e4c62605dedc27267ba0b1b987f6f86355b4e20362ebdeb07a59a792a260d29b"
)
OPENROAD_COPYRIGHT_NOTICE = (
    "Copyright (c) 2018-2023, The Regents of the University of California"
)
UNREVIEWED_WEB_PLACEHOLDER_FRAGMENTS = (
    "coupfe-eda@8a3d91e",
    "8a3d91e",
    "coupfe-core 0.7.0",
    "benchmarks/tsv/thermal-validation-v2.json",
    "verification/mesh-study-04.json",
    "materials/interface-limit-v2.yaml",
    "benchmarks/tsv/margin-validation-v1.json",
    "package-steady-v3",
    "tsv-materials-v2",
)
EXPECTED_CONSOLE_ENTRY_POINTS = (
    "[console_scripts]\n"
    "coupfe-eda-workbench = eda_multiphysics.workbench_api:main\n"
)

REQUIRED_SDIST_FILES = PUBLIC_RELEASE_FILES

FORBIDDEN_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "gcd_nangate45",
    "notes",
    "presentation",
    "reviews",
}
FORBIDDEN_NAMES = {
    "CODE_EXAMPLES_REVIEW.md",
    "COLLABORATION_BRIEF.md",
    "CoupFE_EDA_TSV_Device_Validation_Release_Plan.md",
    "Gaps and Opportunities in Open-Source Multiphysics Simulation for Electronic Design Automation.pdf",
    "Nangate45-Apache-2.0.txt",
    "OpenROAD-flow-scripts-BSD-3-Clause.txt",
    "PERIODIC_BOUNDARY_CONDITION_PLAN.md",
    "PyMTL-BSD-3-Clause.txt",
    "REFACTOR_CONTRACT.md",
    "RELEASE_READINESS.md",
    "TSV_ANISOTROPIC_3D_PLAN.md",
    "TSV_PHYSICS_AUDIT.md",
    "TRUST_NET_FINDINGS.md",
    "VALIDATION_ASSESSMENT.md",
    "claude_review_periodic_mpc.md",
    "electro_thermo_viscoplastic_coupling_plan.md",
    "gpt_review_anand_3d.md",
    "kimi_task_tet4.md",
    "kimi_task_trust_net.md",
    "gcd_thermal.py",
    "open_source_eda_multiphysics_integration_plan.md",
    "open_source_eda_multiphysics_literature_survey.md",
    "petsc_coo_gamg_bug_repro.py",
    "shape_tet4.for",
}
FORBIDDEN_NAME_PATTERNS = {
    "HANDOFF*.md",
    "NOTE_FROM_*.md",
    "NOTE_TO_*.md",
    "*_for_claude*.md",
    "*_for_gpt*.md",
    "*.tar.bz2",
    "*.tar.gz",
    "*.tar.xz",
    "*.tgz",
}
FORBIDDEN_SUFFIXES = {
    ".7z",
    ".a",
    ".bin",
    ".bz2",
    ".cab",
    ".class",
    ".dll",
    ".dmg",
    ".doc",
    ".docx",
    ".dylib",
    ".exe",
    ".gz",
    ".iso",
    ".jar",
    ".lz",
    ".lz4",
    ".mod",
    ".o",
    ".obj",
    ".pdf",
    ".ppt",
    ".pptx",
    ".pyc",
    ".pyd",
    ".pyo",
    ".rar",
    ".so",
    ".tar",
    ".tex",
    ".tgz",
    ".whl",
    ".xls",
    ".xlsx",
    ".xz",
    ".zip",
    ".zst",
    ".zstd",
}
IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
TEXT_SUFFIXES = {
    "",
    ".api",
    ".cfg",
    ".css",
    ".csv",
    ".demo",
    ".example",
    ".f90",
    ".for",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".rst",
    ".sh",
    ".sp",
    ".svg",
    ".tcl",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


def _validate_names(names: list[str], artifact: Path) -> None:
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise SystemExit(f"{artifact.name} contains duplicate entries: {duplicates}")

    unsafe = []
    for name in names:
        path = PurePosixPath(name)
        if "\\" in name or path.is_absolute() or ".." in path.parts:
            unsafe.append(name)
    if unsafe:
        raise SystemExit(f"{artifact.name} contains unsafe paths: {sorted(unsafe)}")


def _is_allowed_public_image(path: PurePosixPath) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    return (
        path.suffix.casefold() in IMAGE_SUFFIXES
        and (
            (len(parts) >= 4 and parts[:3] == ("docs", "validation_guide", "figures"))
            or (len(parts) >= 2 and parts[0] == "web")
        )
    )


def _is_forbidden_path(name: str) -> bool:
    path = PurePosixPath(name)
    parts = tuple(part.casefold() for part in path.parts)
    basename = path.name.casefold()
    suffix = path.suffix.casefold()
    return bool(
        set(parts).intersection(part.casefold() for part in FORBIDDEN_PARTS)
        or basename in {name.casefold() for name in FORBIDDEN_NAMES}
        or any(
            fnmatchcase(basename, pattern.casefold())
            for pattern in FORBIDDEN_NAME_PATTERNS
        )
        or any(part.startswith("_etk") for part in parts)
        or any(part.startswith("_tm_") for part in parts)
        or suffix in FORBIDDEN_SUFFIXES
        or (suffix in IMAGE_SUFFIXES and not _is_allowed_public_image(path))
    )


def _reject_forbidden_files(names: set[str], artifact: Path) -> None:
    rejected = sorted(name for name in names if _is_forbidden_path(name))
    if rejected:
        raise SystemExit(f"{artifact.name} contains forbidden entries: {rejected}")


def _require_files(available: set[str], required: set[str], artifact: Path) -> None:
    missing = sorted(required - available)
    if missing:
        raise SystemExit(f"{artifact.name} is missing required files: {missing}")


def _validate_exact_subtree(
    names: set[str], artifact: Path, prefix: str, expected: set[str]
) -> None:
    """Require one reviewed public subtree to match its static inventory."""

    present = {
        name
        for name in names
        if PurePosixPath(name).parts
        and PurePosixPath(name).parts[0] == prefix
    }
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)
    if missing or unexpected:
        raise SystemExit(
            f"{artifact.name} public {prefix} inventory mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )


def _validate_exact_root_files(
    names: set[str], artifact: Path, expected: set[str]
) -> None:
    """Require the reviewed top-level files and reject unreviewed additions."""

    present = {
        name for name in names if len(PurePosixPath(name).parts) == 1
    }
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)
    if missing or unexpected:
        raise SystemExit(
            f"{artifact.name} public root inventory mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )


def _validate_public_source_inventories(
    names: set[str],
    artifact: Path,
    *,
    root_files: set[str],
    allowed_generated_subtrees: set[str] | None = None,
) -> None:
    """Validate every reviewed source subtree and its top-level boundary."""

    _validate_exact_root_files(names, artifact, root_files)
    for prefix, expected in PUBLIC_SOURCE_INVENTORIES.items():
        _validate_exact_subtree(names, artifact, prefix, expected)

    allowed_prefixes = set(PUBLIC_SOURCE_INVENTORIES)
    allowed_prefixes.update(allowed_generated_subtrees or set())
    unexpected_prefixes = sorted(
        {
            path.parts[0]
            for name in names
            if len((path := PurePosixPath(name)).parts) > 1
            and path.parts[0] not in allowed_prefixes
        }
    )
    if unexpected_prefixes:
        raise SystemExit(
            f"{artifact.name} contains unreviewed top-level subtrees: "
            f"{unexpected_prefixes}"
        )


def _validate_public_tests(files: set[str], artifact: Path) -> None:
    shipped = {
        name
        for name in files
        if len(PurePosixPath(name).parts) >= 2
        and PurePosixPath(name).parts[0] == "tests"
        and PurePosixPath(name).suffix == ".py"
    }
    if shipped != PUBLIC_TEST_FILES:
        raise SystemExit(
            f"{artifact.name} public test partition differs from the reviewed "
            f"allowlist: missing={sorted(PUBLIC_TEST_FILES - shipped)}, "
            f"extra={sorted(shipped - PUBLIC_TEST_FILES)}"
        )


def _validate_entry_point_ledger(
    files: set[str],
    read_bytes,
    artifact: Path,
) -> None:
    ledger_name = "examples/REFERENCES.md"
    if ledger_name not in files:
        raise SystemExit(f"{artifact.name} is missing {ledger_name}")
    ledger = read_bytes(ledger_name).decode("utf-8")
    rows = re.findall(r"^\| `(python [^`]+)` \|", ledger, flags=re.MULTILINE)
    duplicates = sorted(
        entry for entry, count in Counter(rows).items() if count > 1
    )
    if duplicates:
        raise SystemExit(
            f"{artifact.name}:{ledger_name} repeats entry points: {duplicates}"
        )

    discovered = set()
    for name in sorted(files):
        path = PurePosixPath(name)
        entry = None
        if (
            len(path.parts) == 2
            and path.parts[0] == "eda_multiphysics"
            and path.suffix == ".py"
            and path.name != "__init__.py"
        ):
            entry = f"python -m eda_multiphysics.{path.stem}"
        elif (
            len(path.parts) == 3
            and path.parts[0] == "examples"
            and path.name == "run.py"
        ):
            entry = f"python {name}"
        elif (
            len(path.parts) >= 4
            and path.parts[:2] == ("eda_multiphysics", "cases")
            and path.name == "generate_case.py"
        ):
            entry = f"python {name}"
        if entry is None:
            continue
        source = read_bytes(name).decode("utf-8")
        if re.search(
            r"if\s+__name__\s*==\s*['\"]__main__['\"]\s*:",
            source,
        ):
            discovered.add(entry)

    recorded = set(rows)
    if recorded != discovered:
        raise SystemExit(
            f"{artifact.name}:{ledger_name} does not exactly cover runnable "
            f"entry points: missing={sorted(discovered - recorded)}, "
            f"extra={sorted(recorded - discovered)}"
        )


def _sensitive_fragments() -> tuple[str, ...]:
    # Concatenation keeps the guard from matching its own source text.
    return (
        "/" + "home/",
        "/" + "media/",
        "abaqus" + "_ufl_lab",
        "git" + "@jetstream",
        "gh" + "p_",
        "BEGIN " + "PRIVATE KEY",
    )


def _sensitive_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return (
        (
            "github-fine-grained-token",
            re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        ),
        ("openai-api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
        ("aws-access-key-id", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
        (
            "bearer-token",
            re.compile(r"\bBearer[ \t]+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE),
        ),
        (
            "private-key-banner",
            re.compile(
                r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                re.IGNORECASE,
            ),
        ),
    )


def _validate_json_text(text: str, name: str, artifact: Path) -> None:
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate object key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value!r}")

    try:
        json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"{artifact.name}:{name} is not strict JSON: {exc}") from exc


def _validate_text(name: str, payload: bytes, artifact: Path) -> None:
    path = PurePosixPath(name)
    if path.suffix.casefold() not in TEXT_SUFFIXES:
        return
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"{artifact.name}:{name} is not valid UTF-8 text") from exc

    if path.suffix.casefold() == ".json":
        _validate_json_text(text, name, artifact)

    if name.startswith("web/"):
        placeholders = sorted(
            fragment
            for fragment in UNREVIEWED_WEB_PLACEHOLDER_FRAGMENTS
            if fragment in text
        )
        if placeholders:
            raise SystemExit(
                f"{artifact.name}:{name} contains the unreviewed prototype "
                f"evidence record: {placeholders}"
            )

    hits = [fragment for fragment in _sensitive_fragments() if fragment in text]
    hits.extend(
        label for label, pattern in _sensitive_patterns() if pattern.search(text)
    )
    if re.search(r"[\w.+-]+@(?:gmail\.com|syr\.edu)\b", text, flags=re.IGNORECASE):
        hits.append("personal-email-address")
    if hits:
        raise SystemExit(
            f"{artifact.name}:{name} contains private-path/credential material: {sorted(hits)}"
        )


def _release_input_value(
    text: str,
    artifact: Path,
    member: str,
    field: str,
) -> str:
    if member in {"setup.sh", "build.sh"}:
        pattern = re.compile(
            rf'^{field}="\$\{{{field}:-([^}}\r\n]+)\}}"[ \t]*$',
            flags=re.MULTILINE,
        )
    elif member == "Dockerfile":
        pattern = re.compile(
            rf"^ARG[ \t]+{field}=([^\s#]+)[ \t]*(?:#.*)?$",
            flags=re.MULTILINE,
        )
    elif member == ".github/workflows/fast-ci.yml":
        pattern = re.compile(
            rf"^[ \t]+{field}:[ \t]+([^\s#]+)[ \t]*(?:#.*)?$",
            flags=re.MULTILINE,
        )
    else:
        raise AssertionError(f"unsupported Core release input: {member}")

    matches = pattern.findall(text)
    if len(matches) != 1:
        raise SystemExit(
            f"{artifact.name}:{member} must declare exactly one default {field}"
        )
    return matches[0]


def _validate_core_release_inputs(
    files: set[str],
    read_bytes,
    artifact: Path,
    *,
    allow_unapproved_core_ref: bool,
) -> tuple[str, str, str]:
    missing = sorted(set(CORE_RELEASE_INPUTS) - files)
    if missing:
        raise SystemExit(
            f"{artifact.name} is missing Core release inputs: {missing}"
        )

    declarations: dict[str, tuple[str, str, str]] = {}
    for member in CORE_RELEASE_INPUTS:
        text = read_bytes(member).decode("utf-8")
        declarations[member] = tuple(
            _release_input_value(text, artifact, member, field)
            for field in ("COUPFE_URL", "COUPFE_BRANCH", "COUPFE_REF")
        )

    distinct = set(declarations.values())
    if len(distinct) != 1:
        rendered = ", ".join(
            f"{member}={values!r}"
            for member, values in sorted(declarations.items())
        )
        raise SystemExit(
            f"{artifact.name} has inconsistent CoupFE URL/branch/ref declarations "
            f"across release inputs: {rendered}"
        )

    url, branch, ref = distinct.pop()
    if url != PUBLIC_CORE_URL:
        raise SystemExit(
            f"{artifact.name} must use the public HTTPS CoupFE repository "
            f"{PUBLIC_CORE_URL!r}, not {url!r}"
        )
    if branch != PUBLIC_CORE_BRANCH:
        raise SystemExit(
            f"{artifact.name} must use public Core branch "
            f"{PUBLIC_CORE_BRANCH!r}, not {branch!r}"
        )
    if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        raise SystemExit(
            f"{artifact.name} must pin CoupFE to one full 40-hex revision, "
            f"not {ref!r}"
        )

    normalized_ref = ref.casefold()
    approved = APPROVED_PUBLIC_CORE_REF
    if approved is not None and not re.fullmatch(r"[0-9a-f]{40}", approved):
        raise SystemExit(
            "release guard configuration error: APPROVED_PUBLIC_CORE_REF must "
            "be None or one lowercase full 40-hex revision"
        )
    if approved is None:
        message = (
            f"{artifact.name} pins CoupFE revision {normalized_ref}, but the "
            "release guard has no approved public Core revision yet; set "
            "APPROVED_PUBLIC_CORE_REF only after that clean-root commit is "
            f"reachable from public {PUBLIC_CORE_BRANCH}"
        )
    elif normalized_ref != approved:
        message = (
            f"{artifact.name} pins unapproved CoupFE revision {normalized_ref}; "
            f"the only approved public Core revision is {approved}"
        )
    else:
        return url, branch, normalized_ref

    if not allow_unapproved_core_ref:
        raise SystemExit(message)
    print(f"WARNING: {message} (audit override enabled)")

    return url, branch, normalized_ref


def _synthetic_number(
    value: object,
    artifact: Path,
    location: str,
) -> float:
    """Parse one finite fixture number with an artifact-local diagnostic."""

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            f"{artifact.name}:{location} must be a finite number, got {value!r}"
        ) from exc
    if not math.isfinite(number):
        raise SystemExit(
            f"{artifact.name}:{location} must be finite, got {value!r}"
        )
    return number


def _require_synthetic_close(
    actual: float,
    expected: float,
    artifact: Path,
    location: str,
    *,
    abs_tol: float,
) -> None:
    """Require a deterministic fixture equality within serialization roundoff."""

    if not math.isclose(actual, expected, rel_tol=1.0e-12, abs_tol=abs_tol):
        raise SystemExit(
            f"{artifact.name}:{location} mismatch: "
            f"computed {actual:.17g}, declared/reference {expected:.17g}"
        )


def _solve_synthetic_network(
    nodes: set[str],
    resistors: list[tuple[str, str, float]],
    loads: dict[str, float],
    source_node: str,
    source_voltage: float,
    artifact: Path,
    spice_name: str,
) -> tuple[dict[str, float], tuple[str, ...]]:
    """Solve the small resistor graph with stdlib-only Gaussian elimination."""

    fixed = {"0": 0.0, source_node: source_voltage}
    free = tuple(sorted(nodes - set(fixed)))
    index = {node: row for row, node in enumerate(free)}
    matrix = [[0.0 for _ in free] for _ in free]
    rhs = [-loads.get(node, 0.0) for node in free]

    for node_a, node_b, resistance in resistors:
        conductance = 1.0 / resistance
        for node, other in ((node_a, node_b), (node_b, node_a)):
            if node not in index:
                continue
            row = index[node]
            matrix[row][row] += conductance
            if other in index:
                matrix[row][index[other]] -= conductance
            else:
                rhs[row] += conductance * fixed[other]

    augmented = [row[:] + [value] for row, value in zip(matrix, rhs)]
    size = len(augmented)
    for column in range(size):
        pivot_row = max(
            range(column, size),
            key=lambda row: abs(augmented[row][column]),
        )
        pivot = augmented[pivot_row][column]
        if abs(pivot) <= 1.0e-18:
            raise SystemExit(
                f"{artifact.name}:{spice_name} has a singular or disconnected "
                "free-node conductance system"
            )
        augmented[column], augmented[pivot_row] = (
            augmented[pivot_row],
            augmented[column],
        )
        for row in range(column + 1, size):
            factor = augmented[row][column] / augmented[column][column]
            if factor == 0.0:
                continue
            for entry in range(column, size + 1):
                augmented[row][entry] -= factor * augmented[column][entry]

    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        remainder = math.fsum(
            augmented[row][column] * solution[column]
            for column in range(row + 1, size)
        )
        solution[row] = (
            augmented[row][size] - remainder
        ) / augmented[row][row]

    voltages = dict(fixed)
    voltages.update(
        {
            node: solution[index[node]]
            for node in free
        }
    )
    if not all(math.isfinite(value) for value in voltages.values()):
        raise SystemExit(
            f"{artifact.name}:{spice_name} produced a non-finite nodal solution"
        )
    return voltages, free


def _validate_synthetic_electrical_reference(
    read_bytes,
    artifact: Path,
    manifest: dict[str, object],
    instance_rows: list[dict[str, str]],
    power_rows: list[dict[str, str]],
    power_meta: dict[str, object],
    reference_meta: dict[str, object],
) -> None:
    """Independently validate the synthetic SPICE, nodal reference, and power closure."""

    spice_name = f"{SYNTHETIC_CASE_PREFIX}/pdn_vdd.sp"
    element_names: set[str] = set()
    nodes: set[str] = set()
    resistors: list[tuple[str, str, float]] = []
    loads: dict[str, float] = {}
    voltage_sources: list[tuple[str, str, float]] = []
    spice_bytes = read_bytes(spice_name)
    spice_text = spice_bytes.decode("utf-8")
    declared_spice_hash = reference_meta.get("pdn_spice_sha256")
    actual_spice_hash = hashlib.sha256(spice_bytes).hexdigest()
    if (
        not isinstance(declared_spice_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", declared_spice_hash)
        or declared_spice_hash != actual_spice_hash
    ):
        raise SystemExit(
            f"{artifact.name}:{SYNTHETIC_CASE_PREFIX}/"
            "reference_vdd_nodes.meta.json:pdn_spice_sha256 must bind the "
            "reference to the packaged pdn_vdd.sp"
        )

    for line_number, raw_line in enumerate(spice_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("*", ".")):
            continue
        fields = line.split()
        location = f"{spice_name}:{line_number}"
        if len(fields) != 4:
            raise SystemExit(
                f"{artifact.name}:{location} must contain a four-field R, I, or V element"
            )
        element_name, node_a, node_b, raw_value = fields
        if element_name in element_names:
            raise SystemExit(
                f"{artifact.name}:{location} repeats element name {element_name!r}"
            )
        element_names.add(element_name)
        nodes.update((node_a, node_b))
        value = _synthetic_number(raw_value, artifact, location)
        kind = element_name[0].upper()
        if kind == "R":
            if node_a == node_b or value <= 0.0:
                raise SystemExit(
                    f"{artifact.name}:{location} requires a positive resistor "
                    "between distinct nodes"
                )
            resistors.append((node_a, node_b, value))
        elif kind == "I":
            if node_a == "0" or node_b != "0" or value <= 0.0:
                raise SystemExit(
                    f"{artifact.name}:{location} requires a positive node-to-ground load"
                )
            loads[node_a] = loads.get(node_a, 0.0) + value
        elif kind == "V":
            if node_a == "0" or node_b != "0" or value <= 0.0:
                raise SystemExit(
                    f"{artifact.name}:{location} requires a positive ground-referenced supply"
                )
            voltage_sources.append((node_a, node_b, value))
        else:
            raise SystemExit(
                f"{artifact.name}:{location} contains unsupported synthetic element "
                f"{element_name!r}"
            )

    if len(resistors) != 12 or len(loads) != 9 or len(voltage_sources) != 1:
        raise SystemExit(
            f"{artifact.name}:{spice_name} must contain exactly 12 resistors, "
            "9 loaded nodes, and one voltage source"
        )
    source_node, _source_ground, source_voltage = voltage_sources[0]
    solved_voltages, free_nodes = _solve_synthetic_network(
        nodes,
        resistors,
        loads,
        source_node,
        source_voltage,
        artifact,
        spice_name,
    )

    reference_name = f"{SYNTHETIC_CASE_PREFIX}/reference_vdd_nodes.csv"
    reference_rows = list(
        csv.DictReader(
            io.StringIO(read_bytes(reference_name).decode("utf-8"))
        )
    )
    if len(reference_rows) != 9:
        raise SystemExit(
            f"{artifact.name}:{reference_name} must contain exactly nine node rows"
        )

    reference_voltages: dict[str, float] = {"0": 0.0}
    reference_coordinates: dict[str, tuple[float, float]] = {}
    for row_number, row in enumerate(reference_rows, start=2):
        node = str(row.get("node", "")).strip()
        location = f"{reference_name}:{row_number}"
        if not node or node in reference_voltages:
            raise SystemExit(
                f"{artifact.name}:{location} requires a unique non-empty node"
            )
        reference_voltages[node] = _synthetic_number(
            row.get("voltage_V"),
            artifact,
            f"{location}:voltage_V",
        )
        reference_coordinates[node] = (
            _synthetic_number(row.get("x_um"), artifact, f"{location}:x_um"),
            _synthetic_number(row.get("y_um"), artifact, f"{location}:y_um"),
        )

    electrical_nodes = nodes - {"0"}
    if set(reference_voltages) - {"0"} != electrical_nodes:
        missing = sorted(electrical_nodes - set(reference_voltages))
        extra = sorted((set(reference_voltages) - {"0"}) - electrical_nodes)
        raise SystemExit(
            f"{artifact.name}:{reference_name} node inventory does not match SPICE: "
            f"missing={missing}, extra={extra}"
        )
    if set(loads) != electrical_nodes:
        missing = sorted(electrical_nodes - set(loads))
        extra = sorted(set(loads) - electrical_nodes)
        raise SystemExit(
            f"{artifact.name}:{spice_name} every electrical node must have one "
            f"aggregated load: missing={missing}, extra={extra}"
        )

    for node in sorted(electrical_nodes):
        _require_synthetic_close(
            solved_voltages[node],
            reference_voltages[node],
            artifact,
            f"{reference_name}:{node}:voltage_V",
            abs_tol=1.0e-12,
        )

    max_kcl_residual = 0.0
    for node in free_nodes:
        residual_terms = [loads.get(node, 0.0)]
        for node_a, node_b, resistance in resistors:
            if node_a == node:
                residual_terms.append(
                    (reference_voltages[node_a] - reference_voltages[node_b])
                    / resistance
                )
            elif node_b == node:
                residual_terms.append(
                    (reference_voltages[node_b] - reference_voltages[node_a])
                    / resistance
                )
        max_kcl_residual = max(max_kcl_residual, abs(math.fsum(residual_terms)))
    if max_kcl_residual > 1.0e-12:
        raise SystemExit(
            f"{artifact.name}:{reference_name} free-node KCL residual "
            f"{max_kcl_residual:.17g} A exceeds 1e-12 A"
        )

    instance_ids: set[str] = set()
    instance_nodes: dict[str, str] = {}
    claimed_nodes: set[str] = set()
    for row_number, row in enumerate(instance_rows, start=2):
        instance_id = str(row.get("eda_id", "")).strip()
        location = f"{SYNTHETIC_CASE_PREFIX}/instances.csv:{row_number}"
        if not instance_id or instance_id in instance_ids:
            raise SystemExit(
                f"{artifact.name}:{location} requires a unique non-empty eda_id"
            )
        instance_ids.add(instance_id)
        center = (
            _synthetic_number(row.get("x_um"), artifact, f"{location}:x_um")
            + _synthetic_number(row.get("w_um"), artifact, f"{location}:w_um") / 2.0,
            _synthetic_number(row.get("y_um"), artifact, f"{location}:y_um")
            + _synthetic_number(row.get("h_um"), artifact, f"{location}:h_um") / 2.0,
        )
        matches = [
            node
            for node, coordinate in reference_coordinates.items()
            if math.isclose(center[0], coordinate[0], rel_tol=0.0, abs_tol=1.0e-12)
            and math.isclose(center[1], coordinate[1], rel_tol=0.0, abs_tol=1.0e-12)
        ]
        if len(matches) != 1 or matches[0] in claimed_nodes:
            raise SystemExit(
                f"{artifact.name}:{location} centroid {center!r} must map uniquely "
                "to one unclaimed reference/load node"
            )
        instance_nodes[instance_id] = matches[0]
        claimed_nodes.add(matches[0])

    if claimed_nodes != electrical_nodes:
        raise SystemExit(
            f"{artifact.name}:{SYNTHETIC_CASE_PREFIX}/instances.csv centroids "
            "must cover every electrical node exactly once"
        )

    powers_by_id: dict[str, float] = {}
    power_name = f"{SYNTHETIC_CASE_PREFIX}/instance_power.csv"
    for row_number, row in enumerate(power_rows, start=2):
        instance_id = str(row.get("eda_id", "")).strip()
        location = f"{power_name}:{row_number}"
        if not instance_id or instance_id in powers_by_id:
            raise SystemExit(
                f"{artifact.name}:{location} requires a unique non-empty eda_id"
            )
        power = _synthetic_number(
            row.get("power_W"),
            artifact,
            f"{location}:power_W",
        )
        if power < 0.0:
            raise SystemExit(
                f"{artifact.name}:{location}:power_W must be nonnegative"
            )
        powers_by_id[instance_id] = power
    if set(powers_by_id) != instance_ids:
        missing = sorted(instance_ids - set(powers_by_id))
        extra = sorted(set(powers_by_id) - instance_ids)
        raise SystemExit(
            f"{artifact.name}:{power_name} IDs do not match instances.csv: "
            f"missing={missing}, extra={extra}"
        )

    for instance_id in sorted(instance_ids):
        node = instance_nodes[instance_id]
        expected_power = reference_voltages[node] * loads[node]
        _require_synthetic_close(
            powers_by_id[instance_id],
            expected_power,
            artifact,
            f"{power_name}:{instance_id}:V*I",
            abs_tol=1.0e-15,
        )

    computed_load_power = math.fsum(
        reference_voltages[node] * current
        for node, current in loads.items()
    )
    csv_load_power = math.fsum(powers_by_id.values())
    computed_grid_loss = math.fsum(
        (reference_voltages[node_a] - reference_voltages[node_b]) ** 2
        / resistance
        for node_a, node_b, resistance in resistors
    )
    computed_worst_ir = source_voltage - min(
        reference_voltages[node]
        for node in electrical_nodes
    )
    source_current = loads.get(source_node, 0.0)
    for node_a, node_b, resistance in resistors:
        if node_a == source_node:
            source_current += (
                reference_voltages[node_a] - reference_voltages[node_b]
            ) / resistance
        elif node_b == source_node:
            source_current += (
                reference_voltages[node_b] - reference_voltages[node_a]
            ) / resistance
    computed_source_power = source_voltage * source_current

    declared_supply_voltage = _synthetic_number(
        reference_meta.get("supply_voltage_V"),
        artifact,
        f"{SYNTHETIC_CASE_PREFIX}/reference_vdd_nodes.meta.json:supply_voltage_V",
    )
    declared_worst_ir = _synthetic_number(
        reference_meta.get("worst_ir_drop_V"),
        artifact,
        f"{SYNTHETIC_CASE_PREFIX}/reference_vdd_nodes.meta.json:worst_ir_drop_V",
    )
    declared_load_power = _synthetic_number(
        reference_meta.get("total_load_power_W"),
        artifact,
        f"{SYNTHETIC_CASE_PREFIX}/reference_vdd_nodes.meta.json:total_load_power_W",
    )
    declared_grid_loss = _synthetic_number(
        reference_meta.get("total_grid_loss_W"),
        artifact,
        f"{SYNTHETIC_CASE_PREFIX}/reference_vdd_nodes.meta.json:total_grid_loss_W",
    )
    declared_source_power = _synthetic_number(
        reference_meta.get("total_source_power_W"),
        artifact,
        f"{SYNTHETIC_CASE_PREFIX}/reference_vdd_nodes.meta.json:total_source_power_W",
    )
    declared_instance_total = _synthetic_number(
        power_meta.get("total_power_W"),
        artifact,
        f"{SYNTHETIC_CASE_PREFIX}/instance_power.meta.json:total_power_W",
    )
    checks = (
        (
            declared_supply_voltage,
            source_voltage,
            "reference_vdd_nodes.meta.json:supply_voltage_V",
            1.0e-15,
        ),
        (
            declared_worst_ir,
            computed_worst_ir,
            "reference_vdd_nodes.meta.json:worst_ir_drop_V",
            1.0e-15,
        ),
        (
            csv_load_power,
            computed_load_power,
            "instance_power.csv:sum(V*I)",
            1.0e-15,
        ),
        (
            declared_instance_total,
            computed_load_power,
            "instance_power.meta.json:total_power_W",
            1.0e-15,
        ),
        (
            declared_load_power,
            computed_load_power,
            "reference_vdd_nodes.meta.json:total_load_power_W",
            1.0e-15,
        ),
        (
            declared_grid_loss,
            computed_grid_loss,
            "reference_vdd_nodes.meta.json:total_grid_loss_W",
            1.0e-15,
        ),
        (
            declared_source_power,
            computed_source_power,
            "reference_vdd_nodes.meta.json:total_source_power_W",
            1.0e-15,
        ),
        (
            computed_source_power,
            computed_load_power + computed_grid_loss,
            "computed source=load+resistor loss closure",
            1.0e-15,
        ),
        (
            declared_source_power,
            declared_load_power + declared_grid_loss,
            "declared source=load+resistor loss closure",
            1.0e-15,
        ),
    )
    for actual, expected, location, tolerance in checks:
        _require_synthetic_close(
            actual,
            expected,
            artifact,
            f"{SYNTHETIC_CASE_PREFIX}/{location}",
            abs_tol=tolerance,
        )

    dbu_per_micron = _synthetic_number(
        manifest.get("dbu_per_micron"),
        artifact,
        f"{SYNTHETIC_CASE_PREFIX}/manifest.json:dbu_per_micron",
    )
    for node, (x_um, y_um) in reference_coordinates.items():
        fields = node.split("_")
        if (
            len(fields) < 4
            or fields[0] != "VDD"
            or not fields[1].lstrip("+-").isdigit()
            or not fields[2].lstrip("+-").isdigit()
        ):
            raise SystemExit(
                f"{artifact.name}:{reference_name} node {node!r} does not encode "
                "VDD x/y DBU coordinates"
            )
        _require_synthetic_close(
            float(fields[1]),
            x_um * dbu_per_micron,
            artifact,
            f"{reference_name}:{node}:x_dbu",
            abs_tol=1.0e-9,
        )
        _require_synthetic_close(
            float(fields[2]),
            y_um * dbu_per_micron,
            artifact,
            f"{reference_name}:{node}:y_dbu",
            abs_tol=1.0e-9,
        )


def _validate_synthetic_case(
    files: set[str],
    read_bytes,
    artifact: Path,
) -> None:
    """Require a complete, first-party synthetic fixture and reject the old GCD case."""

    legacy = sorted(name for name in files if name.startswith(LEGACY_GCD_PREFIX))
    if legacy:
        raise SystemExit(f"{artifact.name} still contains removed GCD-derived assets: {legacy}")

    present = files.intersection(SYNTHETIC_CASE_ASSETS)
    if present != SYNTHETIC_CASE_ASSETS:
        raise SystemExit(
            f"{artifact.name} contains an incomplete synthetic PDN fixture: "
            f"missing={sorted(SYNTHETIC_CASE_ASSETS - present)}"
        )

    manifest_name = f"{SYNTHETIC_CASE_PREFIX}/manifest.json"
    manifest = json.loads(read_bytes(manifest_name))
    provenance = manifest.get("provenance", {})
    expected_provenance = {
        "source_kind": "project_authored_synthetic_data",
        "origin": "project_authored_synthetic_fixture",
        "license": "Apache-2.0",
        "generator": "generate_case.py",
        "randomness": "none",
        "third_party_design_data": False,
    }
    if manifest.get("design") != "synthetic_pdn":
        raise SystemExit(f"{artifact.name}:{manifest_name} must identify design='synthetic_pdn'")
    for key, expected in expected_provenance.items():
        if provenance.get(key) != expected:
            raise SystemExit(
                f"{artifact.name}:{manifest_name} provenance.{key} must be {expected!r}"
            )

    instance_name = f"{SYNTHETIC_CASE_PREFIX}/instances.csv"
    instance_rows = list(
        csv.DictReader(io.StringIO(read_bytes(instance_name).decode("utf-8")))
    )
    if manifest.get("n_instances") != len(instance_rows) or len(instance_rows) != 9:
        raise SystemExit(
            f"{artifact.name}:{manifest_name} n_instances must match the 9-row fixture"
        )

    power_name = f"{SYNTHETIC_CASE_PREFIX}/instance_power.csv"
    power_rows = list(csv.DictReader(io.StringIO(read_bytes(power_name).decode("utf-8"))))
    power_total = math.fsum(
        _synthetic_number(
            row.get("power_W"),
            artifact,
            f"{power_name}:{row_number}:power_W",
        )
        for row_number, row in enumerate(power_rows, start=2)
    )
    power_meta_name = f"{SYNTHETIC_CASE_PREFIX}/instance_power.meta.json"
    power_meta = json.loads(read_bytes(power_meta_name))
    if (
        len(power_rows) != len(instance_rows)
        or abs(power_total - float(power_meta.get("total_power_W", -1.0))) > 1e-15
        or power_meta.get("instance_power_model") != "closed_form_dc_load_power"
    ):
        raise SystemExit(
            f"{artifact.name}:{power_name} does not match its synthetic power metadata"
        )

    reference_meta_name = f"{SYNTHETIC_CASE_PREFIX}/reference_vdd_nodes.meta.json"
    reference_meta = json.loads(read_bytes(reference_meta_name))
    _validate_synthetic_electrical_reference(
        read_bytes,
        artifact,
        manifest,
        instance_rows,
        power_rows,
        power_meta,
        reference_meta,
    )
    source_power = float(reference_meta.get("total_source_power_W", -1.0))
    grid_loss = float(reference_meta.get("total_grid_loss_W", -1.0))
    if (
        reference_meta.get("reference_source") != "closed_form_symmetric_resistor_grid"
        or abs(float(reference_meta.get("worst_ir_drop_V", -1.0)) - 2.5e-4) > 1e-15
        or abs(source_power - power_total - grid_loss) > 1e-15
    ):
        raise SystemExit(
            f"{artifact.name}:{reference_meta_name} fails the closed-form conservation record"
        )

    hashes = manifest.get("artifact_sha256", {})
    if not isinstance(hashes, dict) or not hashes:
        raise SystemExit(f"{artifact.name}:{manifest_name} requires artifact_sha256")
    expected_hashed_names = {
        PurePosixPath(name).name
        for name in SYNTHETIC_CASE_ASSETS
        if PurePosixPath(name).name not in {"README.md", "generate_case.py", "manifest.json"}
    }
    if set(hashes) != expected_hashed_names:
        raise SystemExit(
            f"{artifact.name}:{manifest_name} artifact_sha256 inventory mismatch"
        )
    for basename, expected_hash in hashes.items():
        member = f"{SYNTHETIC_CASE_PREFIX}/{basename}"
        actual_hash = hashlib.sha256(read_bytes(member)).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", str(expected_hash)) or actual_hash != expected_hash:
            raise SystemExit(
                f"{artifact.name}:{member} SHA-256 does not match the synthetic manifest"
            )


def _validate_openroad_redistribution_notice(
    read_bytes,
    artifact: Path,
    *,
    license_name: str,
    notice_name: str,
) -> None:
    """Keep the redistributed binary notice pinned to the exact OpenROAD revision."""

    license_bytes = read_bytes(license_name)
    actual_hash = hashlib.sha256(license_bytes).hexdigest()
    if actual_hash != OPENROAD_LICENSE_SHA256:
        raise SystemExit(
            f"{artifact.name}:{license_name} must be the exact BSD notice from "
            "OpenROAD revision a008522d88b669ac4c985609533cf5a3d2649222 "
            f"(expected SHA-256 {OPENROAD_LICENSE_SHA256}, got {actual_hash})"
        )

    notice = read_bytes(notice_name).decode("utf-8")
    if OPENROAD_COPYRIGHT_NOTICE not in notice:
        raise SystemExit(
            f"{artifact.name}:{notice_name} must identify the copyright notice "
            "retained for the pinned OpenROAD binary"
        )


def _validate_source_tree(
    source_root: Path,
    *,
    allow_unapproved_core_ref: bool,
    allow_untracked_required: bool = False,
    allow_dirty_source: bool = False,
) -> int:
    """Check releasable tracked plus non-ignored untracked inputs.

    A publishable source result requires a clean worktree. Audit callers may
    explicitly inspect an uncommitted cleanup, but existing operational/readiness
    notes are always rejected.
    """

    status_result = subprocess.run(
        [
            "git",
            "-C",
            str(source_root),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        check=True,
        capture_output=True,
    )
    if status_result.stdout:
        message = (
            f"{source_root} is not clean; release source validation requires "
            "all tracked and non-ignored files to be committed"
        )
        if not allow_dirty_source:
            raise SystemExit(message)
        print(f"WARNING: {message} (audit override enabled)")

    tracked_result = subprocess.run(
        [
            "git",
            "-C",
            str(source_root),
            "ls-files",
            "--cached",
            "-z",
        ],
        check=True,
        capture_output=True,
    )
    untracked_result = subprocess.run(
        [
            "git",
            "-C",
            str(source_root),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        check=True,
        capture_output=True,
    )
    tracked = {
        item.decode("utf-8", errors="strict")
        for item in tracked_result.stdout.split(b"\0")
        if item
    }
    untracked = {
        item.decode("utf-8", errors="strict")
        for item in untracked_result.stdout.split(b"\0")
        if item
    }
    names = sorted(tracked | untracked)
    _validate_names(names, source_root)

    missing = sorted(
        name
        for name in names
        if not (source_root / PurePosixPath(name)).exists()
        and not (source_root / PurePosixPath(name)).is_symlink()
        and not _is_forbidden_path(name)
    )
    if missing:
        raise SystemExit(
            f"{source_root} has tracked releasable paths missing from the working tree: {missing}"
        )

    available = {
        name
        for name in names
        if (source_root / PurePosixPath(name)).exists()
        or (source_root / PurePosixPath(name)).is_symlink()
    }
    symlinks = sorted(
        name
        for name in available
        if (source_root / PurePosixPath(name)).is_symlink()
    )
    if symlinks:
        raise SystemExit(f"{source_root} contains symbolic links: {symlinks}")

    releasable = available
    _require_files(releasable, REQUIRED_SDIST_FILES, source_root)
    untracked_required = sorted(REQUIRED_SDIST_FILES - tracked)
    if untracked_required:
        message = (
            f"{source_root} has required release inputs that are not tracked: "
            f"{untracked_required}"
        )
        if not allow_untracked_required:
            raise SystemExit(message)
        print(f"WARNING: {message} (audit override enabled)")
    _reject_forbidden_files(releasable, source_root)
    _validate_public_source_inventories(
        releasable,
        source_root,
        root_files=PUBLIC_ROOT_FILES,
    )
    for name in sorted(releasable):
        path = source_root / PurePosixPath(name)
        if path.is_file():
            _validate_text(name, path.read_bytes(), source_root)
    _validate_core_release_inputs(
        releasable,
        lambda name: (source_root / PurePosixPath(name)).read_bytes(),
        source_root,
        allow_unapproved_core_ref=allow_unapproved_core_ref,
    )
    _validate_synthetic_case(
        releasable,
        lambda name: (source_root / PurePosixPath(name)).read_bytes(),
        source_root,
    )
    _validate_openroad_redistribution_notice(
        lambda name: (source_root / PurePosixPath(name)).read_bytes(),
        source_root,
        license_name="LICENSES/OpenROAD-BSD-3-Clause.txt",
        notice_name="NOTICE",
    )
    _validate_entry_point_ledger(
        releasable,
        lambda name: (source_root / PurePosixPath(name)).read_bytes(),
        source_root,
    )
    return len(releasable)


def _validate_wheel(wheel: Path) -> int:
    with zipfile.ZipFile(wheel) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        _validate_names(names, wheel)
        symlinks = sorted(
            member.filename
            for member in members
            if stat.S_ISLNK((member.external_attr >> 16) & 0xFFFF)
        )
        if symlinks:
            raise SystemExit(f"{wheel.name} contains symbolic links: {symlinks}")

        files = {member.filename for member in members if not member.is_dir()}
        metadata_roots = {
            PurePosixPath(name).parts[0]
            for name in files
            if len(PurePosixPath(name).parts) == 2
            and PurePosixPath(name).parts[0].endswith(".dist-info")
            and PurePosixPath(name).name == "METADATA"
        }
        if len(metadata_roots) != 1:
            raise SystemExit(
                f"{wheel.name} must contain exactly one .dist-info/METADATA file"
            )
        dist_info = metadata_roots.pop()
        required = PUBLIC_PACKAGE_FILES | {
            f"{dist_info}/entry_points.txt",
            f"{dist_info}/licenses/LICENSE",
            f"{dist_info}/licenses/LICENSES/CC-BY-4.0.txt",
            f"{dist_info}/licenses/LICENSES/OpenROAD-BSD-3-Clause.txt",
            f"{dist_info}/licenses/NOTICE",
            f"{dist_info}/licenses/THIRD_PARTY.md",
            f"{dist_info}/licenses/docs/LICENSE.md",
        }
        _require_files(files, required, wheel)
        entry_points_name = f"{dist_info}/entry_points.txt"
        if (
            archive.read(entry_points_name).decode("utf-8")
            != EXPECTED_CONSOLE_ENTRY_POINTS
        ):
            raise SystemExit(
                f"{wheel.name}:{entry_points_name} differs from the reviewed "
                "workbench console entry point"
            )
        _reject_forbidden_files(files, wheel)
        _validate_exact_subtree(
            files,
            wheel,
            "eda_multiphysics",
            PUBLIC_PACKAGE_FILES,
        )
        for member in members:
            if not member.is_dir():
                _validate_text(member.filename, archive.read(member), wheel)
        _validate_synthetic_case(
            files,
            archive.read,
            wheel,
        )
        _validate_openroad_redistribution_notice(
            archive.read,
            wheel,
            license_name=f"{dist_info}/licenses/LICENSES/OpenROAD-BSD-3-Clause.txt",
            notice_name=f"{dist_info}/licenses/NOTICE",
        )
    return len(files)


def _validate_sdist(
    sdist: Path,
    *,
    allow_unapproved_core_ref: bool,
) -> int:
    with tarfile.open(sdist, mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        _validate_names(names, sdist)

        unsupported = sorted(
            member.name
            for member in members
            if not (member.isfile() or member.isdir())
        )
        if unsupported:
            raise SystemExit(
                f"{sdist.name} contains links or special-file entries: {unsupported}"
            )

        roots = {
            PurePosixPath(member.name).parts[0]
            for member in members
            if PurePosixPath(member.name).parts
        }
        if len(roots) != 1:
            raise SystemExit(f"{sdist.name} must contain exactly one top-level directory")
        root = roots.pop()

        file_members = {
            PurePosixPath(*PurePosixPath(member.name).parts[1:]).as_posix(): member
            for member in members
            if member.isfile()
            and len(PurePosixPath(member.name).parts) > 1
            and PurePosixPath(member.name).parts[0] == root
        }
        files = set(file_members)
        _require_files(files, REQUIRED_SDIST_FILES, sdist)
        _reject_forbidden_files(files, sdist)
        _validate_public_source_inventories(
            files,
            sdist,
            root_files=PUBLIC_SDIST_ROOT_FILES,
            allowed_generated_subtrees={"coupfe_eda.egg-info"},
        )
        _validate_exact_subtree(
            files,
            sdist,
            "coupfe_eda.egg-info",
            PUBLIC_SDIST_METADATA_FILES,
        )
        entry_points_name = "coupfe_eda.egg-info/entry_points.txt"
        entry_points_stream = archive.extractfile(file_members[entry_points_name])
        if entry_points_stream is None:
            raise SystemExit(f"{sdist.name}:{entry_points_name} could not be read")
        if entry_points_stream.read().decode("utf-8") != EXPECTED_CONSOLE_ENTRY_POINTS:
            raise SystemExit(
                f"{sdist.name}:{entry_points_name} differs from the reviewed "
                "workbench console entry point"
            )
        _validate_public_tests(files, sdist)
        for name, member in file_members.items():
            stream = archive.extractfile(member)
            if stream is None:
                raise SystemExit(f"{sdist.name}:{name} could not be read")
            _validate_text(name, stream.read(), sdist)
        def _read_sdist_file(name: str) -> bytes:
            stream = archive.extractfile(file_members[name])
            if stream is None:
                raise SystemExit(f"{sdist.name}:{name} could not be read")
            return stream.read()

        _validate_core_release_inputs(
            files,
            _read_sdist_file,
            sdist,
            allow_unapproved_core_ref=allow_unapproved_core_ref,
        )
        _validate_synthetic_case(
            files,
            _read_sdist_file,
            sdist,
        )
        _validate_openroad_redistribution_notice(
            _read_sdist_file,
            sdist,
            license_name="LICENSES/OpenROAD-BSD-3-Clause.txt",
            notice_name="NOTICE",
        )
        _validate_entry_point_ledger(files, _read_sdist_file, sdist)
    return len(files)


def validate(
    dist_dir: Path,
    source_root: Path | None = None,
    *,
    allow_unapproved_core_ref: bool = False,
    allow_untracked_required: bool = False,
    allow_dirty_source: bool = False,
) -> None:
    source_count = (
        _validate_source_tree(
            source_root.resolve(),
            allow_unapproved_core_ref=allow_unapproved_core_ref,
            allow_untracked_required=allow_untracked_required,
            allow_dirty_source=allow_dirty_source,
        )
        if source_root is not None
        else None
    )
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(
            f"expected one wheel and one sdist in {dist_dir}, "
            f"found {len(wheels)} wheel(s) and {len(sdists)} sdist(s)"
        )

    wheel_count = _validate_wheel(wheels[0])
    sdist_count = _validate_sdist(
        sdists[0],
        allow_unapproved_core_ref=allow_unapproved_core_ref,
    )
    source_summary = (
        f"source tree ({source_count} files), " if source_count is not None else ""
    )
    print(
        f"checked {source_summary}{wheels[0].name} ({wheel_count} files) and "
        f"{sdists[0].name} ({sdist_count} files)"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dist_dir",
        nargs="?",
        type=Path,
        default=Path("dist"),
        help="directory containing exactly one wheel and one .tar.gz sdist",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("."),
        help="git worktree checked before the artifacts (default: current directory)",
    )
    parser.add_argument(
        "--artifacts-only",
        action="store_true",
        help="skip the source-tree check (useful before cleanup deletions are committed)",
    )
    parser.add_argument(
        "--allow-unapproved-core-ref-for-audit",
        "--allow-legacy-core-pin-for-audit",
        dest="allow_unapproved_core_ref_for_audit",
        action="store_true",
        help=(
            "inspect artifacts before the pinned clean-root Core revision is "
            "confirmed publicly reachable; the result is not publishable "
            "(the legacy spelling is retained as an alias)"
        ),
    )
    parser.add_argument(
        "--allow-untracked-required-for-audit",
        action="store_true",
        help=(
            "inspect a review worktree whose required new release files are not "
            "yet tracked; the source result is not publishable"
        ),
    )
    parser.add_argument(
        "--allow-dirty-source-for-audit",
        action="store_true",
        help=(
            "inspect an uncommitted review worktree; the source result is not "
            "publishable"
        ),
    )
    args = parser.parse_args()
    validate(
        args.dist_dir,
        source_root=None if args.artifacts_only else args.source_root,
        allow_unapproved_core_ref=args.allow_unapproved_core_ref_for_audit,
        allow_untracked_required=args.allow_untracked_required_for_audit,
        allow_dirty_source=args.allow_dirty_source_for_audit,
    )


if __name__ == "__main__":
    main()
