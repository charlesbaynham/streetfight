"""Pure-Python player identification via colour-code decoding.

This package is **deliberately dependency-free and decoupled** from the
database, the web layer, and the vision/LLM call. It maps the colours a
player wears (across "channels" such as shirt / head / armband) onto a
unique player identity, robustly against a hidden item (erasure) or a
misread colour.

See ``docs/team_photo_identification_plan.md`` for the full design brief.

Layering (each module depends only on the ones above it):

    galois        -> GF(p) prime-field arithmetic
    code          -> LinearCode (parity / Reed-Solomon) over GF(q)
    channels      -> Channel / ChannelSet (physical label <-> index)
    observations  -> per-channel readings + priors
    scheme        -> IdentityScheme (binds channels + code + assignment)
    decoder       -> soft decoder (readings + prior -> ranked posteriors)
    config        -> the declarative initial config + default_scheme()
"""

from backend.identity.channels import Channel
from backend.identity.channels import ChannelSet
from backend.identity.code import LinearCode
from backend.identity.code import build_code
from backend.identity.code import parity_code
from backend.identity.code import reed_solomon_code
from backend.identity.config import DEFAULT_PALETTE
from backend.identity.config import default_scheme
from backend.identity.decoder import DecodeResult
from backend.identity.decoder import decode
from backend.identity.observations import ChannelObservation
from backend.identity.observations import Prior
from backend.identity.observations import Reading
from backend.identity.scheme import IdentityScheme

__all__ = [
    "Channel",
    "ChannelSet",
    "LinearCode",
    "build_code",
    "parity_code",
    "reed_solomon_code",
    "DEFAULT_PALETTE",
    "default_scheme",
    "DecodeResult",
    "decode",
    "ChannelObservation",
    "Prior",
    "Reading",
    "IdentityScheme",
]
