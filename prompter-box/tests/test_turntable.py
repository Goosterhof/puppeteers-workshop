"""The Turntable's containment suite — every check unit-testable without a
GPU (pre-rendered fixture frames / pre-loaded meshes, never a live pipeline
call), plus the parse half of the vision pass against canned replies."""

import json

import numpy as np
import trimesh
from PIL import Image, ImageDraw

import kiln
import turntable
from turntable import (
    check_floating_islands,
    check_silhouette_continuity,
    check_voxel_hole_ratio,
    parse_grounding_reply,
    render_turntable,
    turntable_qa,
)


def _frame(tmp_path, name, painter):
    size = 256
    mask = Image.new("L", (size, size), 0)
    painter(ImageDraw.Draw(mask))
    path = tmp_path / name
    Image.merge("RGBA", (mask, mask, mask, mask)).save(path)
    return path


class TestSilhouetteContinuity:
    def test_should_pass_one_whole_disk(self, tmp_path):
        frame = _frame(tmp_path, "disk.png", lambda d: d.ellipse((48, 48, 208, 208), fill=255))
        verdict = check_silhouette_continuity([frame], expected_parts=1)
        assert verdict["passed"]
        assert verdict["score"]["parts"] == 1
        assert verdict["score"]["hole_ratio"] < 0.01

    def test_should_fail_a_silhouette_shredded_into_tatters(self, tmp_path):
        def tatters(d):
            for gx in range(4):
                for gy in range(3):
                    d.rectangle((30 + gx * 50, 40 + gy * 60,
                                 60 + gx * 50, 70 + gy * 60), fill=255)
        frame = _frame(tmp_path, "tatters.png", tatters)
        verdict = check_silhouette_continuity([frame], expected_parts=1)
        assert not verdict["passed"]
        assert verdict["score"]["parts"] > 1

    def test_should_fail_a_silhouette_riddled_with_interior_gaps(self, tmp_path):
        def donut(d):
            d.ellipse((28, 28, 228, 228), fill=255)
            d.ellipse((68, 68, 188, 188), fill=0)  # a gaping see-through hole
        frame = _frame(tmp_path, "donut.png", donut)
        verdict = check_silhouette_continuity([frame], expected_parts=1)
        assert not verdict["passed"]
        assert verdict["score"]["hole_ratio"] > turntable.SILHOUETTE_HOLE_LIMIT

    def test_should_honor_expected_parts_for_declared_multi_part_subjects(self, tmp_path):
        def two_parts(d):
            d.ellipse((20, 90, 100, 170), fill=255)
            d.ellipse((150, 90, 230, 170), fill=255)
        frame = _frame(tmp_path, "two.png", two_parts)
        assert not check_silhouette_continuity([frame], expected_parts=1)["passed"]
        assert check_silhouette_continuity([frame], expected_parts=2)["passed"]


class TestVoxelHoleRatio:
    def test_should_pass_a_solid_body(self, solid_glb):
        mesh = trimesh.load(str(solid_glb), force="mesh")
        verdict = check_voxel_hole_ratio(mesh)
        assert verdict["passed"]
        assert verdict["score"] > 0.5

    def test_should_fail_a_body_that_is_mostly_empty_against_its_bbox(self, tmp_path):
        corners = trimesh.util.concatenate([
            trimesh.creation.box(extents=(0.05, 0.05, 0.05)).apply_translation(t)
            for t in ((-1, -1, -1), (1, 1, 1))
        ])
        verdict = check_voxel_hole_ratio(corners)
        assert not verdict["passed"]
        assert verdict["score"] < turntable.VOXEL_OCCUPANCY_FLOOR


class TestFloatingIslands:
    def test_should_pass_one_connected_body(self, solid_glb):
        mesh = trimesh.load(str(solid_glb), force="mesh")
        assert check_floating_islands(mesh, expected_parts=1)["passed"]

    def test_should_fail_a_ring_of_disconnected_fragments(self, shredded_wheel_glb):
        mesh = trimesh.load(str(shredded_wheel_glb), force="mesh")
        verdict = check_floating_islands(mesh, expected_parts=1)
        assert not verdict["passed"]
        assert verdict["score"] == 12

    def test_should_allow_a_declared_second_part(self, tmp_path):
        pair = trimesh.util.concatenate([
            trimesh.creation.box(extents=(1, 1, 1)),
            trimesh.creation.box(extents=(0.8, 0.8, 0.8)).apply_translation((2, 0, 0)),
        ])
        assert not check_floating_islands(pair, expected_parts=1)["passed"]
        assert check_floating_islands(pair, expected_parts=2)["passed"]


