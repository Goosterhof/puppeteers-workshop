"""Admission must have a current driver reading; no hardware is used here."""

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import stagehands


def test_should_read_free_memory_from_a_successful_driver_reply(monkeypatch):
    monkeypatch.setattr(stagehands.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout="32768, 4096\n"))
    assert stagehands.gpu_vram_gb() == (28.0, 32.0)


@pytest.mark.parametrize("code, output", [
    (1, "32768, 4096"), (0, ""), (0, "driver unavailable"),
    (0, "32768, 40000"), (0, "0, 0"), (0, "32768, -1"), (0, "-1, -2"),
])
def test_should_treat_failed_or_impossible_driver_readings_as_unknown(monkeypatch, code, output):
    monkeypatch.setattr(stagehands.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=code, stdout=output))
    assert stagehands.gpu_vram_gb() is None


@pytest.mark.parametrize("error", [FileNotFoundError("no driver"),
                                   subprocess.TimeoutExpired("nvidia-smi", 5)])
def test_should_treat_a_missing_or_timed_out_driver_as_unknown(monkeypatch, error):
    monkeypatch.setattr(stagehands.subprocess, "run", Mock(side_effect=error))
    assert stagehands.gpu_vram_free_gb() is None


@pytest.fixture
def crew(monkeypatch):
    clock = SimpleNamespace(now=0, sleeps=[])

    def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(stagehands, "time", SimpleNamespace(time=lambda: clock.now, sleep=sleep))
    http = Mock(return_value={})
    monkeypatch.setattr(stagehands, "http_json", http)

    def readings(*values):
        meter = Mock(side_effect=values)
        monkeypatch.setattr(stagehands, "gpu_vram_free_gb", meter)
        return meter

    return SimpleNamespace(clock=clock, http=http, readings=readings)


def test_should_refuse_an_unknown_meter_without_asking_a_machine_to_work(crew):
    meter = crew.readings(None)
    assert stagehands.clear_the_set(13) == (False, None)
    assert meter.call_count == 1
    crew.http.assert_not_called()
    assert crew.clock.sleeps == []


def test_should_refuse_if_the_meter_disappears_while_waiting(crew):
    meter = crew.readings(1.0, None)
    assert stagehands.clear_the_set(13) == (False, None)
    assert meter.call_count == 2
    assert crew.clock.sleeps == [1]


@pytest.mark.parametrize("free", [13.0, 28.0])
def test_should_admit_a_verified_clear_stage_without_striking_it(crew, free):
    crew.readings(free)
    assert stagehands.clear_the_set(13) == (True, free)
    crew.http.assert_not_called()
    assert crew.clock.sleeps == []


def test_should_knock_then_admit_only_after_the_driver_confirms_clearance(crew):
    crew.readings(1.0, 3.0, 13.0)
    assert stagehands.clear_the_set(13) == (True, 13.0)
    assert [call.args[0] for call in crew.http.call_args_list] == [
        f"{stagehands.COMFY}/free", f"{stagehands.COMFY}/prompt",
    ]
    assert crew.clock.sleeps == [1, 1]


def test_should_refuse_known_insufficient_memory_at_the_deadline(crew):
    crew.readings(1.0, 2.0, 3.0)
    assert stagehands.clear_the_set(13, wait_s=2) == (False, 3.0)
    assert crew.clock.now == 2


def test_should_still_require_driver_clearance_when_comfy_does_not_answer(crew):
    crew.http.side_effect = OSError("an invented dark Face Shop")
    crew.readings(1.0, 2.0)
    assert stagehands.clear_the_set(13, wait_s=1) == (False, 2.0)


def test_should_allow_a_fresh_retry_after_the_meter_recovers(crew):
    crew.readings(None, 13.0)
    assert stagehands.clear_the_set(13) == (False, None)
    assert stagehands.clear_the_set(13) == (True, 13.0)
