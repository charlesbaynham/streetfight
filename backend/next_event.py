"""The one thing the game says is coming next, and when.

A game carries at most one cue at a time: ``Game.next_event_kind`` /
``next_event_at`` / ``next_event_note``, set by an admin and cleared when the
cue fires or is cancelled. This module holds the vocabulary those columns are
written in, kept out of ``model.py`` so that nothing which only reads a cue has
to import the ORM.

The kinds are the two things that can be counted down to on the night:

``circle``
    The next circle becomes the exclusion circle when the clock runs out
    (M3.2), so everyone outside it has until then to get in.

``drop``
    A courier sets off with a crate when the clock runs out (M3.3), and the
    note is what is in it.

The strings are what reaches the players' phones on ``UserModel``, so they are
part of the wire format: a phone with an older bundle open will show a cue it
does not recognise as nothing at all rather than as a wrong one.
"""

KIND_CIRCLE = "circle"
KIND_DROP = "drop"

EVENT_KINDS = (KIND_CIRCLE, KIND_DROP)
