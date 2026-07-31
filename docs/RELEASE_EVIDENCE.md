# Release evidence and transient-build policy

Release claims must be reproducible from retained evidence, not reconstructed
from a status note. A passing statement without its complete command output,
source identity, environment summary, and artifact digest is a historical
observation rather than current release evidence.

## Required checkpoint contents

Each reviewed checkpoint is a new, timestamped directory outside the Git
worktree. Do not overwrite a prior checkpoint or use an unlabeled mutable name
such as `current`. Keep the directory private (`0700`) and its files private
(`0600`). It contains:

- `manifest.json`: mode, source branch and revision, dirty-state digest,
  Python/platform/package versions, the imported Core Git identity and symbolic
  location, exact commands, exit codes, and durations;
- `source-status.txt`: the exact porcelain status (empty for a release run);
- `logs/*.log`: complete combined standard output and error for every command;
- `artifacts/`: the wheel and source distribution built by that run;
- `SHA256SUMS`: SHA-256 sidecar for the wheel and source distribution;
- `EVIDENCE_SHA256SUMS`: SHA-256 sidecar for the complete evidence record; and
- `README.md`: a human-readable disposition, including whether the checkpoint
  can support publication.

Review both the logs and the manifest before relying on a checkpoint. The
recorder removes credential-like environment variables and redacts recognizable
tokens and local paths in command output. Never put a credential in a command
argument, fixture, or release input.

## Standard command

From the repository root, write to a new directory under the private evidence
store:

```bash
python .github/scripts/record_release_evidence.py \
  --output <private-evidence-root>/eda-<UTC-timestamp>-<short-commit>-release
```

Release mode fails before testing if the worktree has tracked or untracked
changes. Before the numerical gates, it proves that Python imports the clean
`.deps/CoupFE` checkout at the declared full revision, that its origin and
public branch are anonymously reachable, and that the packaging tools are
installed. It records the Python and, when active, conda environments, then
runs the standalone trust harness, the complete default test tier, a toolchain
dependency preflight, the complete toolchain tier, an sdist build, a wheel
build from that sdist, strict Twine checks, an installed-wheel/resource smoke
from a disposable directory, and the release artifact guard without
overrides. A pass is necessary release evidence; it does not turn
synthetic/component validation into real-device validation.

During curation, a deliberately non-publishable checkpoint can be recorded:

```bash
python .github/scripts/record_release_evidence.py \
  --mode audit \
  --output <private-evidence-root>/eda-<UTC-timestamp>-<short-commit>-audit
```

Audit mode runs the maintained dependency-compatible fast partition and passes
only the explicitly named unapproved-Core-ref, untracked-required-file, and
dirty-source audit overrides to the artifact guard. Its README and manifest always state
`publishable: false`. It cannot substitute for the final clean-root run.

## Build-directory boundary

`dist/`, `build/`, `*.egg-info`, pytest caches, and Python bytecode inside the
worktree are disposable products. They are ignored by Git and are never
evidence. The recorder copies exactly the tracked plus non-ignored untracked
release-input inventory to a temporary directory; this excludes ignored
toolchain products without dropping an intentionally tracked source file that
also matches a broad ignore rule. It builds there, copies the resulting wheel
and sdist into the private checkpoint, and then removes the temporary tree.

Fast CI uses a job-local `dist/` to validate builds and installed-wheel imports,
but it does not retain a publication checkpoint. Only artifacts inside a
passed release-mode checkpoint are publication candidates. If a future release
workflow uploads evidence, it must retain the two artifacts, logs, manifest,
README, and both checksum sidecars together; a wheel or sdist copied alone is
an incomplete record.

## Final acceptance

Before publication:

1. use the final reachable public CoupFE revision consistently in every release
   input;
2. run release mode from the exact clean public root;
3. require every recorded command to exit zero and review the toolchain log for
   skips;
4. verify `sha256sum -c SHA256SUMS` and
   `sha256sum -c EVIDENCE_SHA256SUMS` from the checkpoint directory;
5. perform the final sensitive-data and private-path scan; and
6. archive the new, non-overwritten checkpoint under the released tag and
   commit in read-only or write-once storage, verifying both checksum sidecars
   before and after transfer.

The retained record supports statements about what was run and packaged. The
scientific claim boundary remains the one documented in the validation guide
and release plan.
