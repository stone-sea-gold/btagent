"""AIFUND5 API server launcher.

Usage:
    python run_server.py              # Start on default port 8000
    python run_server.py --port 8001  # Start on custom port
    python run_server.py --kill       # Kill running server and exit

Automatically kills any existing process occupying the port before starting.
"""

import argparse
import subprocess
import sys


def find_pid_on_port(port: int) -> int | None:
    """Find the PID of the process listening on the given port."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                if pid > 0:
                    return pid
    except Exception:
        pass
    return None


def kill_process(pid: int) -> bool:
    """Kill a process by PID."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, timeout=5,
        )
        return True
    except Exception:
        return False


def free_port(port: int) -> None:
    """Kill any process listening on the given port."""
    pid = find_pid_on_port(port)
    if pid is not None:
        print(f"  端口 {port} 被进程 PID {pid} 占用，正在释放...")
        if kill_process(pid):
            print(f"  已终止进程 {pid}")
        else:
            print(f"  无法终止进程 {pid}，请手动关闭")
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
