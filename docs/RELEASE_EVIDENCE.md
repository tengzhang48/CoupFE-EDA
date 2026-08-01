# Release evidence policy

A release statement should be traceable to a retained command log, immutable
source identity, environment summary, and artifact digest. A status sentence
without those records is not a release checkpoint.

This policy records software/reproducibility evidence. It does not convert a
synthetic or component check into real-device validation.

## Checkpoint contents

Create each checkpoint as a new timestamped directory outside the Git
worktree. Do not overwrite an earlier record. The recorder creates:

- `manifest.json`: mode, source branch/revision, dirty-state digest,
  Python/platform/package versions, imported Core identity, commands, exit
  codes, durations, and artifact digests;
- `source-status.txt`: the exact source status at start;
- `logs/*.log`: combined output for each command;
- `artifacts/`: the wheel and source distribution retained by the run;
- `SHA256SUMS`: release-artifact hashes;
- `EVIDENCE_SHA256SUMS`: hashes for the complete checkpoint; and
- `README.md`: human-readable disposition.

The directory and files are created with private permissions. Recognizable
credentials and local paths are redacted, but credentials must never be placed
in commands, fixtures, or release inputs.

## Release mode

From the repository root:

```bash
python .github/scripts/record_release_evidence.py \
  --output <private-evidence-root>/eda-<UTC-time>-<short-commit>-release
```

Release mode requires a clean tree. It records environment and Core provenance,
runs the gate harness, default tests, optional toolchain preflight/tests,
builds an sdist and a wheel from that sdist, runs strict Twine and installed-
wheel checks, and applies the release-artifact guard. Execution stops at a
failed command.

The expected Core revision is read from `setup.sh`; for this candidate it is
`e2f42ed5772850a0a23a2ce434f430c287eae5c8`. The recorder checks the imported
root, Git revision, origin, and branch before treating the run as release mode.

## Audit mode

During curation, a non-publishable checkpoint can be recorded:

```bash
python .github/scripts/record_release_evidence.py \
  --mode audit \
  --output <private-evidence-root>/eda-<UTC-time>-<short-commit>-audit
```

Audit mode runs the maintained fast partition and uses explicitly named guard
overrides for a dirty candidate, an unapproved Core reference, and untracked
required inputs. Its manifest always reports `publishable: false`; it cannot
replace the final clean release-mode run.

## Build boundary

`dist/`, `build/`, `*.egg-info`, pytest caches, Python bytecode, and generated
kernel products inside the worktree are disposable. They are not evidence.

The recorder copies the tracked plus non-ignored untracked release inventory to
a temporary source directory, builds there, retains the resulting wheel/sdist
in the checkpoint, and removes the temporary tree. CI build products are useful
checks but are not a publication checkpoint unless the complete record is
retained together.

## Review checklist

Before publication:

1. confirm the candidate and Core revisions are reachable and immutable;
2. run release mode from the exact clean root;
3. require every recorded command to return zero and review skips separately;
4. verify `sha256sum -c SHA256SUMS` and
   `sha256sum -c EVIDENCE_SHA256SUMS` in the checkpoint directory;
5. inspect wheel and sdist inventory, license files, fixture provenance, and
   installed-wheel resource access;
6. scan the final source and artifacts for credentials, private paths, and
   unintended files; and
7. archive the checkpoint under the release tag/revision in protected storage
   and verify both checksum files after transfer.

The scientific/model boundary is defined in
[Capabilities](capabilities.md) and [Validation guide](VALIDATION_GUIDE.md),
not by the recorder's `publishable` field alone.
