"""Install one built wheel outside the checkout and smoke its public resources."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SMOKE = r"""
import importlib.metadata
import importlib.resources
import json
import sys
from pathlib import Path

wheel_site = Path(sys.argv[1]).resolve()
import eda_multiphysics
from coupfe.codegen.generators.element_config import ELEMENT_CONFIGS
from eda_multiphysics.tet_element import TET4_CONFIG

module_path = Path(eda_multiphysics.__file__).resolve()
try:
    module_path.relative_to(wheel_site)
except ValueError as exc:
    raise SystemExit(
        f"eda_multiphysics imported from {module_path}, outside {wheel_site}"
    ) from exc

distribution_root = Path(
    importlib.metadata.distribution("coupfe-eda").locate_file("")
).resolve()
try:
    distribution_root.relative_to(wheel_site)
except ValueError as exc:
    raise SystemExit(
        f"coupfe-eda metadata resolved under {distribution_root}, outside {wheel_site}"
    ) from exc

package_files = importlib.resources.files("eda_multiphysics")
resources = (
    "schemas/validation_manifest.schema.json",
    "cases/synthetic_pdn/manifest.json",
)
for resource_name in resources:
    resource = package_files.joinpath(*resource_name.split("/"))
    if not resource.is_file():
        raise SystemExit(f"installed wheel is missing {resource_name}")
    with resource.open("r", encoding="utf-8") as stream:
        if not isinstance(json.load(stream), dict):
            raise SystemExit(f"installed resource {resource_name} is not a JSON object")

if TET4_CONFIG is not ELEMENT_CONFIGS["tet4"]:
    raise SystemExit("installed EDA package did not resolve Core's native tet4 config")

print(
    json.dumps(
        {
            "import_path": "$WHEEL_SITE/eda_multiphysics/__init__.py",
            "resources": list(resources),
            "version": importlib.metadata.version("coupfe-eda"),
        },
        sort_keys=True,
    )
)
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        parser.error("wheel must name one existing .whl file")

    with tempfile.TemporaryDirectory(prefix="coupfe-eda-wheel-smoke-") as temporary:
        temporary_root = Path(temporary)
        wheel_site = temporary_root / "wheel-site"
        neutral_cwd = temporary_root / "cwd"
        neutral_cwd.mkdir()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-compile",
                "--no-deps",
                "--target",
                str(wheel_site),
                str(wheel),
            ],
            check=True,
        )
        environment = dict(os.environ)
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(wheel_site)
        subprocess.run(
            [sys.executable, "-c", SMOKE, str(wheel_site)],
            cwd=neutral_cwd,
            env=environment,
            check=True,
        )


if __name__ == "__main__":
    main()
