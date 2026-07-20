"""The Kiln's containment suite — the image laws against their own named
fixtures, the firing chain against mocked paint/mesh stages (no live GPU),
and the Curing Rack's division-of-labour contracts."""

import inspect
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import kiln
from conftest import paint_fixture

CLEAR = lambda need: (True, 99.0)  # noqa: E731 — a stage that is always struck


class TestDespillPurpleGate:
    """Criterion 3 — the gate pixel plus the memory file's four named exemptions."""

    def _one(self, rgb):
        return kiln.despill_purple_gate(np.array([[rgb]], dtype=np.uint8))[0, 0]

    def test_should_neutralize_a_lavender_key_survivor_to_g_times_105(self):
        assert tuple(self._one((120, 60, 120))) == (63, 60, 63)

    def test_should_spare_terracotta_because_b_is_below_g(self):
        assert tuple(self._one((180, 90, 60))) == (180, 90, 60)

    def test_should_spare_wicker_because_b_is_low(self):
        assert tuple(self._one((170, 140, 90))) == (170, 140, 90)

    def test_should_spare_red_blooms_because_b_is_low_at_that_brightness(self):
        assert tuple(self._one((200, 60, 70))) == (200, 60, 70)

    def test_should_spare_a_blue_coat_because_r_fails_the_gate(self):
        assert tuple(self._one((60, 80, 160))) == (60, 80, 160)


class TestCropToAlphaBbox:
    """Criterion 4 — the exact +6 px padding value, not 'roughly cropped'."""

    def test_should_pad_the_subject_bbox_by_exactly_six_px_on_all_four_edges(self):
        rgba = np.zeros((120, 100, 4), dtype=np.uint8)
        rgba[30:60, 40:70, 3] = 255  # subject: 30 rows x 30 cols
        out = kiln.crop_to_alpha_bbox(rgba, pad=6)
        assert out.shape[:2] == (30 + 12, 30 + 12)
        ys, xs = np.nonzero(out[..., 3])
        assert (ys.min(), ys.max(), xs.min(), xs.max()) == (6, 35, 6, 35)

    def test_should_refuse_a_hide_with_no_subject_at_all(self):
        with pytest.raises(kiln.KilnRefusal, match="entirely transparent"):
            kiln.crop_to_alpha_bbox(np.zeros((10, 10, 4), dtype=np.uint8))


class TestKeyPropImage:
    def test_should_key_the_ground_to_exactly_zero_border_alpha(self, tmp_path):
        painting = paint_fixture(tmp_path / "prop.png")
        rgba = kiln.key_prop_image(painting)
        assert rgba[0].sum(axis=0)[3] == 0 and rgba[-1].sum(axis=0)[3] == 0
        assert rgba[:, 0].sum(axis=0)[3] == 0 and rgba[:, -1].sum(axis=0)[3] == 0
        assert rgba[100, 100, 3] == 255  # the subject survives whole

    def test_should_shed_the_klein_edge_vignette_before_sampling_the_ring(self, tmp_path):
        """The first live firing's refusal, as a fixture: Klein grounds wear a
        ~14 px darker edge vignette whose corners sit ~55 distance units off
        the ring median — the crop-first law (Menagerie, 2026-07-10) must key
        it clean without widening the tolerance."""
        painting = paint_fixture(tmp_path / "vignetted.png")
        img = np.asarray(Image.open(painting)).copy()
        h, w, _ = img.shape
        yy, xx = np.mgrid[0:h, 0:w]
        edge = np.minimum(np.minimum(yy, h - 1 - yy), np.minimum(xx, w - 1 - xx))
        shade = np.clip((14 - edge) / 14, 0, 1) * 0.25       # up to 25% darker rim
        img = (img * (1 - shade[..., None])).astype(np.uint8)
        Image.fromarray(img, "RGB").save(painting)
        rgba = kiln.key_prop_image(painting)                  # must NOT refuse
        assert rgba[0].sum(axis=0)[3] == 0 and rgba[-1].sum(axis=0)[3] == 0
        assert rgba[:, 0].sum(axis=0)[3] == 0 and rgba[:, -1].sum(axis=0)[3] == 0
        assert rgba[86, 86, 3] == 255  # the subject (shifted by the crop) survives

    def test_should_fail_closed_when_the_subject_reaches_the_border(self, tmp_path):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[...] = (255, 0, 255)
        img[0:100, 40:60] = (30, 30, 30)  # subject bleeds off both edges
        path = tmp_path / "bleed.png"
        Image.fromarray(img, "RGB").save(path)
        with pytest.raises(kiln.KilnRefusal, match="border alpha"):
            kiln.key_prop_image(path)


