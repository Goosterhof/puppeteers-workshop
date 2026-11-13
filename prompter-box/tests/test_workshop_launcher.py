"""The `workshop` launcher under test — the one door in.

Each spec builds a throwaway bench in tmp_path: the real launcher script, a
ComfyUI venv python that is this interpreter, and a stand-in booth at
prompter-box/server.py that answers the same windows the real one does. The
launcher runs as a real bash process against a free port, with no window
(WORKSHOP_NO_WINDOW), so what is asserted is what a person at the shortcut
would get: the booth started once, reused, refused or stopped, and the words.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[2] / "workshop"

# The stand-in booth. STUB_MODE picks its shape: "house" (today's booth),
# "older" (a booth from before /api/booth), "crash" (dies while starting).
# STUB_BUSY is a comma list of acts on stage.
STAND_IN = r'''
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

mode = os.environ.get("STUB_MODE", "house")
mode_swapped = mode == "swapped"  # answers as the house, but refuses every close as another booth
if mode_swapped:
    mode = "house"
if mode == "crash":
    print("Traceback: an invented import went missing", flush=True)
    sys.exit(1)
busy = [a for a in os.environ.get("STUB_BUSY", "").split(",") if a]
with open("stand-in.pids", "a") as pids:  # so the spec's teardown can find every booth it started
    pids.write(f"{os.getpid()}\n")

class Window(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def answer(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        if self.path == "/api/booth/close" and mode == "house":
            asked = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if mode_swapped or asked.get("pid") != os.getpid() or asked.get("bench") != os.getcwd():
                return self.answer(412, {"closing": False, "busy": [], "error": "not the booth that was checked"})
            if busy:
                return self.answer(409, {"closing": False, "busy": busy})
            self.answer(202, {"closing": True, "busy": []})
            import threading
            return threading.Thread(target=self.server.shutdown, daemon=True).start()
        return self.answer(404, {"error": "That window is not in this booth."})
    def do_GET(self):
        if self.path == "/api/booth" and mode == "house":
            return self.answer(200, {"booth": "the-prompters-box", "pid": os.getpid(), "busy": busy})
        if self.path == "/api/status":
            return self.answer(200, {"forge": {}, "kiln": {}, "night_shift": {}})
        return self.answer(404, {"error": "That window is not in this booth."})

print("The Prompter's Box opens its window", flush=True)
ThreadingHTTPServer(("127.0.0.1", int(os.environ["WORKSHOP_PORT"])), Window).serve_forever()
'''


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_open(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture
def bench(tmp_path):
    """A bench with the launcher, a machine venv python and the stand-in booth."""
    root = tmp_path / "video-lab"
    (root / "prompter-box").mkdir(parents=True)
    (root / "ComfyUI" / ".venv" / "bin").mkdir(parents=True)
    shutil.copy2(LAUNCHER, root / "workshop")
    (root / "ComfyUI" / ".venv" / "bin" / "python").symlink_to(sys.executable)
    (root / "prompter-box" / "server.py").write_text(STAND_IN)
    port = free_port()
    env = {**os.environ, "WORKSHOP_PORT": str(port), "WORKSHOP_NO_WINDOW": "1",
           "XDG_STATE_HOME": str(tmp_path / "state"), "WORKSHOP_START_WAIT": "10"}
    env.pop("STUB_MODE", None)
    env.pop("STUB_BUSY", None)

    def run(*args, **extra):
        return subprocess.run(["bash", str(root / "workshop"), *args], env={**env, **extra},
                              capture_output=True, text=True, timeout=30)

    run.root = root
    run.port = port
    run.log = tmp_path / "state" / "puppeteers-workshop" / "booth.log"
    yield run
    # Put every stand-in this spec started to bed, by the pids they wrote down, and nothing else.
    for pids in tmp_path.glob("**/prompter-box/stand-in.pids"):
        for pid in pids.read_text().split():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    for _ in range(50):
        if not port_open(port):
            break
        time.sleep(0.1)


def booth_pid(port):
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/booth", timeout=3) as r:
        return json.load(r)["pid"]


@pytest.fixture
def stranger(bench):
    """Something that is not the booth, holding the booth's port."""
    class Nobody(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(404)
            self.end_headers()

    httpd = ThreadingHTTPServer(("127.0.0.1", bench.port), Nobody)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


class TestOpeningTheBooth:
    def test_should_start_a_dark_booth_and_say_where_it_is(self, bench):
        result = bench()
        assert result.returncode == 0, result.stderr
        assert f"The booth is open at http://localhost:{bench.port}/" in result.stdout
        assert port_open(bench.port)
        assert "./workshop opens the booth" in bench.log.read_text()

    def test_should_reuse_a_lit_booth_instead_of_starting_a_second(self, bench):
        assert bench().returncode == 0
        first = booth_pid(bench.port)
        again = bench()
        assert again.returncode == 0, again.stderr
        assert booth_pid(bench.port) == first
        assert bench.log.read_text().count("./workshop opens the booth") == 1

    def test_should_never_hand_the_launch_lock_to_the_booth(self, bench):
        assert bench().returncode == 0
        lock = bench.log.parent / "launch.lock"
        free = subprocess.run(["flock", "-n", str(lock), "true"], capture_output=True)
        assert free.returncode == 0, "the running booth still holds the launch lock"
        # Unlocked is not enough: a booth holding the lock file open would hold the lock
        # again on any path where the launcher dies before it lets go.
        fds = Path(f"/proc/{booth_pid(bench.port)}/fd")
        held = [os.readlink(fd) for fd in fds.iterdir()]
        assert str(lock) not in held

    def test_should_start_one_booth_when_two_launches_race(self, bench):
        procs = [subprocess.Popen(["bash", str(bench.root / "workshop")],
                                  env={**os.environ, "WORKSHOP_PORT": str(bench.port),
                                       "WORKSHOP_NO_WINDOW": "1", "WORKSHOP_START_WAIT": "10",
                                       "XDG_STATE_HOME": str(bench.log.parents[1])},
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for _ in range(2)]
        outs = [p.communicate(timeout=30) for p in procs]
        assert all(p.returncode == 0 for p in procs), outs
        assert bench.log.read_text().count("./workshop opens the booth") == 1

    def test_should_refuse_a_port_held_by_a_stranger_and_start_nothing(self, bench, stranger):
        result = bench()
        assert result.returncode == 1
        assert "isn't the Prompter's Box" in result.stderr
        assert not bench.log.exists() or "opens the booth" not in bench.log.read_text()

    def test_should_open_an_older_booth_but_say_it_cannot_see_its_stage(self, bench):
        assert bench(STUB_MODE="older").returncode == 0
        result = bench(STUB_MODE="older")
        assert result.returncode == 0
        assert "older than this launcher" in result.stdout

    def test_should_name_the_missing_machine_when_run_from_a_blueprint(self, bench):
        (bench.root / "ComfyUI" / ".venv" / "bin" / "python").unlink()
        result = bench()
        assert result.returncode == 1
        assert "The ComfyUI machine isn't on this floor" in result.stderr
        assert "~/code/video-lab" in result.stderr
        assert not port_open(bench.port)

    def test_should_show_the_log_when_the_booth_dies_while_starting(self, bench):
        result = bench(STUB_MODE="crash")
        assert result.returncode == 1
        assert "The booth stopped while it was starting" in result.stderr
        assert "an invented import went missing" in result.stderr

    def test_should_say_a_night_shift_row_picked_up_again_when_it_started_the_booth(self, bench):
        result = bench(STUB_BUSY="night_shift")
        assert result.returncode == 0
        assert "picked up where it stopped" in result.stdout

    def test_should_only_say_a_shift_is_working_when_it_reused_a_lit_booth(self, bench):
        assert bench(STUB_BUSY="night_shift").returncode == 0
        result = bench(STUB_BUSY="night_shift")
        assert result.returncode == 0
        assert "The Night Shift is working a row" in result.stdout
        assert "picked up" not in result.stdout


class TestTheStatus:
    def test_should_call_a_dark_booth_dark(self, bench):
        assert "The booth is dark" in bench("--status").stdout

    def test_should_name_what_is_on_stage(self, bench):
        bench(STUB_BUSY="stage,night_shift")
        result = bench("--status", STUB_BUSY="stage,night_shift")
        assert "On stage: stage, the Night Shift." in result.stdout

    def test_should_say_nothing_is_on_stage_when_idle(self, bench):
        bench()
        assert "with nothing on stage" in bench("--status").stdout


class TestStoppingTheBooth:
    def test_should_put_an_idle_booth_to_bed(self, bench):
        bench()
        result = bench("--stop")
        assert result.returncode == 0, result.stderr
        assert "The booth is dark" in result.stdout
        assert not port_open(bench.port)

    def test_should_refuse_to_stop_mid_take_and_leave_the_booth_lit(self, bench):
        bench(STUB_BUSY="kiln")
        result = bench("--stop")
        assert result.returncode == 2
        assert "Not stopping: kiln still on stage" in result.stderr
        assert port_open(bench.port)

    def test_should_take_the_booths_own_word_on_a_cue_still_being_taken(self, bench):
        bench(STUB_BUSY="cue")
        result = bench("--stop")
        assert result.returncode == 2
        assert "a cue the booth is still taking" in result.stderr
        assert port_open(bench.port)

    def test_should_say_so_when_there_is_nothing_to_stop(self, bench):
        result = bench("--stop")
        assert result.returncode == 0
        assert "already dark" in result.stdout

    def test_should_stop_nothing_when_the_booth_changed_hands_after_the_check(self, bench):
        bench(STUB_MODE="swapped")
        result = bench("--stop")
        assert result.returncode == 1
        assert "changed between the check and the close" in result.stderr
        assert port_open(bench.port)

    def test_should_never_stop_a_stranger(self, bench, stranger):
        result = bench("--stop")
        assert result.returncode == 1
        assert port_open(bench.port)

    def test_should_never_stop_a_booth_it_cannot_ask(self, bench):
        bench(STUB_MODE="older")
        result = bench("--stop")
        assert result.returncode == 1
        assert "Ctrl+C" in result.stderr
        assert port_open(bench.port)

    def test_should_never_stop_a_booth_run_from_another_bench(self, bench, tmp_path):
        other = tmp_path / "other-bench"
        shutil.copytree(bench.root, other, symlinks=True)
        env = {**os.environ, "WORKSHOP_PORT": str(bench.port), "WORKSHOP_NO_WINDOW": "1",
               "XDG_STATE_HOME": str(tmp_path / "other-state")}
        assert subprocess.run(["bash", str(other / "workshop")], env=env, timeout=30).returncode == 0
        result = bench("--stop")
        assert result.returncode == 1
        assert "not from this bench" in result.stderr
        assert port_open(bench.port)


def test_should_refuse_to_make_an_icon_for_a_checkout_without_the_machines(bench):
    (bench.root / "ComfyUI" / ".venv" / "bin" / "python").unlink()
    result = bench("--shortcut", WSL_DISTRO_NAME="Invented-Distro")
    assert result.returncode == 1
    assert "Run ./workshop --shortcut from the bench" in result.stderr


def test_should_refuse_a_word_it_does_not_know(bench):
    result = bench("--frobnicate")
    assert result.returncode == 64
    assert "--help" in result.stderr


def test_should_explain_itself(bench):
    result = bench("--help")
    assert result.returncode == 0
    assert "--shortcut" in result.stdout and "--stop" in result.stdout

