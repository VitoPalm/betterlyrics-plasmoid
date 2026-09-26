#!/usr/bin/env python3
"""Firefox native messaging host for the optional Better Lyrics bridge.

The browser owns the native port. A local client sends one request over a
private Unix socket; the host forwards it to the extension and returns one
response. Lyrics and credentials are never written to disk.
"""

from __future__ import annotations

import json
import os
import re
import selectors
import socket
import stat
import struct
import sys
import time
import uuid
from pathlib import Path


MAX_MESSAGE = 1_000_000
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
REQUEST_TIMEOUT = 58


def socket_path() -> Path:
    override = os.environ.get("BETTERLYRICS_BRIDGE_SOCKET")
    if override:
        return Path(override)
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "betterlyrics-plasmoid-bridge" / "bridge.sock"


def read_exact(stream, count: int) -> bytes:
    chunks = []
    while count:
        chunk = stream.read(count)
        if not chunk:
            raise EOFError
        chunks.append(chunk)
        count -= len(chunk)
    return b"".join(chunks)


def read_native(stream):
    header = read_exact(stream, 4)
    size = struct.unpack("<I", header)[0]
    if size > MAX_MESSAGE:
        raise ValueError("native message too large")
    value = json.loads(read_exact(stream, size))
    return value if isinstance(value, dict) else None


def write_native(stream, value):
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    if len(payload) > MAX_MESSAGE:
        raise ValueError("native message too large")
    stream.write(struct.pack("<I", len(payload)) + payload)
    stream.flush()


def send_client(client: socket.socket, value):
    try:
        client.sendall(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
    except OSError:
        pass
    finally:
        client.close()


def validate_request(value):
    if not isinstance(value, dict) or not VIDEO_ID.fullmatch(str(value.get("videoId", ""))):
        return None
    return {
        "videoId": value["videoId"],
        "title": str(value.get("title") or "")[:300],
        "artist": str(value.get("artist") or "")[:300],
        "album": str(value.get("album") or "")[:300],
        "duration": max(0, min(86400, float(value.get("duration") or 0))),
    }


def read_client_request(client: socket.socket):
    raw = b""
    while len(raw) <= 16384 and not raw.endswith(b"\n"):
        chunk = client.recv(min(4096, 16385 - len(raw)))
        if not chunk:
            break
        raw += chunk
    return validate_request(json.loads(raw)) if raw.endswith(b"\n") and len(raw) <= 16384 else None


def prepare_socket(path: Path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.exists():
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError("bridge path is not a user-owned socket")
        probe = socket.socket(socket.AF_UNIX)
        try:
            probe.connect(str(path))
        except OSError:
            path.unlink()
        else:
            raise RuntimeError("bridge host already running")
        finally:
            probe.close()
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(path))
    os.chmod(path, 0o600)
    server.listen(8)
    return server


def serve(stream_in=None, stream_out=None, path=None):
    stream_in = stream_in or sys.stdin.buffer
    stream_out = stream_out or sys.stdout.buffer
    path = Path(path) if path else socket_path()
    server = prepare_socket(path)
    pending = {}
    selector = selectors.DefaultSelector()
    selector.register(server, selectors.EVENT_READ, "socket")
    selector.register(stream_in, selectors.EVENT_READ, "native")
    try:
        while True:
            for key, _ in selector.select(timeout=1):
                if key.data == "socket":
                    client, _ = server.accept()
                    client.settimeout(1)
                    try:
                        request = read_client_request(client)
                    except (ValueError, TypeError, OSError):
                        request = None
                    if request is None:
                        send_client(client, {"ok": False})
                        continue
                    request_id = uuid.uuid4().hex
                    pending[request_id] = (client, request["videoId"], time.monotonic())
                    write_native(stream_out, {"type": "fetch", "id": request_id, **request})
                else:
                    try:
                        message = read_native(stream_in)
                    except EOFError:
                        return
                    if not message or message.get("type") != "result":
                        continue
                    entry = pending.pop(message.get("id"), None)
                    if entry:
                        client, video_id, _ = entry
                        result = message.get("result")
                        if isinstance(result, dict) and result.get("playbackVideoId") == video_id:
                            send_client(client, {"ok": True, "result": result})
                        else:
                            send_client(client, {"ok": False})
            now = time.monotonic()
            for request_id, (client, _, started) in list(pending.items()):
                if now - started > REQUEST_TIMEOUT:
                    pending.pop(request_id, None)
                    send_client(client, {"ok": False})
    finally:
        for client, _, _ in pending.values():
            send_client(client, {"ok": False})
        selector.close()
        server.close()
        if path.exists() and stat.S_ISSOCK(path.lstat().st_mode):
            path.unlink()


if __name__ == "__main__":
    serve()
