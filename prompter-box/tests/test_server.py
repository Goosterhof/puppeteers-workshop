"""The booth's service hatch under test — the stage door, the traversal
guards, the 404 voice, and the 409 refusals that keep two takes off one GPU.

Everything here drives a REAL ThreadingHTTPServer on an ephemeral port, so
what is asserted is what a browser would actually receive: status line,
headers, body. No GPU and no machines — the file-serving roots are
monkeypatched into tmp_path and every station that would reach for VRAM is
refused before it gets there, which is exactly the code path under test.
"""

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

import kiln
import server


@pytest.fixture
def booth(tmp_path, monkeypatch):
    """A booth on an ephemeral port with every root inside tmp_path.

    The archive rooms are real directories with one real file each, so the
    traversal specs can prove the guard refuses the escape while still
    serving the neighbour it is guarding.
    """
    rooms = {}
    for attr, name in (("STATIC", "static"), ("FOOTAGE", "footage"),
                       ("COMFY_OUT", "face-output"), ("WAN_OUT", "stage-output"),
                       ("MM_OUT", "foley-output")):
        room = tmp_path / name
        room.mkdir(parents=True)
        monkeypatch.setattr(server, attr, room)
        rooms[name] = room
    for attr, name in (("KILN_OUT", "kiln-output"), ("PACK_QUEUE", "pack-queue")):
        room = tmp_path / name
        room.mkdir(parents=True)
        monkeypatch.setattr(kiln, attr, room)
        rooms[name] = room

    (rooms["static"] / "index.html").write_text("<title>The Prompter's Box</title>")
    (rooms["footage"] / "crier.png").write_bytes(b"\x89PNG a face the booth guards")
    (rooms["face-output"] / "painting.png").write_bytes(b"\x89PNG a painting")
    (tmp_path / "outside.png").write_bytes(b"\x89PNG the neighbour's business")

    # Idle stations, and no real socket probe for the Wan2GP UI: these specs
    # assert the booth's own refusals, not the bench's port weather.
    monkeypatch.setattr(server, "stage_job", {"state": "idle"})
    monkeypatch.setattr(server, "foley_job", {"state": "idle"})
    monkeypatch.setattr(server, "kiln_job", {"state": "idle"})
    monkeypatch.setattr(server, "port_open", lambda _port: False)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.BoothWindow)
    # poll_interval is the shutdown latency, paid once per spec: the stock
    # 0.5 s turns a 33-spec suite into a 17-second one.
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01},
                     daemon=True).start()
    host = f"127.0.0.1:{httpd.server_address[1]}"

    def knock(method, path, body=None, headers=None):
        conn = http.client.HTTPConnection(host, timeout=5)
        try:
            conn.request(method, path, body, headers or {})
            resp = conn.getresponse()
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return resp.status, raw  # a served reel is bytes, not a reply
        finally:
            conn.close()

    knock.host = host
    knock.rooms = rooms
    knock.tmp = tmp_path
    try:
        yield knock
    finally:
        httpd.shutdown()
        httpd.server_close()


def cue(booth, path, payload, ctype="application/json", origin=None):
    headers = {"Content-Type": ctype} if ctype else {}
    if origin:
        headers["Origin"] = origin
    return booth("POST", path, json.dumps(payload), headers)


