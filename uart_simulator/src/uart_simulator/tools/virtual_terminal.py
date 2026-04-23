from __future__ import annotations

import argparse
import selectors
import socket
import sys
import threading
import time


def _log(msg: str) -> None:
    print(f"[vterm] {msg}")


class PairBridge:
    def __init__(self, left_port: int, right_port: int) -> None:
        self.left_port = left_port
        self.right_port = right_port
        self.sel = selectors.DefaultSelector()
        self.left_client: socket.socket | None = None
        self.right_client: socket.socket | None = None

    def _listen(self, port: int) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.listen(1)
        s.setblocking(False)
        return s

    def run(self) -> None:
        left_srv = self._listen(self.left_port)
        right_srv = self._listen(self.right_port)
        self.sel.register(left_srv, selectors.EVENT_READ, data=("accept", "left"))
        self.sel.register(right_srv, selectors.EVENT_READ, data=("accept", "right"))

        _log(f"pair ready: left=127.0.0.1:{self.left_port} right=127.0.0.1:{self.right_port}")
        _log("connect one client to each side; bytes will be bridged bidirectionally")

        try:
            while True:
                for key, _mask in self.sel.select(timeout=0.1):
                    kind, side = key.data
                    if kind == "accept":
                        self._accept(key.fileobj, side)
                    elif kind == "io":
                        self._relay(key.fileobj, side)
        except KeyboardInterrupt:
            _log("stopped")
        finally:
            self.sel.close()
            left_srv.close()
            right_srv.close()
            if self.left_client:
                self.left_client.close()
            if self.right_client:
                self.right_client.close()

    def _accept(self, server_sock: socket.socket, side: str) -> None:
        client, addr = server_sock.accept()
        client.setblocking(False)

        if side == "left":
            if self.left_client is not None:
                _log("left side already connected; rejecting extra client")
                client.close()
                return
            self.left_client = client
            self.sel.register(client, selectors.EVENT_READ, data=("io", "left"))
            _log(f"left connected from {addr}")
            return

        if self.right_client is not None:
            _log("right side already connected; rejecting extra client")
            client.close()
            return
        self.right_client = client
        self.sel.register(client, selectors.EVENT_READ, data=("io", "right"))
        _log(f"right connected from {addr}")

    def _relay(self, src: socket.socket, side: str) -> None:
        try:
            chunk = src.recv(4096)
        except OSError:
            chunk = b""

        if not chunk:
            _log(f"{side} disconnected")
            try:
                self.sel.unregister(src)
            except Exception:
                pass
            src.close()
            if side == "left":
                self.left_client = None
            else:
                self.right_client = None
            return

        dst = self.right_client if side == "left" else self.left_client
        if dst is None:
            return

        try:
            dst.sendall(chunk)
            preview = chunk[:32]
            _log(f"{side}->other {len(chunk)}B hex={preview.hex()}")
        except OSError:
            pass


def run_terminal(host: str, port: int, encoding: str) -> None:
    sock = socket.create_connection((host, port), timeout=5)
    sock.settimeout(0.2)
    _log(f"connected to {host}:{port} as interactive terminal")
    _log("type lines to send; Ctrl+C to quit")

    def reader() -> None:
        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            try:
                text = data.decode(encoding, errors="replace")
            except Exception:
                text = repr(data)
            sys.stdout.write(f"\n[rx] {text}\n> ")
            sys.stdout.flush()

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    try:
        while True:
            line = input("> ")
            payload = (line + "\n").encode(encoding, errors="replace")
            sock.sendall(payload)
    except KeyboardInterrupt:
        _log("terminal stopped")
    finally:
        sock.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Free Python virtual terminal tools (TCP pair and interactive terminal)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pair = sub.add_parser("pair", help="Create a free virtual terminal pair over localhost TCP")
    pair.add_argument("--left-port", type=int, default=7001, help="Left endpoint TCP port")
    pair.add_argument("--right-port", type=int, default=7002, help="Right endpoint TCP port")

    term = sub.add_parser("term", help="Interactive terminal client")
    term.add_argument("--host", default="127.0.0.1", help="Host")
    term.add_argument("--port", type=int, required=True, help="Port")
    term.add_argument("--encoding", default="utf-8", help="Display/send encoding")

    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.cmd == "pair":
        PairBridge(args.left_port, args.right_port).run()
        return
    if args.cmd == "term":
        run_terminal(args.host, args.port, args.encoding)


if __name__ == "__main__":
    main()
