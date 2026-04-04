"""Compatibility shim for legacy NTT imports.

The Mutant profile is now implemented in strategies.mutant, but we keep this
module as a light re-export so older internal references do not break.
"""

from strategies.mutant import *  # noqa: F401,F403