class TestOrientHint:
    def test_should_stand_thin_axis_subjects_and_lay_long_the_rest(self):
        assert kiln.orient_hint("a black omafiets leaning at a slight angle") == "standThin"
        assert kiln.orient_hint("a garden gnome with a red hat") == "layLong"
        for phrase in ("a wooden fence", "a rusty trike", "terracotta geraniums"):
            assert kiln.orient_hint(phrase) in {"standThin", "layLong"}


def fake_paint(tmp_path):
    def paint(subject, seed, prefix, back_of=None):
        return paint_fixture(tmp_path / f"paint-{prefix.replace('/', '-')}-{bool(back_of)}.png")
    return paint


def fake_mesh(mapping, calls):
    """A fire_mesh stand-in: routes octree -> fixture GLB, records the call."""
    def fire(hide_path, octree=128, threshold=0.5, seed=7, prefix="x"):
        calls.append({"octree": octree, "threshold": threshold,
                      "hide": Path(hide_path).read_bytes()})
        return mapping[octree]
    return fire


@pytest.fixture
def fired_solid(tmp_path, monkeypatch, kiln_sandbox, software_render, solid_glb):
    """One completed solid firing on the Rack, mocked paint/mesh, real chain."""
    calls = []
    monkeypatch.setattr(kiln, "paint_subject", fake_paint(tmp_path))
    monkeypatch.setattr(kiln, "fire_mesh", fake_mesh({128: solid_glb, 224: solid_glb}, calls))
    result = kiln.kiln_fire("a garden gnome with a red hat", seed=7, clear_set=CLEAR)
    return {"result": result, "calls": calls, "sandbox": kiln_sandbox}


class TestKilnFire:
    def test_should_return_the_full_output_contract_from_a_fixture_firing(self, fired_solid):
        """Criterion 1 — kiln_fire's output contract, fixture-driven."""
        r = fired_solid["result"]
        assert r.glb_path and Path(r.glb_path).exists()
        assert r.orient_hint in {"standThin", "layLong"}
        hide = np.asarray(Image.open(r.hide_path))
        # border-alpha == 0 on the keyed hide
        assert hide[0, :, 3].sum() == 0 and hide[-1, :, 3].sum() == 0
        assert hide[:, 0, 3].sum() == 0 and hide[:, -1, 3].sum() == 0
        # cropped to the subject's alpha bbox +6 px exactly (80 px subject)
        assert hide.shape[:2] == (92, 92)
        ys, xs = np.nonzero(hide[..., 3])
        assert (ys.min(), xs.min(), ys.max(), xs.max()) == (6, 6, 85, 85)
        # the lavender key spill on the frame tubes was despilled to g*1.05
        assert tuple(hide[6, 20, :3]) == (63, 60, 63)

    def test_should_refire_a_shredded_mesh_exactly_once_at_224_04(
            self, tmp_path, monkeypatch, kiln_sandbox, software_render,
            shredded_wheel_glb, healed_wheel_glb):
        """Criterion 2, site 1 — shred at 128 triggers ONE refire; the
        refired mesh passes the Turntable's silhouette check."""
        calls = []
        monkeypatch.setattr(kiln, "paint_subject", fake_paint(tmp_path))
        monkeypatch.setattr(kiln, "fire_mesh",
                            fake_mesh({128: shredded_wheel_glb, 224: healed_wheel_glb}, calls))
        r = kiln.kiln_fire("a black omafiets leaning at a slight angle",
                           seed=7, clear_set=CLEAR)
        assert [c["octree"] for c in calls] == [128, 224]
        assert calls[1]["threshold"] == 0.4
        assert r.refire_count == 1
        assert r.octree == 224 and r.threshold == 0.4
        assert r.shredding_detected is False  # the cure took
        assert not kiln.detect_shredding(r.glb_path)

    def test_should_not_refire_a_solid_subject_at_128(self, fired_solid):
        """Criterion 2, site 2 — the gnome stand-in stays at 128."""
        assert [c["octree"] for c in fired_solid["calls"]] == [128]
        r = fired_solid["result"]
        assert r.refire_count == 0 and r.octree == 128
        assert r.shredding_detected is False

    def test_should_park_a_still_tattering_mesh_flagged_not_looping(
            self, tmp_path, monkeypatch, kiln_sandbox, software_render, shredded_wheel_glb):
        calls = []
        monkeypatch.setattr(kiln, "paint_subject", fake_paint(tmp_path))
        monkeypatch.setattr(kiln, "fire_mesh",
                            fake_mesh({128: shredded_wheel_glb, 224: shredded_wheel_glb}, calls))
        r = kiln.kiln_fire("a wrought iron trellis", seed=7, clear_set=CLEAR)
        assert len(calls) == 2  # never a third guess — one refire, then a human
        assert r.refire_count == 1 and r.shredding_detected is True

    def test_should_write_only_inside_kiln_output_never_the_pack_queue(self, fired_solid):
        """Criterion 6 — the write boundary, enforced and grep-verified."""
        r, sandbox = fired_solid["result"], fired_solid["sandbox"]
        out_root = sandbox["out"].resolve()
        for path in (r.glb_path, r.hide_path):
            assert Path(path).resolve().is_relative_to(out_root)
        assert not sandbox["queue"].exists() or not any(sandbox["queue"].iterdir())
        import server
        assert "PACK_QUEUE" not in inspect.getsource(kiln.kiln_fire)
        assert "PACK_QUEUE" not in inspect.getsource(server.BoothWindow.api_kiln_generate)


