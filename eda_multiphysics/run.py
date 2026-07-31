"""One-command entry point for the EDA-multiphysics suite.

  python -m eda_multiphysics.run            # run all validation trust-gates (~30 s)

The suite combines analytic/literature references, independent-path
comparisons, invariants, interface/structural checks, and broken controls. This
is the trust layer; caller-supplied OpenROAD-to-multiphysics demonstrations need
the EDA toolchain, input rights, and case-specific qualification. See
RESULTS.md.
"""

from __future__ import annotations

from .gates import run_all


def main():
    rs = run_all()
    print(f"\n{'EDA-multiphysics trust gates':<46}{'status':>8}  detail")
    print("-" * 86)
    for r in rs:
        print(f"{r['name']:<46}{'PASS' if r['ok'] else 'FAIL':>8}  {r['detail']}")
    print("-" * 86)
    n = sum(r["ok"] for r in rs)
    print(f"  {n}/{len(rs)} gates pass\n")
    return all(r["ok"] for r in rs)


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
