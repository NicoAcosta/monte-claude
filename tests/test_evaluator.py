from poker.deck import Card
from poker.evaluator import best_hand, evaluate_five, HAND_RANKS


def cards(s: str) -> list[Card]:
    """Parse space-separated card strings: 'Ah Kd Qs Jh Tc'"""
    return [Card.from_str(c) for c in s.split()]


def test_royal_flush():
    h = best_hand(cards("Ah Kh Qh Jh Th"))
    assert h.name == "royal_flush"
    assert h.rank == HAND_RANKS["royal_flush"]


def test_straight_flush():
    h = best_hand(cards("9s 8s 7s 6s 5s"))
    assert h.name == "straight_flush"


def test_four_of_a_kind():
    h = best_hand(cards("Ah Ad As Ac Kd"))
    assert h.name == "four_of_a_kind"


def test_full_house():
    h = best_hand(cards("Ah Ad As Kh Kd"))
    assert h.name == "full_house"


def test_flush():
    h = best_hand(cards("Ah Kh Qh Jh 9h"))
    assert h.name == "flush"


def test_straight():
    h = best_hand(cards("Ah Kd Qs Jh Tc"))
    assert h.name == "straight"


def test_ace_low_straight():
    h = best_hand(cards("Ah 2d 3s 4h 5c"))
    assert h.name == "straight"
    assert h.kickers == (3,)  # 5-high


def test_three_of_a_kind():
    h = best_hand(cards("Ah Ad As Kh Qd"))
    assert h.name == "three_of_a_kind"


def test_two_pair():
    h = best_hand(cards("Ah Ad Kh Kd Qs"))
    assert h.name == "two_pair"


def test_one_pair():
    h = best_hand(cards("Ah Ad Kh Qd Js"))
    assert h.name == "one_pair"


def test_high_card():
    h = best_hand(cards("Ah Kd Qs Jh 9c"))
    assert h.name == "high_card"


def test_comparison_different_ranks():
    flush = best_hand(cards("Ah Kh Qh Jh 9h"))
    pair = best_hand(cards("Ah Ad Kh Qd Js"))
    assert flush > pair
    assert pair < flush


def test_comparison_same_rank_different_kickers():
    high_pair = best_hand(cards("Ah Ad Kh Qd Js"))
    low_pair = best_hand(cards("2h 2d Kh Qd Js"))
    assert high_pair > low_pair


def test_comparison_equal():
    h1 = best_hand(cards("Ah Kd Qs Jh Tc"))
    h2 = best_hand(cards("Ac Ks Qd Jc Ts"))
    assert h1 == h2


def test_best_of_seven():
    # 7 cards, should find the royal flush
    h = best_hand(cards("Ah Kh Qh Jh Th 2d 3c"))
    assert h.name == "royal_flush"


def test_best_of_seven_picks_best():
    # Hole: Ah Kh, Board: Qh Jh Th 2d 3c -> royal flush
    h = best_hand(cards("Ah Kh Qh Jh Th 2d 3c"))
    assert h.name == "royal_flush"


def test_two_pair_kicker():
    h1 = best_hand(cards("Ah Ad Kh Kd Qs"))
    h2 = best_hand(cards("Ah Ad Kh Kd Js"))
    assert h1 > h2


def test_full_house_comparison():
    h1 = best_hand(cards("Ah Ad As Kh Kd"))
    h2 = best_hand(cards("Kh Kd Ks Ah Ad"))
    assert h1 > h2  # Aces full > Kings full


def test_straight_flush_beats_four_of_a_kind():
    sf = best_hand(cards("9s 8s 7s 6s 5s"))
    quads = best_hand(cards("Ah Ad As Ac Kd"))
    assert sf > quads


def test_ace_low_straight_loses_to_regular():
    low = best_hand(cards("Ah 2d 3s 4h 5c"))
    high = best_hand(cards("2h 3d 4s 5h 6c"))
    assert high > low
