"""Resolve auditable CoupFE Core source identity across shared environments."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


APPROVED_COUPFE_URL = "https://github.com/tengzhang48/CoupFE.git"
APPROVED_COUPFE_REVISION = "e2f42ed5772850a0a23a2ce434f430c287eae5c8"
_REVISION = re.compile(r"^[0-9a-f]{40}$")


class SourceIdentityError(RuntimeError):
    """Raised when the imported Core cannot be tied to reviewed source."""


@dataclass(frozen=True)
class CoupFESourceIdentity:
    revision: str
    url: str
    source_kind: str
    root: Path

    def as_record(self) -> dict[str, str]:
        return {
            "revision": self.revision,
            "url": self.url,
            "sourceKind": self.source_kind,
        }


def _git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=check,
        capture_output=True,
        text=True,
    )


def _checkout_identity(module_path: Path) -> CoupFESourceIdentity | None:
    discovered = _git(module_path.parent, "rev-parse", "--show-toplevel", check=False)
    if discovered.returncode != 0:
        return None
    root = Path(discovered.stdout.strip()).resolve()
    if module_path != (root / "coupfe/__init__.py").resolve():
        # A site-packages directory can sit inside an unrelated enclosing Git
        # checkout. Do not attribute that repository's HEAD to CoupFE.
        return None
    revision = _git(root, "rev-parse", "HEAD").stdout.strip()
    origin = _git(root, "remote", "get-url", "origin").stdout.strip()
    if _REVISION.fullmatch(revision) is None:
        raise SourceIdentityError("CoupFE checkout returned a non-canonical revision")
    if _git(root, "status", "--porcelain", "--untracked-files=all").stdout:
        raise SourceIdentityError("CoupFE checkout must be clean")
    return CoupFESourceIdentity(
        revision=revision,
        url=origin,
        source_kind="clean-git-checkout",
        root=root,
    )


def _direct_url_path(distribution: metadata.Distribution) -> Path:
    matches = [
        item
        for item in (distribution.files or ())
        if item.name == "direct_url.json" and ".dist-info" in PurePosixPath(str(item)).parts[-2]
    ]
    if len(matches) != 1:
        raise SourceIdentityError("installed CoupFE must provide one PEP 610 direct_url.json")
    return Path(distribution.locate_file(matches[0])).resolve()


def _verify_record(distribution: metadata.Distribution, package_root: Path) -> None:
    installation_root = Path(distribution.locate_file("")).resolve()
    records = {str(item): item for item in (distribution.files or ())}
    installed = sorted(
        path
        for path in package_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    if not installed:
        raise SourceIdentityError("installed CoupFE package contains no auditable files")
    for path in installed:
        try:
            relative = path.relative_to(installation_root).as_posix()
        except ValueError as error:
            raise SourceIdentityError("installed CoupFE file lies outside its distribution") from error
        record = records.get(relative)
        if record is None or record.hash is None or record.hash.mode != "sha256":
            raise SourceIdentityError(f"installed CoupFE file lacks a SHA-256 RECORD entry: {relative}")
        observed = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).decode().rstrip("=")
        if observed != record.hash.value:
            raise SourceIdentityError(f"installed CoupFE file differs from its RECORD hash: {relative}")


def _installed_identity(module_path: Path) -> CoupFESourceIdentity:
    try:
        distribution = metadata.distribution("coupfe")
    except metadata.PackageNotFoundError as error:
        raise SourceIdentityError("imported CoupFE has no installed distribution metadata") from error
    try:
        direct_url = json.loads(_direct_url_path(distribution).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SourceIdentityError("installed CoupFE has invalid PEP 610 provenance") from error
    vcs = direct_url.get("vcs_info")
    if not isinstance(vcs, dict) or vcs.get("vcs") != "git":
        raise SourceIdentityError("installed CoupFE is not a PEP 610 Git installation")
    revision = vcs.get("commit_id")
    requested = vcs.get("requested_revision")
    url = direct_url.get("url")
    if not isinstance(revision, str) or _REVISION.fullmatch(revision) is None:
        raise SourceIdentityError("installed CoupFE has a non-canonical commit ID")
    if requested != revision or not isinstance(url, str):
        raise SourceIdentityError("installed CoupFE requested revision does not match its commit ID")
    expected_module = Path(distribution.locate_file("coupfe/__init__.py")).resolve()
    if module_path != expected_module:
        raise SourceIdentityError("imported CoupFE path differs from installed distribution metadata")
    _verify_record(distribution, module_path.parent)
    return CoupFESourceIdentity(
        revision=revision,
        url=url,
        source_kind="verified-pep610-vcs-install",
        root=module_path.parent,
    )


def resolve_coupfe_identity(
    *,
    expected_url: str = APPROVED_COUPFE_URL,
    expected_revision: str = APPROVED_COUPFE_REVISION,
) -> CoupFESourceIdentity:
    """Return a verified exact-pin identity for the imported CoupFE package.

    A canonical clean Git checkout is preferred. A shared environment such as
    CoupFE-Cardiac is also accepted when PEP 610 records the exact VCS commit
    and every installed package file still matches its PEP 376 RECORD digest.
    """

    try:
        import coupfe
    except ImportError as error:
        raise SourceIdentityError("CoupFE is not importable") from error
    if coupfe.__file__ is None:
        raise SourceIdentityError("imported CoupFE has no filesystem path")
    module_path = Path(coupfe.__file__).resolve()
    identity = _checkout_identity(module_path) or _installed_identity(module_path)
    if identity.url != expected_url:
        raise SourceIdentityError(
            f"CoupFE source URL {identity.url!r} differs from {expected_url!r}"
        )
    if identity.revision != expected_revision:
        raise SourceIdentityError(
            f"CoupFE revision {identity.revision} differs from {expected_revision}"
        )
    return identity
