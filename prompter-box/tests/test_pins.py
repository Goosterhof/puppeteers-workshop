"""The Pinboard's containment suite (#08) — the pin grammar, the bottom-up
promotion contract, duplicate-name refusals, and atomic persistence. The
booth windows that hang and take down pins over HTTP are specced in
test_server.py, beside the rest of the service hatch."""

import json

import pytest

import pins
from pins import PinboardError, load_pins, pin_recipe, unpin_recipe, validate_pin


@pytest.fixture
def board(tmp_path, monkeypatch):
    """A sandboxed pinboard — no bench file is ever touched."""
    path = tmp_path / "pinned-recipes.json"
    monkeypatch.setattr(pins, "PINS_FILE", path)
    return path


def spoked_vehicle(**overrides):
    pin = {"name": "Spoked Vehicle", "room": "kiln", "source": "kiln-test-0001",
           "recipe": {"octree": 224, "threshold": 0.4, "seed": 7, "two_sided": False}}
    pin.update(overrides)
    return pin


class TestThePinGrammar:
    """validate_pin is the whole door — what hangs on the board got past it."""

    def test_should_normalize_a_proven_firing_into_a_named_card(self):
        pin = validate_pin(spoked_vehicle(), existing=[])
        assert pin["name"] == "Spoked Vehicle"
        assert pin["room"] == "kiln"
        assert pin["recipe"] == {"octree": 224, "threshold": 0.4, "seed": 7, "two_sided": False}
        assert pin["source"] == "kiln-test-0001"
        assert pin["id"].startswith("pin-")
        assert pin["pinned_at"]

    def test_should_refuse_a_nameless_pin_with_a_voiced_error(self):
        with pytest.raises(PinboardError, match="name the pin"):
            validate_pin(spoked_vehicle(name="  "), existing=[])

    def test_should_refuse_a_name_that_overruns_the_card(self):
        with pytest.raises(PinboardError, match="under 80 characters"):
            validate_pin(spoked_vehicle(name="x" * 81), existing=[])

    def test_should_refuse_a_duplicate_name_case_insensitively(self):
        first = validate_pin(spoked_vehicle(), existing=[])
        with pytest.raises(PinboardError, match="already hangs on the pinboard"):
            validate_pin(spoked_vehicle(name="spoked vehicle"), existing=[first])

    def test_should_refuse_a_room_that_hangs_no_recipes(self):
        with pytest.raises(PinboardError, match="No room called 'attic'"):
            validate_pin(spoked_vehicle(room="attic"), existing=[])

    def test_should_refuse_a_recipe_that_is_not_an_object(self):
        with pytest.raises(PinboardError, match="recipe field"):
            validate_pin(spoked_vehicle(recipe="octree 224"), existing=[])

    def test_should_drop_empty_knobs_but_refuse_an_all_empty_recipe(self):
        pin = validate_pin(spoked_vehicle(recipe={"octree": 224, "seed": None, "loras": []}), existing=[])
        assert pin["recipe"] == {"octree": 224}
        with pytest.raises(PinboardError, match="nothing to repeat"):
            validate_pin(spoked_vehicle(recipe={"seed": None, "prompt": ""}), existing=[])

    def test_should_refuse_a_setting_the_board_cannot_hold(self):
        with pytest.raises(PinboardError, match="'graph'"):
            validate_pin(spoked_vehicle(recipe={"graph": {"nested": "object"}}), existing=[])

    def test_should_keep_a_lora_wardrobe_as_a_list_of_names(self):
        pin = validate_pin(spoked_vehicle(room="stage",
                                          recipe={"steps": 4, "loras": ["FastWan", "OmniNFT"]}),
                           existing=[])
        assert pin["recipe"]["loras"] == ["FastWan", "OmniNFT"]


class TestThePinboardShelf:
    """load / pin / unpin against the persisted board."""

    def test_should_start_bare_when_no_board_has_been_hung(self, board):
        assert load_pins() == []

    def test_should_pin_and_read_back_the_same_card(self, board):
        pinned = pin_recipe(spoked_vehicle())
        assert [p["id"] for p in load_pins()] == [pinned["id"]]
        assert json.loads(board.read_text())[0]["name"] == "Spoked Vehicle"

    def test_should_unpin_by_id_and_refuse_a_ghost(self, board):
        pinned = pin_recipe(spoked_vehicle())
        unpin_recipe(pinned["id"])
        assert load_pins() == []
        with pytest.raises(PinboardError, match="already be unpinned"):
            unpin_recipe(pinned["id"])

    def test_should_survive_a_corrupt_board_by_starting_bare(self, board):
        board.write_text("{not json")
        assert load_pins() == []
