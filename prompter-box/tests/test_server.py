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
