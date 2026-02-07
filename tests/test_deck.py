from poker.deck import Card, Deck, full_deck

import pytest


def test_full_deck_has_52_cards():
    assert len(full_deck()) == 52


def test_full_deck_all_unique():
    cards = full_deck()
    assert len(set(cards)) == 52


def test_card_from_str():
    c = Card.from_str("Ah")
    assert c.rank == "A"
    assert c.suit == "h"
    assert c.rank_value == 12
    assert str(c) == "Ah"
    assert c.display() == "A♥"


def test_card_invalid_rank():
    with pytest.raises(ValueError):
        Card(rank="X", suit="s")


def test_card_invalid_suit():
    with pytest.raises(ValueError):
        Card(rank="A", suit="x")


def test_card_from_str_bad_length():
    with pytest.raises(ValueError):
        Card.from_str("Ace")


def test_deck_deal():
    deck = Deck(seed=42)
    cards = deck.deal(2)
    assert len(cards) == 2
    assert deck.remaining == 50


def test_deck_deterministic_with_seed():
    d1 = Deck(seed=1)
    d2 = Deck(seed=1)
    assert d1.deal(5) == d2.deal(5)


def test_deck_exhaustion():
    deck = Deck(seed=0)
    deck.deal(52)
    with pytest.raises(RuntimeError):
        deck.deal(1)


def test_card_frozen():
    c = Card.from_str("Ks")
    with pytest.raises(AttributeError):
        c.rank = "Q"  # type: ignore[misc]
