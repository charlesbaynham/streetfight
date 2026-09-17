"""Synthesise the game's sound effects (numpy -> wave), as the first batch was.

The sounds a player hears are all frontend files in ``react-ui/src/``, imported
like any other asset and played through ``use-sound``. They were originally
hand-rolled tones with no generator kept, which made "make the hit louder" a
guess; this script is that generator, so a sound can be re-tuned by editing the
number that made it rather than by recording something new.

Run it from the repo root::

    python scripts/make_sounds.py            # rewrite every sound
    python scripts/make_sounds.py bang       # just one

The design constraint that matters is **a phone in a coat pocket**. Bass does
not get out of one; the mid-band (roughly 800 Hz - 3 kHz) does, and so does
anything that changes -- a steady tone is masked by pub noise in a way an
alternating two-tone klaxon is not. That is why the alarm here is bright and
modulated rather than the low thud it replaces, and why everything is
normalised to full scale.
"""

import argparse
import math
import os
import wave

import numpy as np

# 22050 mono 16-bit, matching the sounds that were already here. These files
# are shipped uncompressed in the bundle and downloaded over mobile data by a
# player standing in a pub, so the rate is the lowest one that still carries
# everything here: the highest partial in the set is the klaxon's fifth
# harmonic at 5.2 kHz, comfortably under the 11 kHz this leaves.
SAMPLE_RATE = 22050

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, os.pardir, "react-ui", "src")


def _t(seconds: float) -> np.ndarray:
    """A time axis, in seconds, for a clip this long."""
    return np.arange(int(round(seconds * SAMPLE_RATE))) / SAMPLE_RATE


def _sweep(t: np.ndarray, f_start: float, f_end: float) -> np.ndarray:
    """A sine whose frequency glides exponentially from f_start to f_end.

    Exponential rather than linear because pitch is heard logarithmically: a
    linear sweep through the same endpoints spends almost all of its time in
    the top octave and reads as a click with a tail.
    """
    if t.size == 0:
        return t
    duration = t[-1] if t[-1] > 0 else 1.0
    k = math.log(f_end / f_start) / duration
    phase = 2 * math.pi * f_start * (np.exp(k * t) - 1) / k
    return np.sin(phase)


def _decay(t: np.ndarray, tau: float, attack: float = 0.004) -> np.ndarray:
    """An envelope: a short linear attack, then an exponential fall.

    The attack is not cosmetic. A waveform that starts at full amplitude on
    sample zero is a step, and a step is a click on top of whatever follows.
    """
    env = np.exp(-t / tau)
    n_attack = max(1, int(attack * SAMPLE_RATE))
    env[:n_attack] *= np.linspace(0.0, 1.0, n_attack)
    return env


def _noise(n: int, seed: int) -> np.ndarray:
    """Deterministic noise, so re-running this script rewrites byte-identical
    files and a no-op run leaves the working tree clean."""
    return np.random.default_rng(seed).uniform(-1.0, 1.0, n)


def _square_ish(phase: np.ndarray) -> np.ndarray:
    """A tone with odd harmonics: a rounded square, band-limited by hand.

    Two-thirds of the energy sits above the fundamental, which is the point --
    it is what gets through fabric.
    """
    return np.sin(phase) + np.sin(3 * phase) / 3 + np.sin(5 * phase) / 5


def _bell(t: np.ndarray, freq: float, tau: float) -> np.ndarray:
    """A struck-bell partial stack: the upper partials die faster than the
    fundamental, which is what makes it read as struck rather than blown."""
    out = np.zeros_like(t)
    for harmonic, weight in ((1, 1.0), (2, 0.45), (3, 0.22), (4.2, 0.12)):
        out += weight * np.sin(2 * math.pi * freq * harmonic * t) * np.exp(
            -t / (tau / harmonic)
        )
    return out


def _place(canvas: np.ndarray, start: float, clip: np.ndarray) -> None:
    """Mix a clip into a canvas at a start time, truncating at the end."""
    i = int(round(start * SAMPLE_RATE))
    n = min(clip.size, canvas.size - i)
    if n > 0:
        canvas[i : i + n] += clip[:n]


def _normalise(signal: np.ndarray, peak: float = 0.99) -> np.ndarray:
    """Scale to a target peak. Everything here is meant to be heard across a
    pub, so the target is full scale rather than the 0.9 the first batch used.
    """
    loudest = np.abs(signal).max()
    if loudest == 0:
        return signal
    return signal * (peak / loudest)


def _saturate(signal: np.ndarray, drive: float) -> np.ndarray:
    """Soft-clip, to trade peak headroom for loudness.

    Phone speakers are limited by their excursion, not by the sample values, so
    what actually carries across a room is average level and not peak. A tone
    normalised to full scale still has most of its samples near zero; running
    it through a tanh first fills that gap in, which is why a klaxon is driven
    and a bell is not.
    """
    normalised = _normalise(signal, 1.0)
    return np.tanh(drive * normalised) / math.tanh(drive)