class TestTheStageDoor:
    """P1-1 — the perimeter. The bind keeps the LAN out; these keep the
    other browser tabs out, which the bind cannot."""

    def test_should_refuse_a_post_that_is_not_marked_as_a_cue_sheet(self, booth):
        # text/plain + a JSON body is a CORS *simple* request: no preflight,
        # no consent, and the damage is the side effect rather than the reply.
        status, body = cue(booth, "/api/rack/discard", {"candidate_id": "x"},
                           ctype="text/plain")
        assert status == 415
        assert "application/json" in body["error"]

    def test_should_refuse_a_post_that_arrives_unmarked(self, booth):
        status, body = cue(booth, "/api/rack/discard", {"candidate_id": "x"}, ctype=None)
        assert status == 415
        assert "unmarked" in body["error"]

    def test_should_read_a_cue_sheet_marked_with_a_charset_parameter(self, booth):
        status, _ = cue(booth, "/api/rack/discard", {"candidate_id": "nobody"},
                        ctype="application/json; charset=utf-8")
        assert status != 415

    def test_should_refuse_a_post_shouted_in_from_another_origin(self, booth):
        status, body = cue(booth, "/api/kiln/generate", {"subject": "a lantern"},
                           origin="http://evil.example")
        assert status == 403
        assert "http://evil.example" in body["error"]
        assert "its own console" in body["error"]

    def test_should_refuse_a_get_shouted_in_from_another_origin(self, booth):
        status, body = booth("GET", "/footage/crier.png",
                             headers={"Origin": "http://evil.example"})
        assert status == 403
        assert "http://evil.example" in body["error"]

    def test_should_admit_a_request_whose_origin_is_the_booths_own(self, booth):
        status, body = booth("GET", "/api/footage",
                             headers={"Origin": f"http://{booth.host}"})
        assert status == 200
        assert body["images"] == ["crier.png"]

    def test_should_admit_the_side_port_booth_because_the_host_decides_the_house(self, booth):
        # verify-sideport.py runs the SAME handler on :7901. A hardcoded
        # :7900 origin check would lock the bench out of its own probe.
        assert booth.host != "127.0.0.1:7900"
        status, _ = booth("GET", "/api/footage", headers={"Origin": f"http://{booth.host}"})
        assert status == 200

    def test_should_admit_a_caller_that_sends_no_origin_at_all(self, booth):
        # curl, the verify probes, and same-origin GETs all arrive bare.
        status, _ = booth("GET", "/api/footage")
        assert status == 200

    def test_should_bind_the_house_interface_and_never_every_interface(self, booth):
        assert server.HOUSE_HOST == "127.0.0.1"
        import inspect
        assert '"0.0.0.0"' not in inspect.getsource(server)


class TestTheArchiveGuards:
    """P1-3 — the boundary between the booth and the footage archive.
    `footage/` is 'personal media... never leaves the building.'"""

    def test_should_serve_a_reel_that_is_genuinely_in_the_archive(self, booth):
        status, body = booth("GET", "/footage/crier.png")
        assert status == 200
        assert body == b"\x89PNG a face the booth guards"

    @pytest.mark.parametrize("room", ["/footage/", "/face-output/", "/stage-output/",
                                      "/foley-output/", "/kiln-output/", "/pack-queue/",
                                      "/static/"])
    def test_should_refuse_a_climb_out_of_every_guarded_room(self, booth, room):
        status, body = booth("GET", f"{room}%2e%2e/outside.png")
        assert status == 404
        assert body["error"] == "That reel is not in the archive."

    def test_should_refuse_an_absolute_path_dressed_as_a_reel_name(self, booth):
        status, body = booth("GET", "/footage//etc/passwd")
        assert status == 404
        assert body["error"] == "That reel is not in the archive."

    def test_should_refuse_a_directory_that_is_not_a_file(self, booth):
        (booth.rooms["footage"] / "reels").mkdir()
        status, _ = booth("GET", "/footage/reels")
        assert status == 404

    def test_should_resolve_a_reel_reference_only_inside_its_own_root(self, booth):
        # resolve_reel touches no request state — the 'stage:'/'footage:'
        # grammar is the whole contract.
        resolve = server.BoothWindow.resolve_reel
        assert resolve(None, "footage:crier.png") == booth.rooms["footage"] / "crier.png"
        assert resolve(None, "footage:../outside.png") is None
        assert resolve(None, "stage:../../outside.png") is None
        assert resolve(None, "footage:") is None
        assert resolve(None, None) is None

    def test_should_refuse_to_cast_a_painting_from_outside_the_rack(self, booth):
        status, body = cue(booth, "/api/stage/cast", {"image": "../outside.png"})
        assert status == 404
        assert body["error"] == "That painting is not hanging on that rack."
        assert not (booth.rooms["footage"] / "outside.png").exists()

    def test_should_cast_a_painting_that_really_hangs_on_the_rack(self, booth):
        status, body = cue(booth, "/api/stage/cast", {"image": "painting.png"})
        assert status == 200
        assert body["cast"] == "painting.png"
        assert (booth.rooms["footage"] / "painting.png").read_bytes() == b"\x89PNG a painting"


