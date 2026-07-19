"""The Night Shift's containment suite — call-sheet grammar, unattended
completion, the takes_done resume cursor, row-level failure isolation, and
the non-negotiable containment wait at the door."""

import json
import threading
import time

import pytest

import kiln
import night_shift
from night_shift import (
    CallSheetError,
    add_row,
    load_queue,
    remove_row,
    reorder_row,
    save_queue,
    validate_row,
)


@pytest.fixture
def sheet(tmp_path, monkeypatch):
    """A sandboxed call sheet + a sandboxed Rack for parked candidates."""
    queue_path = tmp_path / "night-shift-queue.json"
    monkeypatch.setattr(night_shift, "QUEUE_FILE", queue_path)
    out = tmp_path / "kiln-output"
    monkeypatch.setattr(kiln, "KILN_OUT", out)
    return queue_path


def park_candidate(subject, seed, shredded=False):
    """What a real take leaves behind: a candidate dir with its recipe."""
    cid = f"kiln-test-{seed}-{abs(hash(subject)) % 10_000}"
    cdir = kiln.candidate_dir(cid)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "recipe.json").write_text(json.dumps({
        "id": cid, "subject": subject, "seed": seed, "status": "pending",
        "shredding_detected": shredded, "refire_count": 1 if shredded else 0,
        "fired_at": f"take-{seed}", "files": {"glb": "x.glb", "hide": "x.png"},
    }))
    return cid


def run_shift_to_end(fire_take, stations_clear=lambda: True, timeout=10.0):
    ok, msg = night_shift.start_shift(fire_take, stations_clear,
                                      log=lambda _m: None, poll_s=0.05)
    assert ok, msg
    thread = night_shift._shift["thread"]
    thread.join(timeout)
    assert not thread.is_alive(), "the shift never clocked out"


class TestCallSheetSchema:
    def test_should_accept_a_kiln_row_and_fill_the_prop_dressing_defaults(self):
        row = validate_row({"subject": "a black omafiets", "variant_count": 2})
        assert row["job_type"] == "kiln"
        assert row["octree"] == 128 and row["threshold"] == 0.5
        assert row["status"] == "queued" and row["takes_done"] == 0

    def test_should_reject_any_other_job_type_with_a_named_error(self):
        """Criterion 25 — the workshop-wide shape is real; only 'kiln' is legal."""
        with pytest.raises(CallSheetError, match="'stage' job"):
            validate_row({"subject": "a take", "job_type": "stage"})
        with pytest.raises(CallSheetError, match="'foley' job"):
            validate_row({"subject": "a sting", "job_type": "foley"})

    def test_should_accept_the_seed_varied_grammar(self):
        """Criterion 24, site 1 — one phrase, K seed-varied takes."""
        row = validate_row({"subject": "a black omafiets", "variant_count": 3})
        assert row["subject"] == "a black omafiets" and row["variant_count"] == 3

    def test_should_accept_the_phrase_list_grammar(self):
        """Criterion 24, site 2 — K phrases, K distinct fires."""
        row = validate_row({"subject": ["a gnome", "a windmill"], "variant_count": 2})
        assert row["subject"] == ["a gnome", "a windmill"]

    def test_should_demand_that_the_two_grammars_agree(self):
        with pytest.raises(CallSheetError, match="must agree"):
            validate_row({"subject": ["a gnome", "a windmill"], "variant_count": 3})

    def test_should_refuse_an_empty_subject(self):
        with pytest.raises(CallSheetError, match="empty phrase|needs a subject"):
            validate_row({"subject": "   "})


class TestCallSheetPersistence:
    def test_should_survive_the_add_remove_reorder_round_trip(self, sheet):
        a = add_row({"subject": "the gnome"}, sheet)
        b = add_row({"subject": "the windmill"}, sheet)
        assert [r["subject"] for r in load_queue(sheet)] == ["the gnome", "the windmill"]
        reorder_row(b["id"], "up", sheet)
        assert [r["subject"] for r in load_queue(sheet)] == ["the windmill", "the gnome"]
        remove_row(a["id"], sheet)
        assert [r["id"] for r in load_queue(sheet)] == [b["id"]]

    def test_should_name_a_missing_order_when_removing(self, sheet):
        with pytest.raises(CallSheetError, match="row-ghost"):
            remove_row("row-ghost", sheet)


