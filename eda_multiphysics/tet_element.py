"""Native CoupFE Tet4 configuration used by the EDA geometry adapters.

Tet4 is a general finite-element/code-generation primitive and therefore belongs in
CoupFE core. CoupFE-EDA intentionally carries no copied shape-function template and
does not patch core's template resolver. Importing this module fails clearly when the
installed core predates native ``tet4`` support.
"""
from __future__ import annotations

from coupfe.codegen.generators.element_config import ELEMENT_CONFIGS


def tet4_config():
    """Return core's native linear-tetrahedron configuration or fail closed."""
    try:
        return ELEMENT_CONFIGS["tet4"]
    except KeyError as exc:
        raise ImportError(
            "CoupFE-EDA Tet4 workflows require a CoupFE core containing native "
            "'tet4' code-generation support; the consumer-side fallback was removed "
            "from the public release."
        ) from exc


TET4_CONFIG = tet4_config()
