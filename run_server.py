"""AIFUND5 API server launcher.

Usage:
    python run_server.py              # Start on default port 8000
    python run_server.py --port 8001  # Start on custom port
    python run_server.py --kill       # Kill running server and exit

Frees the port before starting. Port lookup is platform-aware: Windows ships
``netstat``/``taskkill``, while Linux images usually ship ``lsof`` and ``ss``
instead — ``netstat`` is frequently absent, which previously made this script's
port check a silent no-op on Linux.
"""

import argparse
import os
import re
import signal
import subprocess
import sys
import time

WINDOWS = sys.platform == "win32"


def _stdout_of(command: list[str]) -> str:
    """Output of ``command``, or ``""`` when the tool is missing or fails."""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def _describe(pid: int) -> str:
    """A short command line for ``pid``, so the user sees what will be killed."""
    if WINDOWS:
        return ""
    return _stdout_of(["ps", "-p", str(pid), "-o", "args="]).strip()[:90]


def find_pids_on_port(port: int) -> list[int]:
    """PIDs listening on ``port``, best effort for the current platform."""
    if WINDOWS:
        pids = set()
        for line in _stdout_of(["netstat", "-ano"]).splitlines():
            parts = line.split()
            # Proto  Local Address  Foreign Address  State  PID
            if (
                len(parts) >= 5
                and parts[-2] == "LISTENING"
                and f":{port}" in parts[1]
                and parts[-1].isdigit()
            ):
                pids.add(int(parts[-1]))
        return sorted(pids)

    # lsof prints bare PIDs; ss is the fallback when lsof is unavailable. The ss
    # query must carry the port filter: an unfiltered `ss -ltnp` lists every
    # socket, so scanning it for `pid=` could return a different port's process.
    listed = _stdout_of(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"]).split()
    pids = {int(item) for item in listed if item.isdigit()}
    if pids:
        return sorted(pids)
    filtered = _stdout_of(["ss", "-ltnp", f"sport = :{port}"])
    return sorted({int(m) for m in re.findall(r"pid=(\d+)", filtered)})


def kill_process(pid: int) -> bool:
    """Terminate ``pid``, reporting whether the request was accepted."""
    try:
        if WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=5,
                check=False,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def free_port(port: int) -> None:
    """Stop whatever listens on ``port`` and wait for the socket to actually close.

    The kernel releases a port when its process exits, so the wait matters:
    binding immediately after the signal can still race a listener that has not
    finished shutting down.
    """
    pids = find_pids_on_port(port)
    if not pids:
        return

    print(f"  端口 {port} 被进程 {', '.join(map(str, pids))} 占用，正在释放...")
    for pid in pids:
        command = _describe(pid)
        if command:
            print(f"    PID {pid}: {command}")
        if kill_process(pid):
            print(f"  已终止进程 {pid}")
        else:
            print(f"  无法终止进程 {pid}，请手动关闭")
            sys.exit(1)

    for _ in range(50):
        time.sleep(0.1)
        if not find_pids_on_port(port):
            return
    print(f"  端口 {port} 仍被占用，请手动关闭")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="AIFUND5 API 服务器")
    parser.add_argument("--port", type=int, default=8000, help="服务端口 (默认 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="绑定地址 (默认 127.0.0.1)")
    parser.add_argument("--kill", action="store_true", help="仅终止已有服务器进程")
    args = parser.parse_args()

    if args.kill:
        free_port(args.port)
        print(f"  端口 {args.port} 已释放")
        return

    free_port(args.port)

    import uvicorn
    print(f"  启动 AIFUND5 API 服务器 http://{args.host}:{args.port}")
    uvicorn.run("src.api.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
