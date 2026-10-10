"""Serve the reference boards on localhost.

Run from the meowtext checkout::

    python3 -m ui_board

Pictures stay where they are. Include / leave-out and the notes are written
to ``ui_board/notes.json``.
"""

from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, UnidentifiedImageError

HERE = Path(__file__).resolve().parent
PAGE = HERE / "web" / "index.html"
NOTES_PATH = HERE / "notes.json"
THUMB_DIR = Path.home() / ".cache" / "meowtext" / "ui-board-thumbs"
SCAN_ROOTS = (
    str(Path.home() / "data/art"),
    str(Path.home() / "data/programming"),
    str(Path.home() / "data/personal"),
    str(Path.home() / "Pictures"),
    str(Path.home() / "Desktop"),
)
KEYS = ("tui", "inspo", "mood")
SKIP_DIRS = {
    ".git",
    "node_modules",
    "target",
    ".cache",
    "__pycache__",
    "incremental",
    ".fingerprint",
    "dist",
    ".venv",
    "venv",
}
EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif", ".tif", ".tiff"}

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")


class Node:
    def __init__(self, path: str) -> None:
        self.path = path
        self.name = os.path.basename(path) or path
        self.images: list[str] = []
        self.children: dict[str, Node] = {}

    def sorted_children(self) -> list[Node]:
        return sorted(self.children.values(), key=lambda node: node.name.casefold())

    def subtree_images(self) -> int:
        return len(self.images) + sum(child.subtree_images() for child in self.children.values())

    def subtree_folders(self) -> int:
        return len(self.children) + sum(child.subtree_folders() for child in self.children.values())

    def cover(self) -> str | None:
        if self.images:
            return self.images[0]
        for child in self.sorted_children():
            found = child.cover()
            if found:
                return found
        return None


def _name_matches(name: str) -> bool:
    folded = name.casefold()
    return any(key in folded for key in KEYS)


def _path_matches(path: str) -> bool:
    return any(_name_matches(part) for part in path.split(os.sep))


def kind_of(path: str) -> str:
    parts = [part.casefold() for part in path.split(os.sep)]
    if any("tui" in part for part in parts):
        return "tui"
    if any("mood" in part for part in parts):
        return "mood"
    return "inspo"


def collection_root(path: str) -> str | None:
    found = None
    current = path
    while current and current != os.sep:
        if _name_matches(os.path.basename(current)):
            found = current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return found


def discover(roots: tuple[str, ...] | list[str]) -> tuple[dict[str, Node], dict[str, Node]]:
    """Return ``(collections, nodes)`` for image folders under ``roots``."""

    images: list[str] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")]
            if not _path_matches(dirpath):
                continue
            for name in filenames:
                if os.path.splitext(name)[1].lower() in EXTS:
                    images.append(os.path.join(dirpath, name))

    collections: dict[str, Node] = {}
    nodes: dict[str, Node] = {}

    def ensure(path: str) -> Node:
        node = nodes.get(path)
        if node is None:
            node = Node(path)
            nodes[path] = node
        return node

    for image in images:
        folder = os.path.dirname(image)
        root = collection_root(folder)
        if root is None:
            continue
        parent = ensure(root)
        collections[root] = parent
        if folder != root:
            current = root
            relative = os.path.relpath(folder, root)
            for part in relative.split(os.sep):
                current = os.path.join(current, part)
                child = ensure(current)
                parent.children.setdefault(part, child)
                parent = child
        parent.images.append(image)

    for node in nodes.values():
        node.images.sort(key=lambda item: os.path.basename(item).casefold())
    return collections, nodes


class NoteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.images: dict[str, dict] = {}
        self.folders: dict[str, str] = {}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                loaded = {}
            images = loaded.get("images") if isinstance(loaded, dict) else None
            folders = loaded.get("folders") if isinstance(loaded, dict) else None
            if isinstance(images, dict):
                for key, value in images.items():
                    if isinstance(value, dict):
                        include = value.get("include")
                        note = value.get("note") if isinstance(value.get("note"), str) else ""
                        if include in (True, False) or note:
                            self.images[str(key)] = {
                                "include": include if include in (True, False) else None,
                                "note": note,
                            }
            if isinstance(folders, dict):
                self.folders = {str(key): value for key, value in folders.items() if isinstance(value, str) and value}

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "images": {key: dict(value) for key, value in self.images.items()},
                "folders": dict(self.folders),
            }

    def put_image(self, path: str, include: bool | None, note: str) -> dict | None:
        with self.lock:
            if include not in (True, False) and not note:
                self.images.pop(path, None)
                stored = None
            else:
                stored = {"include": include if include in (True, False) else None, "note": note}
                self.images[path] = stored
            self._write()
            return None if stored is None else dict(stored)

    def put_folder(self, path: str, note: str) -> str:
        with self.lock:
            if note:
                self.folders[path] = note
            else:
                self.folders.pop(path, None)
            self._write()
            return note

    def _write(self) -> None:
        payload = {
            "images": self.images,
            "folders": self.folders,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)


