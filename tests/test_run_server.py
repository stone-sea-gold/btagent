"""Tests for the server launcher's port lookup.

The lookup shells out to platform tools, and process ownership is not always
inspectable (a sandboxed or restricted shell can see the listener but not its
PID), so the parsers are pinned against the real output formats of each tool
rather than against a live listener.
"""

import pytest

import run_server

LSOF_OUTPUT = "110741\n"

SS_OUTPUT = (
    "State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
    "LISTEN 0      2048   127.0.0.1:8099      0.0.0.0:*    "
    'users:(("uvicorn",pid=110741,fd=28))\n'
)

# Windows `netstat -ano`: Proto, Local Address, Foreign Address, State, PID.
NETSTAT_OUTPUT = (
    "  TCP    127.0.0.1:8099         0.0.0.0:0              LISTENING       110741\n"
    "  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       110742\n"
    "  TCP    127.0.0.1:8099         127.0.0.1:51000        ESTABLISHED     110999\n"
)


def _fake_tools(monkeypatch, **outputs: str) -> None:
    """Serve canned output per tool name, as if each command were installed."""

    def fake(command: list[str]) -> str:
        return outputs.get(command[0], "")

    monkeypatch.setattr(run_server, "_stdout_of", fake)


class TestPosixLookup:
    def test_lsof_output_yields_pids(self, monkeypatch):
        monkeypatch.setattr(run_server, "WINDOWS", False)
        _fake_tools(monkeypatch, lsof=LSOF_OUTPUT)

        assert run_server.find_pids_on_port(8099) == [110741]

    def test_ss_is_used_when_lsof_is_missing(self, monkeypatch):
        monkeypatch.setattr(run_server, "WINDOWS", False)
        _fake_tools(monkeypatch, lsof="", ss=SS_OUTPUT)

        assert run_server.find_pids_on_port(8099) == [110741]

    def test_ss_query_carries_the_port_filter(self, monkeypatch):
        """An unfiltered `ss -ltnp` would expose every socket's pid."""
        seen: list[list[str]] = []

        def fake(command: list[str]) -> str:
            seen.append(command)
            return "" if command[0] == "lsof" else SS_OUTPUT

        monkeypatch.setattr(run_server, "WINDOWS", False)
        monkeypatch.setattr(run_server, "_stdout_of", fake)

        run_server.find_pids_on_port(8099)

        ss_calls = [c for c in seen if c[0] == "ss"]
        assert ss_calls, "ss fallback was never consulted"
        assert any(":8099" in arg for arg in ss_calls[0])

    def test_no_listener_is_empty(self, monkeypatch):
        monkeypatch.setattr(run_server, "WINDOWS", False)
        _fake_tools(monkeypatch, lsof="", ss="State  Recv-Q\n")

        assert run_server.find_pids_on_port(8099) == []


class TestWindowsLookup:
    def test_netstat_rows_are_filtered_by_port(self, monkeypatch):
        monkeypatch.setattr(run_server, "WINDOWS", True)
        _fake_tools(monkeypatch, netstat=NETSTAT_OUTPUT)

        assert run_server.find_pids_on_port(8099) == [110741]
        assert run_server.find_pids_on_port(8000) == [110742]

    def test_non_listening_rows_are_ignored(self, monkeypatch):
        """An established connection on the port is not the listener."""
        monkeypatch.setattr(run_server, "WINDOWS", True)
        _fake_tools(monkeypatch, netstat=NETSTAT_OUTPUT)

        assert 110999 not in run_server.find_pids_on_port(8099)


class TestFreePort:
    def test_free_port_is_a_noop_without_a_listener(self, monkeypatch):
        monkeypatch.setattr(run_server, "WINDOWS", False)
        _fake_tools(monkeypatch, lsof="", ss="")

        run_server.free_port(8099)  # must not raise or exit

    def test_free_port_signals_the_listener(self, monkeypatch):
        """Once killed, the listener is gone and the port reads as free."""
        monkeypatch.setattr(run_server, "WINDOWS", False)
        state = {"busy": True}

        def fake(command: list[str]) -> str:
            return LSOF_OUTPUT if state["busy"] and command[0] == "lsof" else ""

        killed: list[int] = []

        def kill(pid: int) -> bool:
            killed.append(pid)
            state["busy"] = False
            return True

        monkeypatch.setattr(run_server, "_stdout_of", fake)
        monkeypatch.setattr(run_server, "kill_process", kill)

        run_server.free_port(8099)

        assert killed == [110741]

    def test_free_port_exits_when_the_port_stays_busy(self, monkeypatch):
        """A listener that refuses to die must fail loudly, not start anyway."""
        monkeypatch.setattr(run_server, "WINDOWS", False)
        _fake_tools(monkeypatch, lsof=LSOF_OUTPUT, ss="")
        monkeypatch.setattr(run_server, "kill_process", lambda pid: True)
        monkeypatch.setattr(run_server.time, "sleep", lambda _: None)

        with pytest.raises(SystemExit):
            run_server.free_port(8099)
