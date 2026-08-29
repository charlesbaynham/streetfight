"""Deterministic ids, derived from the master seed rather than minted.

``backend.model`` defaults every primary key to ``uuid4``, which is right for
a real game and wrong for a fixture: today's ``MAKE_DEBUG_ENTRIES`` mints its
team ids at *import* time, so a printed join QR stops working when the server
restarts, not merely when the database is reset. Deriving the ids from the
seed instead makes them stable for as long as the seed is, which is what a
printed card needs.

UUID5 rather than a seeded RNG: it is order-independent, so adding a seventh
team does not renumber the first six, and it needs no shared generator
threaded through the call stack.
"""

import uuid

# A fixed namespace of our own, so these ids cannot collide with anything
# generated elsewhere. Itself a uuid5 of the project name under the DNS
# namespace, so it is reproducible rather than magic.
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "test-world.streetfight.invalid")


def derive(seed: int, *parts: str) -> uuid.UUID:
    """A stable UUID for ``parts`` within the world built from ``seed``."""
    return uuid.uuid5(NAMESPACE, ":".join((str(seed),) + parts))


def game_id(seed: int) -> uuid.UUID:
    return derive(seed, "game")


def team_id(seed: int, team_slug: str) -> uuid.UUID:
    return derive(seed, "team", team_slug)


def user_id(seed: int, player_slug: str) -> uuid.UUID:
    return derive(seed, "user", player_slug)
