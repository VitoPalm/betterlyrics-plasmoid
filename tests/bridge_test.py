#!/usr/bin/env python3
"""Native messaging and Unix socket bridge contract tests."""

import json
import os
import select
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "bridge/native_host.py"
SERVICE = ROOT / "contents/ui/lyrics_service.py"


def read_exact(stream, count):
    data = b""
    while len(data) < count:
        data += stream.read(count - len(data))
    return data


class BridgeHostTests(unittest.TestCase):
    def test_service_receives_browser_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bridge.sock"
            env = dict(os.environ, BETTERLYRICS_BRIDGE_SOCKET=str(path), PYTHONDONTWRITEBYTECODE="1")
            host = subprocess.Popen([sys.executable, str(HOST)], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            service = None
            try:
                for _ in range(100):
                    if path.is_socket():
                        break
                    time.sleep(0.01)
                self.assertTrue(path.is_socket())
                service = subprocess.Popen([sys.executable, str(SERVICE), "--phase", "bridge",
                                            "--title", "Song", "--artist", "Artist",
                                            "--video-id", "dQw4w9WgXcQ", "--request-token", "test"],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                readable, _, _ = select.select([host.stdout], [], [], 5)
                self.assertTrue(readable)
                length = struct.unpack("<I", read_exact(host.stdout, 4))[0]
                request = json.loads(read_exact(host.stdout, length))
                result = {"type": "result", "id": request["id"], "result": {
                    "playbackVideoId": "dQw4w9WgXcQ", "provider": "unison-synced",
                    "source": "Unison", "lyrics": [{"startTimeMs": 1000, "durationMs": 2000,
                                                      "words": "Hello"}]}}
                encoded = json.dumps(result).encode()
                host.stdin.write(struct.pack("<I", len(encoded)) + encoded)
                host.stdin.flush()
                stdout, stderr = service.communicate(timeout=5)
                self.assertEqual(service.returncode, 0, stderr.decode())
                payload = json.loads(stdout)
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["requestToken"], "test")
                self.assertEqual(payload["result"]["provider"], "unison-synced")
                self.assertEqual(payload["result"]["lines"][0]["words"], "Hello")
            finally:
                if service and service.poll() is None:
                    service.kill()
                    service.wait()
                host.stdin.close()
                host.wait(timeout=3)
                host.stdout.close()
                host.stderr.close()

    def test_request_result_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bridge.sock"
            env = dict(os.environ, BETTERLYRICS_BRIDGE_SOCKET=str(path))
            process = subprocess.Popen([sys.executable, str(HOST)], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            try:
                for _ in range(100):
                    if path.is_socket():
                        break
                    time.sleep(0.01)
                self.assertTrue(path.is_socket())
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(3)
                    client.connect(str(path))
                    client.sendall(b'{"videoId":"dQw4w9WgXcQ","title":"Song"}\n')
                    readable, _, _ = select.select([process.stdout], [], [], 3)
                    self.assertTrue(readable)
                    length = struct.unpack("<I", read_exact(process.stdout, 4))[0]
                    request = json.loads(read_exact(process.stdout, length))
                    self.assertEqual((request["type"], request["videoId"]), ("fetch", "dQw4w9WgXcQ"))
                    result = {"type": "result", "id": request["id"], "result": {
                        "playbackVideoId": "dQw4w9WgXcQ", "provider": "yt-lyrics", "lyrics": []}}
                    encoded = json.dumps(result).encode()
                    process.stdin.write(struct.pack("<I", len(encoded)) + encoded)
                    process.stdin.flush()
                    response = json.loads(client.makefile("rb").readline())
                    self.assertTrue(response["ok"])
                    self.assertEqual(response["result"]["provider"], "yt-lyrics")
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(3)
                    client.connect(str(path))
                    client.sendall(b'{"videoId":"invalid"}\n')
                    self.assertFalse(json.loads(client.makefile("rb").readline())["ok"])
            finally:
                process.stdin.close()
                process.wait(timeout=3)
                process.stdout.close()
                process.stderr.close()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