class TestTheBoothsVoice:
    """The Error Manifesto at the routing table — a wrong window is answered
    in character, not with a stack trace."""

    def test_should_answer_an_unknown_get_window_in_the_booths_voice(self, booth):
        status, body = booth("GET", "/api/understage/secrets")
        assert status == 404
        assert body["error"] == "The booth has no such window."

    def test_should_answer_an_unknown_post_window_in_the_booths_voice(self, booth):
        status, body = cue(booth, "/api/stage/detonate", {})
        assert status == 404
        assert body["error"] == "The booth has no such window."

    def test_should_refuse_a_cue_sheet_that_is_not_valid_json(self, booth):
        status, body = booth("POST", "/api/forge", "{not json",
                             {"Content-Type": "application/json"})
        assert status == 400
        assert body["error"] == "The cue sheet is not valid JSON."

    def test_should_serve_the_console_at_the_root_window(self, booth):
        status, body = booth("GET", "/")
        assert status == 200
        assert b"The Prompter's Box" in body


class TestTheOnePerformanceStage:
    """The 409s — one GPU, one performance. Every refusal here fires BEFORE
    any station reaches for VRAM, which is why the suite needs no hardware."""

    def test_should_refuse_a_firing_while_the_stage_is_mid_performance(self, booth, monkeypatch):
        monkeypatch.setattr(server, "stage_job", {"state": "running"})
        status, body = cue(booth, "/api/kiln/generate", {"subject": "a lantern"})
        assert status == 409
        assert "two masters" in body["error"]

    def test_should_refuse_a_firing_while_the_foley_booth_is_mid_take(self, booth, monkeypatch):
        monkeypatch.setattr(server, "foley_job", {"state": "running"})
        status, body = cue(booth, "/api/kiln/generate", {"subject": "a lantern"})
        assert status == 409
        assert "Foley Booth is mid-take" in body["error"]

    def test_should_refuse_a_firing_while_the_full_ui_holds_the_stage(self, booth, monkeypatch):
        monkeypatch.setattr(server, "port_open", lambda _port: True)
        status, body = cue(booth, "/api/kiln/generate", {"subject": "a lantern"})
        assert status == 409
        assert ":7860" in body["error"]

    def test_should_refuse_a_firing_while_the_night_shift_works_a_row(self, booth, monkeypatch):
        monkeypatch.setattr(server.night_shift, "shift_status",
                            lambda: {"running": True, "row_id": "row-1",
                                     "subject": "a cart", "started": None})
        status, body = cue(booth, "/api/kiln/generate", {"subject": "a lantern"})
        assert status == 409
        assert "one order at a time" in body["error"]

    def test_should_refuse_a_stage_take_while_the_full_ui_holds_the_gpu(self, booth, monkeypatch):
        monkeypatch.setattr(server, "port_open", lambda _port: True)
        monkeypatch.setattr(server, "stage_playbill", lambda: [
            {"type": "ti2v_2_2", "name": "The 5B", "kind": "t2v", "vram_gb": 18,
             "resolution": "704x1280", "video_length": 41, "steps": 30,
             "guidance": 5, "loras": [], "lora_shelf": "wan_5B", "note": "", "recipe": {}},
        ])
        status, body = cue(booth, "/api/stage/generate",
                           {"prompt": "the crier swings the bell", "model_type": "ti2v_2_2"})
        assert status == 409
        assert "cannot share the GPU" in body["error"]

    def test_should_refuse_a_refire_of_a_candidate_that_is_not_on_the_rack(self, booth):
        status, body = cue(booth, "/api/rack/refire", {"candidate_id": "ghost"})
        assert status == 404
        assert "No candidate 'ghost' is curing on the rack." == body["error"]

    def test_should_name_the_empty_subject_before_it_ever_reaches_the_kiln(self, booth):
        status, body = cue(booth, "/api/kiln/generate", {"subject": "   "})
        assert status == 400
        assert "empty subject" in body["error"]


