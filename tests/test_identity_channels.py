"""Tests for channels: label<->index round-trips, alphabet validation, and
heterogeneous alphabets (a shape channel alongside colour channels)."""

import pytest

from backend.identity.channels import Channel
from backend.identity.channels import ChannelSet

PALETTE = ["red", "yellow", "green", "blue", "purple"]
SHAPES = ["circle", "square", "triangle", "star", "cross"]


def test_label_index_roundtrip():
    channel = Channel("shirt", PALETTE)
    for i, label in enumerate(PALETTE):
        assert channel.label_to_index(label) == i
        assert channel.index_to_label(i) == label


def test_channel_rejects_unknown_label():
    channel = Channel("shirt", PALETTE)
    with pytest.raises(ValueError):
        channel.label_to_index("octarine")


def test_channel_rejects_duplicate_labels():
    with pytest.raises(ValueError):
        Channel("shirt", ["red", "red", "green"])


def test_channelset_rejects_channel_with_too_few_labels():
    short = Channel("armband", ["red", "yellow"])
    with pytest.raises(ValueError):
        ChannelSet([Channel("shirt", PALETTE), short], q=5)


def test_channelset_rejects_duplicate_names():
    with pytest.raises(ValueError):
        ChannelSet([Channel("shirt", PALETTE), Channel("shirt", PALETTE)], q=5)


def test_heterogeneous_alphabets():
    # A colour channel and a shape channel of the same cardinality coexist.
    cs = ChannelSet([Channel("shirt", PALETTE), Channel("shape", SHAPES)], q=5)
    appearance = cs.codeword_to_appearance((0, 2))
    assert appearance == {"shirt": "red", "shape": "triangle"}
    assert cs.appearance_to_codeword(appearance) == (0, 2)


def test_codeword_appearance_roundtrip():
    cs = ChannelSet(
        [Channel(name, PALETTE) for name in ["shirt", "head", "armband"]], q=5
    )
    codeword = (3, 1, 4)
    appearance = cs.codeword_to_appearance(codeword)
    assert appearance == {"shirt": "blue", "head": "yellow", "armband": "purple"}
    assert cs.appearance_to_codeword(appearance) == codeword


def test_channel_may_carry_extra_labels():
    # 6 labels with q=5 is fine; only the first q are addressed by codewords.
    cs = ChannelSet([Channel("shirt", PALETTE + ["orange"])], q=5)
    assert cs.n == 1
    assert cs[0].size == 6