class Board:
    def __init__(self, collections: dict[str, Node], nodes: dict[str, Node], notes: NoteStore, thumbs: Path) -> None:
        self.collections = collections
        self.nodes = nodes
        self.notes = notes
        self.thumbs = thumbs
        self.images = {image for node in nodes.values() for image in node.images}
        self.thumbs.mkdir(parents=True, exist_ok=True)

    def under(self, root: str, path: str) -> bool:
        return path == root or path.startswith(root + os.sep)

    def collection_payload(self) -> dict:
        snap = self.notes.snapshot()
        cards = []
        for path, node in self.collections.items():
            included = sum(1 for image, entry in snap["images"].items() if entry.get("include") is True and self.under(path, image))
            noted = sum(
                1
                for image, entry in snap["images"].items()
                if entry.get("note") and self.under(path, image)
            )
            noted += sum(1 for folder, text in snap["folders"].items() if text and self.under(path, folder))
            cards.append(
                {
                    "path": path,
                    "name": node.name,
                    "kind": kind_of(path),
                    "place": os.path.relpath(os.path.dirname(path), str(Path.home())),
                    "images": node.subtree_images(),
                    "folders": node.subtree_folders(),
                    "cover": node.cover(),
                    "included": included,
                    "noted": noted,
                }
            )
        cards.sort(key=lambda card: (-card["images"], card["name"].casefold()))
        return {"collections": cards, "notes": snap}

    def folder_payload(self, path: str) -> dict | None:
        node = self.nodes.get(path)
        if node is None:
            return None
        snap = self.notes.snapshot()
        root = collection_root(path) or path
        crumbs = []
        current = root
        crumbs.append({"name": os.path.basename(root) or root, "path": root})
        if path != root:
            for part in os.path.relpath(path, root).split(os.sep):
                current = os.path.join(current, part)
                crumbs.append({"name": part, "path": current})
        children = []
        for child in node.sorted_children():
            children.append(
                {
                    "path": child.path,
                    "name": child.name,
                    "images": child.subtree_images(),
                    "folders": child.subtree_folders(),
                    "cover": child.cover(),
                }
            )
        images = []
        for image in node.images:
            entry = snap["images"].get(image, {})
            images.append(
                {
                    "path": image,
                    "name": os.path.basename(image),
                    "include": entry.get("include"),
                    "note": entry.get("note") or "",
                }
            )
        return {
            "path": path,
            "name": node.name,
            "kind": kind_of(path),
            "crumbs": crumbs,
            "folderNote": snap["folders"].get(path, ""),
            "children": children,
            "images": images,
        }

    def known_image(self, raw: str) -> str | None:
        path = os.path.normpath(raw)
        if path in self.images and os.path.isfile(path):
            return path
        return None

    def known_folder(self, raw: str) -> str | None:
        path = os.path.normpath(raw)
        if path in self.nodes:
            return path
        return None