def fake_comfy(stats=None, queue=None):
    """A stand-in for http_json: answers /system_stats and /queue like the
    real ComfyUI, or refuses like a dark one (stats/queue None → OSError)."""
    def fake(url, payload=None, timeout=10):
        if url.endswith("/system_stats"):
            if stats is None:
                raise OSError("dark")
            return stats
        if url.endswith("/queue"):
            if queue is None:
                raise OSError("dark")
            return queue
        raise OSError(f"unexpected probe: {url}")
    return fake


class TestTheCallboardTruth:
    """Chaos #00085 detonations 1+2 — the /queue probe that lets the Face
    Shop plate go live, and the dimmer's nvidia-smi driver fallback."""

    STATS = {"devices": [{"vram_free": 6e9, "vram_total": 24e9}]}

    @pytest.fixture(autouse=True)
    def _quiet_floor(self, monkeypatch):
        monkeypatch.setattr(server, "loaded_llms", lambda: None)
        monkeypatch.setattr(server, "gpu_vram_gb", lambda: None)

    def test_should_report_a_running_paint_so_the_face_plate_can_go_live(self, booth, monkeypatch):
        monkeypatch.setattr(server, "http_json",
                            fake_comfy(self.STATS, {"queue_running": [["job"]], "queue_pending": []}))
        status, body = booth("GET", "/api/status")
        assert status == 200
        assert body["face_shop"] == {"up": True, "vram_free_gb": 6.0,
                                     "vram_total_gb": 24.0, "painting": True}

    def test_should_read_not_painting_when_the_queue_is_empty(self, booth, monkeypatch):
        monkeypatch.setattr(server, "http_json",
                            fake_comfy(self.STATS, {"queue_running": [], "queue_pending": []}))
        _, body = booth("GET", "/api/status")
        assert body["face_shop"]["painting"] is False

    def test_should_never_fake_a_performance_when_the_queue_probe_fails(self, booth, monkeypatch):
        monkeypatch.setattr(server, "http_json", fake_comfy(self.STATS, queue=None))
        _, body = booth("GET", "/api/status")
        assert body["face_shop"]["up"] is True
        assert body["face_shop"]["painting"] is False

    def test_should_fall_back_to_driver_vram_when_the_face_shop_is_dark(self, booth, monkeypatch):
        monkeypatch.setattr(server, "http_json", fake_comfy(stats=None))
        monkeypatch.setattr(server, "gpu_vram_gb", lambda: (20.42, 31.84))
        _, body = booth("GET", "/api/status")
        assert body["face_shop"] == {"up": False}
        assert body["gpu"] == {"vram_free_gb": 20.4, "vram_total_gb": 31.8}

    def test_should_leave_the_meter_dark_only_when_the_driver_is_silent(self, booth, monkeypatch):
        monkeypatch.setattr(server, "http_json", fake_comfy(stats=None))
        _, body = booth("GET", "/api/status")
        assert body["gpu"] is None


class TestThePinboardWindows:
    """#08 — the Pinboard over HTTP: the same knock the front's store makes.
    The grammar itself is specced in test_pins.py; these prove the windows
    speak it with the right status lines."""

    @pytest.fixture(autouse=True)
    def sandboxed_board(self, booth, monkeypatch):
        import pins
        monkeypatch.setattr(pins, "PINS_FILE", booth.tmp / "pinned-recipes.json")

    CARD = {"name": "Spoked Vehicle", "room": "kiln", "source": "kiln-test-0001",
            "recipe": {"octree": 224, "threshold": 0.4, "seed": 7}}

    def test_should_hang_a_pin_and_list_it_through_the_window(self, booth):
        status, reply = cue(booth, "/api/pins/pin", self.CARD)
        assert status == 200
        assert reply["pin"]["name"] == "Spoked Vehicle"
        status, reply = booth("GET", "/api/pins")
        assert status == 200
        assert [p["name"] for p in reply["pins"]] == ["Spoked Vehicle"]

    def test_should_voice_a_grammar_refusal_as_a_400(self, booth):
        status, reply = cue(booth, "/api/pins/pin", {**self.CARD, "name": " "})
        assert status == 400
        assert "name the pin" in reply["error"]

    def test_should_404_an_unpin_of_a_ghost(self, booth):
        status, reply = cue(booth, "/api/pins/unpin", {"pin_id": "pin-deadbeef"})
        assert status == 404
        assert "already be unpinned" in reply["error"]

    def test_should_unpin_through_the_window(self, booth):
        _, reply = cue(booth, "/api/pins/pin", self.CARD)
        status, _ = cue(booth, "/api/pins/unpin", {"pin_id": reply["pin"]["id"]})
        assert status == 200
        assert booth("GET", "/api/pins")[1]["pins"] == []