class TestTurntableQA:
    def test_should_fail_the_shredded_wheel_naming_silhouette_continuity(
            self, software_render, shredded_wheel_glb):
        qa = turntable_qa(shredded_wheel_glb, expected_parts=1)
        assert qa.passed is False
        assert "silhouette continuity" in qa.failure_reason

    def test_should_pass_a_solid_whole_fixture_on_all_three_checks(
            self, software_render, solid_glb):
        qa = turntable_qa(solid_glb, expected_parts=1)
        assert qa.passed is True
        assert all(c["passed"] for c in qa.checks.values())
        assert len(qa.checks) == 3

    def test_should_pass_the_healed_wheel_after_the_refire(
            self, software_render, healed_wheel_glb):
        qa = turntable_qa(healed_wheel_glb, expected_parts=1)
        assert qa.passed is True

    def test_should_reuse_fresh_frames_instead_of_rendering_twice(self, tmp_path):
        # one render pass, two consumers: frames newer than the GLB are
        # returned as-is — the early return never touches pyrender
        glb = tmp_path / "prop.glb"
        glb.write_bytes(b"stale-mesh-bytes")
        turn = tmp_path / "turn"
        turn.mkdir()
        expected = []
        for i in range(8):
            frame = turn / f"{i:03d}.png"
            Image.new("RGBA", (4, 4)).save(frame)
            expected.append(frame)
        assert render_turntable(glb, out_dir=turn) == expected


class TestVisionGrounding:
    def test_should_parse_a_clean_three_line_reply(self):
        parsed = parse_grounding_reply(
            "RECOGNIZED: yes\nBROKEN: no\n"
            "LABEL: black omafiets, leaning left, weathered frame")
        assert parsed == {"recognized": True, "broken": False,
                         "label": "black omafiets, leaning left, weathered frame"}

    def test_should_parse_a_negative_grounding_as_a_negative(self):
        # the discrimination case: asking "is this a bicycle?" of a gnome render
        parsed = parse_grounding_reply(
            "RECOGNIZED: no — this is a garden gnome, not a bicycle\n"
            "BROKEN: no\nLABEL: ceramic garden gnome with a red hat")
        assert parsed["recognized"] is False
        assert parsed["label"] == "ceramic garden gnome with a red hat"

    def test_should_survive_a_thinking_wrapper_and_flourish(self):
        parsed = parse_grounding_reply(
            "<think>RECOGNIZED: no? hmm, the spokes...</think>\n"
            "Sure! Here is my read:\n**RECOGNIZED: Yes, clearly.**\n"
            "BROKEN: yes — the wheels are shredded\nLABEL: a black bicycle")
        assert parsed == {"recognized": True, "broken": True, "label": "a black bicycle"}

    def test_should_return_nones_for_a_reply_that_never_answers(self):
        assert parse_grounding_reply("the model rambles about art") == {
            "recognized": None, "broken": None, "label": None}


class TestOneInstrumentTwoConsumers:
    """Criterion 18: the shred gate and the Rack's QA are the SAME function,
    verified on the import graph — not two implementations free to drift."""

    def test_should_route_detect_shredding_through_turntable_qa(self):
        import inspect
        source = inspect.getsource(kiln.detect_shredding)
        assert "turntable_qa(" in source
        assert "from turntable import turntable_qa" in inspect.getsource(kiln)

    def test_should_route_the_booths_appraisal_through_the_same_instrument(self):
        import inspect
        import server
        assert "turntable_qa(" in inspect.getsource(kiln.appraise_candidate)
        assert "appraise_candidate(" in inspect.getsource(server.BoothWindow.api_turntable_run)

    def test_should_guard_the_vision_pass_at_the_swap_boundary(self):
        import inspect
        source = inspect.getsource(turntable.turntable_qa)
        assert source.index("clear_set(VISION_VRAM_GB)") < source.index("vision_ground(")


class TestWriteQA:
    def test_should_file_the_report_beside_the_recipe(self, tmp_path,
                                                      software_render, solid_glb):
        qa = turntable_qa(solid_glb, expected_parts=1)
        path = turntable.write_qa(tmp_path, qa)
        filed = json.loads(path.read_text())
        assert filed["passed"] is True
        assert set(filed["checks"]) == {
            "silhouette_continuity", "voxel_hole_ratio", "floating_islands"}
