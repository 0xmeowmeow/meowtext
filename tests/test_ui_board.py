"""The reference-board index serves only the pictures it discovered, and it keeps notes."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

from ui_board.server import discover, make_handler, open_board
from http.server import ThreadingHTTPServer


class BoardTests(unittest.TestCase):
    def test_discover_groups_a_folder_and_rejects_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inspo = root / "inspo"
            nested = inspo / "screens"
            nested.mkdir(parents=True)
            self._png(inspo / "wide.png")
            self._png(nested / "panel.png")
            (root / "notes.txt").write_text("no", encoding="utf-8")
            (root / "loose.png").write_bytes(b"no")
            collections, nodes = discover([str(root)])
            self.assertEqual(set(collections), {str(inspo)})
            self.assertEqual(collections[str(inspo)].subtree_images(), 2)
            self.assertEqual(len(nodes[str(inspo)].images), 1)
            self.assertEqual(len(nodes[str(nested)].images), 1)

    def test_notes_round_trip_and_closed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "tui-shots"
            folder.mkdir()
            image = folder / "screen.png"
            self._png(image)
            board = open_board(notes_path=root / "notes.json", roots=[str(root)], thumbs=root / "thumbs")
            handler = make_handler(board)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = httpd.server_address[1]
            try:
                base = f"http://127.0.0.1:{port}"
                collections = self._json(base + "/api/collections")
                self.assertEqual(collections["collections"][0]["name"], "tui-shots")
                self.assertEqual(collections["collections"][0]["kind"], "tui")
                payload = self._json(base + "/api/folder?p=" + urllib.parse.quote(str(folder)))
                self.assertEqual(payload["images"][0]["name"], "screen.png")
                saved = self._post(base + "/api/image", {
                    "path": str(image),
                    "include": True,
                    "note": "Keep the status on one line",
                })
                self.assertEqual(saved["entry"]["note"], "Keep the status on one line")
                notes = self._json(base + "/api/notes")
                self.assertTrue(notes["images"][str(image)]["include"])
                self._post(base + "/api/folder", {"path": str(folder), "note": "Density like this"})
                notes = self._json(base + "/api/notes")
                self.assertEqual(notes["folders"][str(folder)], "Density like this")
                with urllib.request.urlopen(base + "/thumb?p=" + urllib.parse.quote(str(image))) as thumb:
                    self.assertEqual(thumb.status, 200)
                    self.assertTrue(thumb.read().startswith(b"\xff\xd8"))
                with urllib.request.urlopen(base + "/g?p=" + urllib.parse.quote(str(folder))) as page:
                    self.assertIn(b"Reference boards", page.read())
                for blocked in ("/file?p=/etc/passwd", "/api/folder?p=/etc", "/thumb?p=" + urllib.parse.quote(str(root / "nope.png"))):
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(base + blocked)
                    self.assertEqual(caught.exception.code, 404)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def _png(self, path: Path) -> None:
        Image.new("RGB", (12, 8), (30, 40, 50)).save(path)

    def _json(self, url: str) -> dict:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
