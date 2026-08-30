"""A deterministic thirty-player test world.

Real games have found bugs that unit tests did not, because unit tests
provision one or two players at a time and the bugs needed a crowd. This
package generates the crowd: six teams of five moving around Westminster for
an hour, with telemetry that behaves like real phones do.

The whole world is a pure function of one master seed. Same seed, identical
``world.json``; a new seed, a wholly different but equally reproducible game.
Nothing here calls the network -- image generation is a separate, later phase
that reads the world file rather than participating in building it.

Two rules shape everything below:

* **The truth track never reaches the database.** Where a player actually is,
  second by second, is used to find encounters and to compose photographs. The
  database only ever sees ``fixes`` -- timestamped, error-laden readings from a
  simulated phone, delivered exactly as the browser would deliver them. The gap
  between the two is the point of the exercise.
* **Identity is by slug, never by UUID.** ``world.json`` names players
  ``pimlico-1`` and shots ``S1`` so that it is byte-stable; the database ids
  are derived from the seed at materialisation time (see ``ids.py``) rather
  than minted randomly, which is also what stops a printed join QR from dying
  on the next server restart.

``data/`` holds the world and everything derived from it, and it lives inside
this package rather than under ``tests/`` because the replay is not only a
test tool: the admin's **Fire demo game** button runs it on a server, whose
working directory is the state directory and which has no checkout anywhere
near it. Two of its files are therefore declared as package data in
``pyproject.toml`` and travel into every deployment -- ``world.json`` and the
ten cropped photographs in ``data/shots/``. The rest (the 25MB image store in
``data/images/``, and the backdrop and swatch card the generator composes
from) stays behind in the repository, because only the generation tooling,
which is only ever run from a checkout, reads it. Anything a *replay* comes to
need has to be added to that manifest too, or it will be missing exactly where
nobody is watching.
"""