def _write(path: str, signal: np.ndarray) -> None:
    samples = np.clip(_normalise(signal), -1.0, 1.0)
    frames = (samples * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(frames)
    print(f"{os.path.basename(path)}: {samples.size / SAMPLE_RATE:.2f}s")


# ---------------------------------------------------------------------------
# The sounds themselves
# ---------------------------------------------------------------------------


def bang() -> np.ndarray:
    """Firing your own weapon: a sci-fi "pew".

    Short, because it plays on every shot and the fire button is pressed a lot
    -- anything with a tail becomes irritating by the third one.
    """
    t = _t(0.26)
    out = np.zeros_like(t)

    # The pew proper: a fast fall through the mid-band, thickened by a
    # detuned second voice a shade behind it.
    body = _t(0.20)
    pew = _sweep(body, 2400, 380) + 0.5 * _sweep(body, 2330, 368)
    _place(out, 0.0, _normalise(pew * _decay(body, 0.055), 1.0))

    # The crack of it leaving the barrel: a few milliseconds of noise, so the
    # onset has an edge instead of fading in.
    crack = _t(0.02)
    _place(out, 0.0, 0.5 * _noise(crack.size, seed=1) * _decay(crack, 0.006, attack=0.001))

    # A little low body underneath, so it has some weight on a phone speaker
    # that cannot reproduce the sweep's bottom end at all.
    thump = _t(0.12)
    _place(out, 0.0, 0.3 * np.sin(2 * math.pi * 110 * thump) * _decay(thump, 0.035))

    return out


def hit_received() -> np.ndarray:
    """You have just been shot: 2.5 seconds of klaxon.

    The sound this replaces was a 130 Hz thump that decayed in under a second
    (RMS 0.14 of full scale). In a pocket, in a pub, on a phone speaker, it was
    inaudible -- and this is the one moment in the game a player cannot afford
    to miss. So: bright, alternating, and long enough that a phone fished out
    mid-alarm is still ringing when it reaches eye level.
    """
    total = 2.5
    t = _t(total)

    # Eight two-tone blasts. The pair is roughly a tritone apart, which is the
    # interval every emergency siren in Europe is built on, for the reason that
    # it refuses to resolve and so refuses to be ignored.
    klaxon = np.zeros_like(t)
    blast_length = 0.27
    for i in range(8):
        start = 0.12 + i * blast_length
        if start + blast_length > total:
            break
        b = _t(blast_length * 0.88)
        freq = 1046.0 if i % 2 else 740.0
        # A slight rise across each blast: a siren that bends is heard as
        # getting closer.
        phase = 2 * math.pi * np.cumsum(freq * (1 + 0.03 * b / b[-1])) / SAMPLE_RATE
        env = np.minimum(1.0, b / 0.01) * np.minimum(1.0, (b[-1] - b) / 0.02)
        _place(klaxon, start, _square_ish(phase) * env)

    out = _saturate(klaxon, 2.2)

    # The impact itself, once, so the alarm has something to be about. Mixed in
    # after the drive and below it: a transient loud enough to dominate would
    # normalise the whole 2.5 seconds back down to a whisper, which is exactly
    # the bug this file is fixing.
    hit = _t(0.18)
    _place(out, 0.0, 0.5 * _noise(hit.size, seed=2) * _decay(hit, 0.03, attack=0.002))
    _place(out, 0.0, 0.6 * np.sin(2 * math.pi * 90 * hit) * _decay(hit, 0.06))

    return out


def knocked_out() -> np.ndarray:
    """You have been knocked out: the sound of your own power going off.

    Deliberately the opposite shape to everything else here -- it falls, it
    slows, and it ends in silence rather than on a note.
    """
    t = _t(1.6)
    out = np.zeros_like(t)

    # The blow that did it.
    thud = _t(0.25)
    _place(out, 0.0, 1.0 * np.sin(2 * math.pi * 70 * thud) * _decay(thud, 0.08))
    _place(out, 0.0, 0.4 * _noise(thud.size, seed=3) * _decay(thud, 0.04, attack=0.002))

    # The wind-down: a long fall with a wobble that slows as it goes, the way
    # a tape machine sounds when the power is cut.
    spin = _t(1.25)
    wobble = 0.06 * np.sin(2 * math.pi * 7 * spin * np.exp(-spin / 1.1))
    glide = _sweep(spin, 900, 62) * (1 + wobble)
    # A second voice an octave down for the grind -- built from odd harmonics
    # rather than a hard square, which at this sample rate would alias into a
    # shimmer that has no business in a power-down.
    grind_phase = 2 * math.pi * np.cumsum(450 * (31 / 450) ** (spin / spin[-1])) / SAMPLE_RATE
    grind = 0.45 * _square_ish(grind_phase)
    _place(out, 0.14, (glide + grind) * _decay(spin, 0.55, attack=0.02))

    return out


def shot_knockout() -> np.ndarray:
    """One of your own shots has just put somebody out of the game.

    It has to be told apart from shot_confirmed.wav -- an ordinary confirmed
    hit, a rising fifth over half a second -- by somebody not looking at their
    phone. So it is the same direction (up: good news) but three notes instead
    of two, twice as long, and it ends on a chord that rings rather than on a
    tone that stops.
    """
    t = _t(1.1)
    out = np.zeros_like(t)

    # C5 - G5 - C6, struck.
    for start, freq in ((0.0, 523.25), (0.11, 783.99), (0.22, 1046.50)):
        note = _t(0.9)
        _place(out, start, 0.55 * _bell(note, freq, 0.42))

    # ...landing on a major triad up top, with a tremolo so it shimmers
    # instead of sitting still.
    chord = _t(0.78)
    tremolo = 1 + 0.25 * np.sin(2 * math.pi * 11 * chord)
    for freq in (1046.50, 1318.51, 1567.98):
        _place(out, 0.32, 0.3 * _bell(chord, freq, 0.34) * tremolo)

    return _saturate(out, 1.6)


SOUNDS = {
    "bang": bang,
    "hit_received": hit_received,
    "knocked_out": knocked_out,
    "shot_knockout": shot_knockout,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "names",
        nargs="*",
        choices=sorted(SOUNDS) + [[]],
        help="which sounds to write (default: all of them)",
    )
    parser.add_argument("--out", default=DEFAULT_OUT, help="directory to write into")
    args = parser.parse_args()

    for name in args.names or sorted(SOUNDS):
        _write(os.path.join(args.out, f"{name}.wav"), SOUNDS[name]())


if __name__ == "__main__":
    main()