class TestTheShift:
    def test_should_work_five_rows_unattended_into_seven_candidates(self, sheet):
        """Criterion 19 — 5 rows, one K=3, no Scientist after Start:
        5 + 2 = 7 candidates on the Rack, each with its own recipe."""
        for subject in ("the gnome", "the windmill", "the planter", "the bench"):
            add_row({"subject": subject}, sheet)
        add_row({"subject": "a black omafiets", "variant_count": 3, "seed": 100}, sheet)
        fired = []

        def take(row, i, subject, seed):
            fired.append((subject, seed))
            park_candidate(subject, seed)

        run_shift_to_end(take)
        assert len(fired) == 7
        rack = kiln.rack_list()
        assert len(rack) == 7
        assert len({e["id"] for e in rack}) == 7              # each independently visible
        assert len({e["recipe"]["subject"] for e in rack}) == 5  # each with its own recipe
        assert all(r["status"] == "done" for r in load_queue(sheet))
        # the K=3 row fired three seed-varied takes of the one subject
        omafiets_seeds = [s for subj, s in fired if subj == "a black omafiets"]
        assert omafiets_seeds == [100, 101, 102]

    def test_should_not_let_a_shredded_seed_sink_its_row_or_the_queue(self, sheet):
        """Criterion 20 — the row-level failure-isolation contract: a shred
        parks flagged; the other takes still complete."""
        add_row({"subject": "a black omafiets", "variant_count": 3, "seed": 7}, sheet)
        add_row({"subject": "the gnome"}, sheet)

        def take(row, i, subject, seed):
            park_candidate(subject, seed, shredded=(i == 1))  # the middle seed tatters

        run_shift_to_end(take)
        rows = load_queue(sheet)
        assert [r["status"] for r in rows] == ["done", "done"]
        rack = kiln.rack_list()
        assert len(rack) == 4
        flagged = [e for e in rack if e["recipe"]["shredding_detected"]]
        assert len(flagged) == 1  # parked flagged, per the refire ceiling

    def test_should_fail_a_row_voiced_only_when_the_kiln_goes_cold(self, sheet):
        add_row({"subject": "the gnome"}, sheet)
        add_row({"subject": "the windmill"}, sheet)

        calls = []

        def take(row, i, subject, seed):
            calls.append(subject)
            if subject == "the windmill":
                raise kiln.KilnColdError(
                    "The kiln went cold mid-firing — ComfyUI stopped answering on :8188.")
            park_candidate(subject, seed)

        run_shift_to_end(take)
        rows = {r["subject"]: r for r in load_queue(sheet)}
        assert rows["the gnome"]["status"] == "done"
        assert rows["the windmill"]["status"] == "failed"
        assert "went cold" in rows["the windmill"]["reason"]

    def test_should_resume_a_firing_row_from_its_first_unfinished_take(self, sheet):
        """Criterion 21, two sites — resume-from-row and no-duplicate-takes:
        a booth restart with takes_done: 2 of K=3 on disk fires exactly the
        third take, never K + duplicates."""
        save_queue([validate_row({
            "subject": "a black omafiets", "variant_count": 3, "seed": 100,
            "status": "firing", "takes_done": 2,
        })], sheet)
        fired = []

        def take(row, i, subject, seed):
            fired.append((i, seed))
            park_candidate(subject, seed)

        run_shift_to_end(take)
        assert fired == [(2, 102)]                       # site 1: the third take only
        assert len(kiln.rack_list()) == 1                # site 2: 2 already parked + 1, no dupes
        assert load_queue(sheet)[0]["status"] == "done"
        assert load_queue(sheet)[0]["takes_done"] == 3

    def test_should_pick_up_a_row_added_mid_shift_without_a_restart(self, sheet):
        """Criterion 22 — a panel add lands on the next row boundary."""
        add_row({"subject": "the gnome"}, sheet)
        first_take_running = threading.Event()
        release = threading.Event()
        fired = []

        def take(row, i, subject, seed):
            fired.append(subject)
            if len(fired) == 1:
                first_take_running.set()
                release.wait(5)
            park_candidate(subject, seed)

        ok, _ = night_shift.start_shift(take, lambda: True, log=lambda _m: None, poll_s=0.05)
        assert ok
        assert first_take_running.wait(5)
        add_row({"subject": "the windmill"}, sheet)      # briefed mid-shift
        release.set()
        night_shift._shift["thread"].join(10)
        assert fired == ["the gnome", "the windmill"]
        assert all(r["status"] == "done" for r in load_queue(sheet))

    def test_should_hold_a_row_queued_while_another_station_holds_the_gpu(self, sheet):
        """Criterion 23 — containment, non-negotiable: the row stays queued
        (not firing) until the Stage's guard releases; same guard, no second
        lock."""
        add_row({"subject": "the gnome"}, sheet)
        stage_released = threading.Event()
        fired = []

        def take(row, i, subject, seed):
            fired.append(subject)
            park_candidate(subject, seed)

        ok, _ = night_shift.start_shift(take, stage_released.is_set,
                                        log=lambda _m: None, poll_s=0.05)
        assert ok
        time.sleep(0.4)  # the shift is at the door, waiting
        assert fired == []
        assert load_queue(sheet)[0]["status"] == "queued"  # queued, NOT firing
        stage_released.set()                               # the Stage job ends
        night_shift._shift["thread"].join(10)
        assert fired == ["the gnome"]
        assert load_queue(sheet)[0]["status"] == "done"

    def test_should_refuse_a_second_crew_on_the_floor(self, sheet):
        add_row({"subject": "the gnome"}, sheet)
        gate = threading.Event()

        def take(row, i, subject, seed):
            gate.wait(5)
            park_candidate(subject, seed)

        ok, _ = night_shift.start_shift(take, lambda: True, log=lambda _m: None, poll_s=0.05)
        assert ok
        ok2, msg = night_shift.start_shift(take, lambda: True)
        assert not ok2 and "already on the floor" in msg
        gate.set()
        night_shift._shift["thread"].join(10)

    def test_should_refuse_a_bad_row_at_the_door_without_sinking_the_sheet(self, sheet):
        add_row({"subject": "the gnome"}, sheet)
        rows = load_queue(sheet)
        rows.insert(0, {"id": "row-bad", "subject": "a ghost order",
                        "job_type": "seance", "status": "queued", "takes_done": 0})
        save_queue(rows, sheet)
        fired = []

        def take(row, i, subject, seed):
            fired.append(subject)
            park_candidate(subject, seed)

        run_shift_to_end(take)
        by_id = {r["id"]: r for r in load_queue(sheet)}
        assert by_id["row-bad"]["status"] == "failed"
        assert "seance" in by_id["row-bad"]["reason"]
        assert fired == ["the gnome"]  # the sheet kept working


class TestBootResume:
    def test_should_know_when_a_shift_died_mid_row(self, sheet):
        assert not night_shift.has_firing_row(sheet)
        save_queue([validate_row({"subject": "x", "status": "firing"})], sheet)
        assert night_shift.has_firing_row(sheet)
