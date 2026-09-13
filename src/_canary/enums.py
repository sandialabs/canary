# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Backward-compatible re-export shim.

The canonical location of these symbols is now ``canary_pyt.enums``.
This module re-exports everything from there so that existing code that
imports from ``_canary.enums`` continues to work without modification.
"""

import warnings

warnings.warn(
    "_canary.enums is deprecated; import from canary_pyt.enums instead.",
    DeprecationWarning,
    stacklevel=2,
)

from canary_pyt.enums import centered_parameter_space  # noqa: F401, E402
from canary_pyt.enums import enums  # noqa: F401, E402
from canary_pyt.enums import list_parameter_space  # noqa: F401, E402
from canary_pyt.enums import random_parameter_space  # noqa: F401, E402

__all__ = ["enums", "list_parameter_space", "centered_parameter_space", "random_parameter_space"]