def thumb_bytes(path: str, width: int, cache: Path) -> tuple[bytes, str]:
    stamp = os.stat(path).st_mtime_ns
    key = hashlib.sha1(f"{path}|{stamp}|{width}".encode()).hexdigest()
    dest = cache / f"{key}.jpg"
    if dest.is_file():
        return dest.read_bytes(), "image/jpeg"
    try:
        with Image.open(path) as opened:
            opened.seek(0)
            if opened.mode in {"RGBA", "LA"} or (opened.mode == "P" and "transparency" in opened.info):
                rgba = opened.convert("RGBA")
                sheet = Image.new("RGB", rgba.size, (16, 17, 20))
                sheet.paste(rgba, mask=rgba.getchannel("A"))
                frame = sheet
            else:
                frame = opened.convert("RGB")
            frame.thumbnail((width, width))
            buffer = io.BytesIO()
            frame.save(buffer, "JPEG", quality=72)
            data = buffer.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return Path(path).read_bytes(), mime
    temporary = dest.with_suffix(".jpg.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, dest)
    return data, "image/jpeg"


def make_handler(board: Board):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/brief", "/g"}:
                self._page(parsed)
                return
            if parsed.path == "/api/collections":
                self._json(200, board.collection_payload())
                return
            if parsed.path == "/api/notes":
                self._json(200, board.notes.snapshot())
                return
            query = parse_qs(parsed.query)
            raw = query.get("p", [""])[0]
            if parsed.path == "/api/folder":
                payload = board.folder_payload(os.path.normpath(raw))
                if payload is None:
                    self._json(404, {"error": "unknown folder"})
                    return
                self._json(200, payload)
                return
            image = board.known_image(raw)
            if image is None:
                self._send(404, "text/plain; charset=utf-8", b"not found")
                return
            if parsed.path == "/file":
                mime = mimetypes.guess_type(image)[0] or "application/octet-stream"
                self._send(200, mime, Path(image).read_bytes())
                return
            if parsed.path == "/thumb":
                try:
                    width = int(query.get("w", ["360"])[0])
                except ValueError:
                    width = 360
                width = max(64, min(640, width))
                data, mime = thumb_bytes(image, width, board.thumbs)
                self._send(200, mime, data, cache=True)
                return
            self._send(404, "text/plain; charset=utf-8", b"not found")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0") or 0)
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(400, {"error": "expected json"})
                return
            if not isinstance(payload, dict):
                self._json(400, {"error": "expected an object"})
                return
            raw = payload.get("path")
            if not isinstance(raw, str):
                self._json(400, {"error": "missing path"})
                return
            if parsed.path == "/api/image":
                image = board.known_image(raw)
                if image is None:
                    self._json(404, {"error": "unknown image"})
                    return
                include = payload.get("include")
                note = payload.get("note") if isinstance(payload.get("note"), str) else ""
                if include not in (True, False, None):
                    self._json(400, {"error": "include must be true, false, or null"})
                    return
                stored = board.notes.put_image(image, include, note.strip())
                self._json(200, {"path": image, "entry": stored})
                return
            if parsed.path == "/api/folder":
                folder = board.known_folder(raw)
                if folder is None:
                    self._json(404, {"error": "unknown folder"})
                    return
                note = payload.get("note") if isinstance(payload.get("note"), str) else ""
                stored = board.notes.put_folder(folder, note.strip())
                self._json(200, {"path": folder, "note": stored})
                return
            self._json(404, {"error": "unknown endpoint"})

        def _page(self, parsed) -> None:
            query = parse_qs(parsed.query)
            if parsed.path == "/g":
                raw = query.get("p", [""])[0]
                folder = board.folder_payload(os.path.normpath(raw)) if raw else None
                boot = {"page": "gallery", "folder": folder}
            elif parsed.path == "/brief":
                boot = {"page": "brief", "notes": board.notes.snapshot()}
            else:
                boot = board.collection_payload()
                boot["page"] = "index"
            blob = json.dumps(boot, ensure_ascii=False).replace("<", "\\u003c")
            body = PAGE.read_text(encoding="utf-8").replace("__BOOT__", blob, 1).encode("utf-8")
            self._send(200, "text/html; charset=utf-8", body)

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, "application/json; charset=utf-8", body)

        def _send(self, status: int, mime: str, body: bytes, cache: bool = False) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400" if cache else "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(board: Board, host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = make_handler(board)
    httpd = None
    bound = port
    for candidate in range(port, port + 10):
        try:
            httpd = ThreadingHTTPServer((host, candidate), handler)
            bound = candidate
            break
        except OSError:
            continue
    if httpd is None:
        raise SystemExit(f"no free port from {port} to {port + 9}")
    pictures = sum(node.subtree_images() for node in board.collections.values())
    print(f"Reference boards  http://{host}:{bound}/", flush=True)
    print(f"{len(board.collections)} boards, {pictures} pictures", flush=True)
    print(f"Notes  {board.notes.path}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()


def open_board(notes_path: Path | None = None, roots: tuple[str, ...] | list[str] = SCAN_ROOTS, thumbs: Path | None = None) -> Board:
    collections, nodes = discover(roots)
    return Board(collections, nodes, NoteStore(notes_path or NOTES_PATH), thumbs or THUMB_DIR)


def main() -> None:
    print("Indexing pictures…", flush=True)
    serve(open_board())
