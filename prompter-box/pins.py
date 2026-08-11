"""The Pinboard — named, replayable recipes pinned from proven takes.

Idea #08's mutation (workshop ledger, 2026-07-19): recipes are born from
working results and promoted BOTTOM-UP — a take that earned its keep gets
its settings pinned and named from the Canisters (or a firing from the
Curing Rack), and the pin becomes a selectable formula that prefills a
kiln firing, a Night Shift row, or a Stage cue. The Canisters record what
WAS done; a pin marks what SHOULD be repeated. Same store, two intents.

Persisted beside the call sheet as `pinned-recipes.json` — hand-editable,
diffable, atomically written, bench data the blueprint never tracks.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

PINS_FILE = Path(__file__).resolve().parent / "pinned-recipes.json"

# The rooms a recipe can speak for — the same names the Canisters use,
# plus the kiln (whose proven settings live on the Rack, not the shelves).
PIN_ROOMS = ("stage", "face", "foley", "kiln")

NAME_CAP = 80


class PinboardError(Exception):
    """A refusal with a voice — every message names what to do next."""


def _scalar(v):
    return v is None or isinstance(v, (str, int, float, bool))


def validate_pin(pin, existing):
    if not isinstance(pin, dict):
        raise PinboardError("A pin is a named settings card — send an object, not a bare value.")

    name = str(pin.get("name") or "").strip()
    if not name:
        raise PinboardError("A recipe without a name cannot be asked for again — name the pin.")
    if len(name) > NAME_CAP:
        raise PinboardError(f"'{name[:24]}…' overruns the card — keep the name under {NAME_CAP} characters.")
    if any(p.get("name", "").strip().lower() == name.lower() for p in existing):
        raise PinboardError(
            f"A recipe named '{name}' already hangs on the pinboard — unpin it first, or choose another name.")

    room = pin.get("room")
    if room not in PIN_ROOMS:
        raise PinboardError(f"No room called '{room}' hangs recipes here — one of {list(PIN_ROOMS)}.")

    recipe = pin.get("recipe")
    if not isinstance(recipe, dict):
        raise PinboardError("A pin carries its settings as an object — the recipe field is the card's whole point.")
    kept = {}
    for key, value in recipe.items():
        if value is None or value == "" or value == []:
            continue  # empty knobs are not part of the formula
        if not (_scalar(value) or (isinstance(value, list) and all(_scalar(v) for v in value))):
            raise PinboardError(f"The recipe's '{key}' is not a setting the board can hold — scalars and lists only.")
        kept[key] = value
    if not kept:
        raise PinboardError("Every knob on that recipe is empty — there is nothing to repeat. Pin a take with settings.")

    return {
        "id": f"pin-{uuid4().hex[:8]}",
        "name": name,
        "room": room,
        "source": str(pin.get("source") or "") or None,
        "recipe": kept,
        "pinned_at": datetime.now().isoformat(timespec="seconds"),
    }


def load_pins(path=None):
    path = Path(path or PINS_FILE)
    try:
        pins = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return pins if isinstance(pins, list) else []


def save_pins(pins, path=None):
    """Atomic write — a mid-save booth death never leaves half a pinboard."""
    path = Path(path or PINS_FILE)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pins, indent=1))
    os.replace(tmp, path)


def pin_recipe(pin, path=None):
    pins = load_pins(path)
    normalized = validate_pin(pin, pins)
    pins.append(normalized)
    save_pins(pins, path)
    return normalized


def unpin_recipe(pin_id, path=None):
    pins = load_pins(path)
    kept = [p for p in pins if p.get("id") != pin_id]
    if len(kept) == len(pins):
        raise PinboardError(f"No pin '{pin_id}' hangs on the board — it may already be unpinned.")
    save_pins(kept, path)