class TestBringYourOwnStill:
    """The shelf's own stage door — a still from the browser lands in
    footage/ through the SAME JSON door as every other cue, identified by
    its bytes, named safely, never overwriting what already hangs there."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"a sitter the investor brought"
    JPG = b"\xff\xd8\xff\xe0" + b"a jpeg sitter"
    WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"a webp sitter"

    @staticmethod
    def b64(data):
        import base64
        return base64.b64encode(data).decode()

    def test_should_shelve_a_png_and_list_it_on_the_footage_shelf(self, booth):
        status, body = cue(booth, "/api/footage/upload",
                           {"name": "my-sitter.png", "data": self.b64(self.PNG)})
        assert status == 200
        assert body == {"shelved": "my-sitter.png", "bytes": len(self.PNG)}
        assert (booth.rooms["footage"] / "my-sitter.png").read_bytes() == self.PNG
        _, listing = booth("GET", "/api/footage")
        assert "my-sitter.png" in listing["images"]

    def test_should_read_a_data_url_the_way_a_filereader_hands_it_over(self, booth):
        status, body = cue(booth, "/api/footage/upload",
                           {"name": "reader.png", "data": f"data:image/png;base64,{self.b64(self.PNG)}"})
        assert status == 200
        assert body["shelved"] == "reader.png"

    @pytest.mark.parametrize("claimed,data,expected", [
        ("photo.jpeg", JPG, "photo.jpg"),
        ("photo.webp", WEBP, "photo.webp"),
        ("lying.png", JPG, "lying.jpg"),  # the bytes name the extension, not the browser
    ])
    def test_should_name_the_still_by_what_its_bytes_are(self, booth, claimed, data, expected):
        status, body = cue(booth, "/api/footage/upload", {"name": claimed, "data": self.b64(data)})
        assert status == 200
        assert body["shelved"] == expected

    def test_should_flatten_a_name_that_tries_to_climb_out_of_the_shelf(self, booth):
        status, body = cue(booth, "/api/footage/upload",
                           {"name": "../../outside.png", "data": self.b64(self.PNG)})
        assert status == 200
        assert body["shelved"] == "outside.png"
        assert (booth.rooms["footage"] / "outside.png").exists()
        assert booth.tmp.joinpath("outside.png").read_bytes() == b"\x89PNG the neighbour's business"

    def test_should_tame_a_wild_name_and_fall_back_to_still_when_nothing_is_left(self, booth):
        status, body = cue(booth, "/api/footage/upload",
                           {"name": "C:\\Users\\me\\my photo (1)!.PNG", "data": self.b64(self.PNG)})
        assert status == 200
        assert body["shelved"] == "my-photo-1.png"
        status, body = cue(booth, "/api/footage/upload", {"name": "???", "data": self.b64(self.PNG)})
        assert body["shelved"] == "still.png"

    def test_should_never_overwrite_a_still_that_already_hangs_there(self, booth):
        status, body = cue(booth, "/api/footage/upload",
                           {"name": "crier.png", "data": self.b64(self.PNG)})
        assert status == 200
        assert body["shelved"] == "crier-2.png"
        assert (booth.rooms["footage"] / "crier.png").read_bytes() == b"\x89PNG a face the booth guards"
        _, body = cue(booth, "/api/footage/upload", {"name": "crier.png", "data": self.b64(self.PNG)})
        assert body["shelved"] == "crier-3.png"

    def test_should_refuse_a_file_that_is_not_a_still(self, booth):
        status, body = cue(booth, "/api/footage/upload",
                           {"name": "page.png", "data": self.b64(b"<html>not a still</html>")})
        assert status == 415
        assert "PNG, JPEG, or WebP" in body["error"]
        assert not (booth.rooms["footage"] / "page.png").exists()

    def test_should_refuse_an_empty_or_garbled_upload(self, booth):
        status, body = cue(booth, "/api/footage/upload", {"name": "void.png", "data": ""})
        assert status == 400
        assert "Nothing arrived" in body["error"]
        status, body = cue(booth, "/api/footage/upload", {"name": "void.png", "data": "not base64!!"})
        assert status == 400
        assert "garbled" in body["error"]

    def test_should_refuse_a_still_heavier_than_the_shelf_can_hold(self, booth, monkeypatch):
        monkeypatch.setattr(server, "STILL_CEILING_BYTES", 16)
        status, body = cue(booth, "/api/footage/upload",
                           {"name": "heavy.png", "data": self.b64(self.PNG)})
        assert status == 413
        assert "shelf takes up to" in body["error"]

    def test_should_leave_no_torn_still_behind(self, booth):
        cue(booth, "/api/footage/upload", {"name": "whole.png", "data": self.b64(self.PNG)})
        assert [p.name for p in booth.rooms["footage"].glob(".*.part")] == []

    def test_should_walk_through_the_same_stage_door_as_every_other_cue(self, booth):
        status, _ = cue(booth, "/api/footage/upload",
                        {"name": "x.png", "data": self.b64(self.PNG)}, origin="http://evil.example")
        assert status == 403
        status, _ = cue(booth, "/api/footage/upload",
                        {"name": "x.png", "data": self.b64(self.PNG)}, ctype="text/plain")
        assert status == 415
        assert not (booth.rooms["footage"] / "x.png").exists()


class TestTheBin:
    """Binning a take — one file, one room, behind the front's confirm; the
    booth still refuses every climb, every directory, every room that keeps
    its own audit trail."""

    def test_should_bin_a_painting_from_the_face_rack(self, booth):
        status, body = cue(booth, "/api/take/discard", {"room": "face", "name": "painting.png"})
        assert status == 200
        assert body == {"binned": "painting.png", "room": "face"}
        assert not (booth.rooms["face-output"] / "painting.png").exists()

    def test_should_bin_a_still_the_investor_shelved_in_footage(self, booth):
        status, body = cue(booth, "/api/take/discard", {"room": "footage", "name": "crier.png"})
        assert status == 200
        assert body["binned"] == "crier.png"
        _, listing = booth("GET", "/api/footage")
        assert listing["images"] == []

    def test_should_bin_a_foley_score_by_its_path_inside_the_room(self, booth):
        reel = booth.rooms["foley-output"] / "2026-08" / "toll.flac"
        reel.parent.mkdir()
        reel.write_bytes(b"fLaC a toll")
        status, body = cue(booth, "/api/take/discard", {"room": "foley", "name": "2026-08/toll.flac"})
        assert status == 200
        assert body["binned"] == "2026-08/toll.flac"
        assert not reel.exists()
        assert reel.parent.exists()  # only the file goes, never its room

    @pytest.mark.parametrize("name", ["../outside.png", "../../outside.png", "/etc/passwd", "", "reels"])
    def test_should_refuse_every_climb_directory_and_blank(self, booth, name):
        (booth.rooms["footage"] / "reels").mkdir(exist_ok=True)
        status, body = cue(booth, "/api/take/discard", {"room": "footage", "name": name})
        assert status == 404
        assert body["error"] == "That take is not hanging in that room — nothing to bin."
        assert booth.tmp.joinpath("outside.png").exists()
        assert (booth.rooms["footage"] / "crier.png").exists()

    @pytest.mark.parametrize("room", ["kiln", "pack-queue", "static", "", "../footage"])
    def test_should_refuse_rooms_that_are_not_on_the_bin_list(self, booth, room):
        status, body = cue(booth, "/api/take/discard", {"room": room, "name": "index.html"})
        assert status == 404
        assert "only face, stage, foley, or footage" in body["error"]
        assert (booth.rooms["static"] / "index.html").exists()

    def test_should_walk_through_the_same_stage_door_as_every_other_cue(self, booth):
        status, _ = cue(booth, "/api/take/discard", {"room": "face", "name": "painting.png"},
                        origin="http://evil.example")
        assert status == 403
        status, _ = cue(booth, "/api/take/discard", {"room": "face", "name": "painting.png"},
                        ctype="text/plain")
        assert status == 415
        assert (booth.rooms["face-output"] / "painting.png").exists()
