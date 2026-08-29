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
"""
