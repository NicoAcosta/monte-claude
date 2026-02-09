"""Bot name pool — pick a random first name, format as {name}_bot."""

from __future__ import annotations

import random

NAMES: tuple[str, ...] = (
    "james", "mary", "robert", "patricia", "john",
    "jennifer", "michael", "linda", "david", "elizabeth",
    "william", "barbara", "richard", "susan", "joseph",
    "jessica", "thomas", "sarah", "charles", "karen",
    "christopher", "lisa", "daniel", "nancy", "matthew",
    "betty", "anthony", "margaret", "mark", "sandra",
    "donald", "ashley", "steven", "dorothy", "paul",
    "kimberly", "andrew", "emily", "joshua", "donna",
    "kenneth", "michelle", "kevin", "carol", "brian",
    "amanda", "george", "melissa", "timothy", "deborah",
    "ronald", "stephanie", "edward", "rebecca", "jason",
    "sharon", "jeffrey", "laura", "ryan", "cynthia",
    "jacob", "kathleen", "gary", "amy", "nicholas",
    "angela", "eric", "shirley", "jonathan", "anna",
    "stephen", "brenda", "larry", "pamela", "justin",
    "emma", "scott", "nicole", "brandon", "helen",
    "benjamin", "samantha", "samuel", "katherine", "raymond",
    "christine", "gregory", "debra", "frank", "rachel",
    "alexander", "carolyn", "patrick", "janet", "jack",
    "catherine", "dennis", "maria", "jerry", "heather",
)

_used: set[str] = set()


def pick_name() -> str:
    """Pick a unique bot name like 'david_bot'.

    Draws from the name pool without replacement. Once all 100 base names
    are taken, appends a random number suffix (e.g. 'david_bot427').
    """
    available = [n for n in NAMES if n not in _used]

    if available:
        name = random.choice(available)
        _used.add(name)
        return f"{name}_bot"

    # All base names used — pick any name + random number
    name = random.choice(NAMES)
    suffix = random.randint(100, 999)
    return f"{name}_bot{suffix}"