class TestCuringRack:
    def test_should_park_a_fresh_firing_pending_and_invisible_to_the_packer(self, fired_solid):
        """Criterion 7 — pending on the Rack, nothing under pack-queue/."""
        entries = kiln.rack_list()
        assert len(entries) == 1
        assert entries[0]["recipe"]["status"] == "pending"
        queue = fired_solid["sandbox"]["queue"]
        assert not queue.exists() or not any(queue.iterdir())

    def test_should_move_an_approved_pair_where_pack_props_accepts_it(
            self, fired_solid, tmp_path):
        """Criterion 8 — a real fixture pair through the REAL pack-props.mjs,
        zero hand-editing."""
        cid = fired_solid["result"].id
        verdict = kiln.rack_approve(cid, "gnome-red-hat")
        assert verdict["pack_name"] == "gnome-red-hat"
        queue = fired_solid["sandbox"]["queue"]
        assert (queue / "gnome-red-hat.glb").exists()
        assert (queue / "gnome-red-hat-hide.png").exists()
        assert kiln.read_recipe(cid)["status"] == "approved"

        packer = Path(__file__).resolve().parents[4] / \
            "town-sketches" / "05-de-wandeling" / "pack-props.mjs"
        node = shutil.which("node")
        if not (packer.exists() and node):
            pytest.skip("pack-props.mjs or node not on this bench — packer gate runs in the lab tree")
        workdir = tmp_path / "packer"
        workdir.mkdir()
        shutil.copyfile(packer, workdir / "pack-props.mjs")
        run = subprocess.run(
            [node, "pack-props.mjs", str(queue), "--out", "packed.js", "--global", "__KILN_TEST__"],
            cwd=workdir, capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, run.stderr
        packed = (workdir / "packed.js").read_text()
        assert "gnome-red-hat" in packed and packed.startswith("window.__KILN_TEST__")

    def test_should_refuse_a_colliding_pack_name_voiced_and_keep_it_pending(
            self, fired_solid, tmp_path, monkeypatch, solid_glb):
        """Criterion 9 — the collision guard at the Approve boundary."""
        first = fired_solid["result"].id
        kiln.rack_approve(first, "omafiets")
        second = kiln.kiln_fire("a second bicycle for the rij", seed=8, clear_set=CLEAR)
        with pytest.raises(kiln.RackRefusal, match="'omafiets' is already curing"):
            kiln.rack_approve(second.id, "omafiets")
        assert kiln.read_recipe(second.id)["status"] == "pending"

    def test_should_refuse_a_name_the_packer_regex_would_reject(self, fired_solid):
        with pytest.raises(kiln.RackRefusal, match="lowercase"):
            kiln.rack_approve(fired_solid["result"].id,
                              "A Black Omafiets Leaning At A Slight Angle")

    def test_should_refire_the_judged_hide_byte_identical_and_supersede(
            self, fired_solid, monkeypatch, healed_wheel_glb):
        """Criterion 10, three sites: new-candidate-created,
        hide-byte-identical, original-marked-superseded — all via rack_list."""
        orig = fired_solid["result"]
        new_id = kiln.rack_refire(orig.id, 224, 0.4, clear_set=CLEAR)
        entries = {e["id"]: e for e in kiln.rack_list()}
        assert new_id in entries and orig.id in entries          # site 1
        new_recipe = entries[new_id]["recipe"]
        new_hide = kiln.candidate_dir(new_id) / new_recipe["files"]["hide"]
        assert new_hide.read_bytes() == Path(orig.hide_path).read_bytes()  # site 2
        old_recipe = entries[orig.id]["recipe"]
        assert old_recipe["status"] == "refired"                 # site 3
        assert old_recipe["superseded_by"] == new_id
        assert new_recipe["refired_from"] == orig.id
        assert new_recipe["octree"] == 224 and new_recipe["threshold"] == 0.4
        # criterion 2's fixture check rides along: the last mesh call used 224
        assert fired_solid["calls"][-1]["octree"] == 224

    def test_should_reconstruct_the_full_history_from_the_two_recipes(self, fired_solid):
        """Criterion 11 — original recipe → refire recipe → approved, no
        deleted state."""
        orig = fired_solid["result"]
        new_id = kiln.rack_refire(orig.id, 224, 0.4, clear_set=CLEAR)
        kiln.rack_approve(new_id, "gnome-final")
        first = kiln.read_recipe(orig.id)
        second = kiln.read_recipe(new_id)
        # the chain, walked purely from disk:
        assert first["octree"] == 128 and first["status"] == "refired"
        assert first["superseded_by"] == new_id
        assert second["refired_from"] == orig.id
        assert second["octree"] == 224 and second["status"] == "approved"
        assert second["pack_name"] == "gnome-final"
        assert second["refire_count"] == first["refire_count"] + 1

    def test_should_refuse_to_refire_or_approve_a_superseded_candidate(self, fired_solid):
        orig = fired_solid["result"]
        kiln.rack_refire(orig.id, 224, 0.4, clear_set=CLEAR)
        with pytest.raises(kiln.RackRefusal, match="refired"):
            kiln.rack_approve(orig.id, "too-late")
        with pytest.raises(kiln.RackRefusal, match="refired"):
            kiln.rack_refire(orig.id, 256, 0.4, clear_set=CLEAR)


class TestCanisterLabel:
    def test_should_carry_the_vision_label_from_grounding_to_the_rack_card(
            self, fired_solid, monkeypatch):
        """Criterion 16 — the labeling half of the Appraiser, firing → Rack,
        one chain."""
        import turntable
        monkeypatch.setattr(
            turntable, "vision_ground",
            lambda frame, subject, model=None: {
                "recognized": True, "broken": False,
                "label": "garden gnome, red hat, ceramic"})
        qa = kiln.appraise_candidate(fired_solid["result"].id, clear_set=CLEAR)
        assert qa.canister_label == "garden gnome, red hat, ceramic"
        entry = kiln.rack_list()[0]
        assert entry["recipe"]["canister_label"] == "garden gnome, red hat, ceramic"
        assert entry["qa"]["canister_label"] == "garden gnome, red hat, ceramic"
        assert entry["qa"]["passed"] is True


class TestStagehandsGuard:
    """The non-negotiable containment gate: every GPU swap boundary routes
    through the ONE clear_the_set; nobody grows a second lock."""

    def test_should_guard_the_mesh_stage_before_every_fire(self):
        source = inspect.getsource(kiln.kiln_fire)
        assert source.index("clear_set(MESH_VRAM_GB)") < source.index("fire_mesh(")
        refire = inspect.getsource(kiln.rack_refire)
        assert refire.index("clear_set(MESH_VRAM_GB)") < refire.index("fire_mesh(")

    def test_should_share_the_single_guard_definition_across_the_booth(self):
        import server
        import stagehands
        assert server.clear_the_set is stagehands.clear_the_set
        assert kiln.stagehands.clear_the_set is stagehands.clear_the_set
        assert "def clear_the_set" not in inspect.getsource(kiln)
        assert "def clear_the_set" not in inspect.getsource(server)

    def test_should_give_the_night_shift_no_second_lock(self):
        import night_shift
        source = inspect.getsource(night_shift)
        assert "def clear_the_set" not in source    # no second guard definition
        assert "clear_the_set(" not in source       # no direct GPU call either —
        # the shift only reaches VRAM through the injected fire_take chain
        assert source.count("threading.Lock(") == 1  # the start gate — bookkeeping, not VRAM

    def test_should_fail_closed_when_the_stagehands_cannot_clear(
            self, tmp_path, monkeypatch, kiln_sandbox, software_render, solid_glb):
        monkeypatch.setattr(kiln, "paint_subject", fake_paint(tmp_path))
        monkeypatch.setattr(kiln, "fire_mesh", fake_mesh({128: solid_glb}, []))
        with pytest.raises(kiln.KilnColdError, match="could not clear the GPU"):
            kiln.kiln_fire("a stubborn subject", seed=7,
                           clear_set=lambda need: (False, 3.2))


class TestMeshGraph:
    def test_should_wire_octree_to_the_decode_and_threshold_to_the_mesher(self):
        graph = kiln.kiln_mesh_graph("hide.png", octree=224, threshold=0.4,
                                     seed=7, prefix="kiln-test")
        assert graph["vox"]["inputs"]["octree_resolution"] == 224
        assert graph["mesh"]["inputs"]["threshold"] == 0.4
        assert graph["mesh"]["inputs"]["algorithm"] == "surface net"
        assert graph["ks"]["inputs"]["steps"] == 30 and graph["ks"]["inputs"]["cfg"] == 5.0
        assert graph["ckpt"]["inputs"]["ckpt_name"] == kiln.HUNYUAN_CKPT
        assert graph["save"]["class_type"] == "SaveGLB"

    def test_should_paint_props_on_a_palette_disjoint_ground(self):
        assert kiln.pick_key_colour("terracotta geraniums") == ("chroma magenta", "#FF00FF")
        assert kiln.pick_key_colour("a pink parasol") == ("chroma green", "#00FF00")
        assert kiln.pick_key_colour("purple geranium basket") == ("chroma blue", "#0000FF")


class TestRackDiscard:
    def test_should_break_a_pending_candidate_and_remove_every_artifact(self, fired_solid):
        cid = fired_solid["result"].id
        out = kiln.rack_discard(cid)
        assert out["discarded"] == cid
        assert not kiln.candidate_dir(cid).exists()
        assert cid not in {e["id"] for e in kiln.rack_list()}

    def test_should_refuse_to_break_an_approved_candidate(self, fired_solid):
        cid = fired_solid["result"].id
        kiln.rack_approve(cid, "gnome-red-hat")
        with pytest.raises(kiln.RackRefusal, match="audit trail"):
            kiln.rack_discard(cid)
        assert kiln.candidate_dir(cid).exists()

    def test_should_refuse_a_candidate_that_never_fired(self, kiln_sandbox):
        with pytest.raises(kiln.RackRefusal, match="No candidate"):
            kiln.rack_discard("kiln-00000000-000000-ffffff")


class TestPropShelf:
    def test_should_list_an_approved_pair_married_to_its_firing_record(self, fired_solid):
        cid = fired_solid["result"].id
        kiln.rack_approve(cid, "gnome-red-hat")
        [prop] = kiln.shelf_list()
        assert prop["name"] == "gnome-red-hat"
        assert prop["glb"] == "gnome-red-hat.glb"
        assert prop["hide"] == "gnome-red-hat-hide.png"
        assert prop["subject"] == "a garden gnome with a red hat"
        assert prop["seed"] == 7
        assert prop["two_sided"] is False

    def test_should_read_an_empty_shelf_without_a_queue_dir(self, kiln_sandbox):
        assert kiln.shelf_list() == []
