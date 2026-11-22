"""NAM / IR library for melon-pedald.

Melon NAM and Melon Cab (melon_plugins >= the "library index" change) choose their file with
an integer parameter:

    https://github.com/melon-audio/melon-nam:model_index   -> a file in /data/media/NAM
    https://github.com/melon-audio/melon-cab:ir_index      -> a file in /data/media/IR

    -1 = no file, 0..65535 = position in the list below, past the end = no file.

The list MUST match the plugins' (shared/MelonLibraryScan.h): every file under the folder,
all sub-folders, extension in the set (case-insensitive), nothing whose name or any parent
folder's name starts with "." , relative paths with "/" sorted by their UTF-8 bytes.

Presets store the RELATIVE PATH (e.g. "Marshall/JCM800/Crunch.nam"), never the index, and
turn it into the index when the preset is loaded, so adding files never breaks a preset.

A host only sends a parameter *change*: to reload the same index after the library changed
(e.g. a USB import), send -1 first, then the index.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MEDIA_ROOT = Path(os.environ.get("MELON_MEDIA_DIR", "/data/media"))

NAM_EXTS = frozenset({"nam", "aidax", "json"})
IR_EXTS = frozenset({"wav", "aif", "aiff", "flac"})

NAM_PARAM = "https://github.com/melon-audio/melon-nam:model_index"
IR_PARAM = "https://github.com/melon-audio/melon-cab:ir_index"

NONE = -1
MAX_INDEX = 65535


def scan(root: Path, exts: frozenset[str]) -> list[str]:
    """Relative paths, in the plugins' order (see module docstring)."""
    out: list[bytes] = []
    root_b = os.fsencode(root)
    if not os.path.isdir(root_b):
        return []
    for dirpath, dirnames, filenames in os.walk(root_b, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(b".")]  # skip hidden folders
        for name in filenames:
            if name.startswith(b"."):
                continue
            _, ext = os.path.splitext(name)
            if ext[1:].lower().decode("utf-8", "replace") not in exts:
                continue
            full = os.path.join(dirpath, name)
            if not os.path.isfile(full):  # regular file (or symlink to one)
                continue
            out.append(os.path.relpath(full, root_b).replace(os.sep.encode(), b"/"))
    out.sort()  # bytes compare = UTF-8 byte order, same as std::string in C++
    return [os.fsdecode(p) for p in out]


@dataclass
class Library:
    """One library (NAM or IR). Call refresh() at start and whenever the folder changes."""

    root: Path
    exts: frozenset[str]
    files: list[str] = field(default_factory=list)
    _index: dict[str, int] = field(default_factory=dict, repr=False)

    def refresh(self) -> None:
        self.files = scan(self.root, self.exts)
        self._index = {p: i for i, p in enumerate(self.files)}

    def index_of(self, rel_path: str | None) -> int:
        """Preset path -> parameter value (NONE if empty or no longer in the library)."""
        if not rel_path:
            return NONE
        i = self._index.get(rel_path.replace("\\", "/"), NONE)
        return i if i <= MAX_INDEX else NONE

    def path_at(self, index: int) -> str | None:
        return self.files[index] if 0 <= index < len(self.files) else None

    # --- browsing by folder (LCD / app) -------------------------------------------------
    def list_folder(self, folder: str = "") -> tuple[list[str], list[str]]:
        """Sub-folders and files directly inside `folder` ("" = top), both sorted."""
        prefix = folder.strip("/") + "/" if folder.strip("/") else ""
        dirs: set[str] = set()
        files: list[str] = []
        for p in self.files:
            if not p.startswith(prefix):
                continue
            rest = p[len(prefix):]
            if "/" in rest:
                dirs.add(rest.split("/", 1)[0])
            else:
                files.append(rest)
        return sorted(dirs, key=str.casefold), files


# parameter short id -> library folder name (see Pedal.lib_of)
LIB_PARAMS = {"model_index": "NAM", "ir_index": "IR"}


def libraries() -> dict[str, Library]:
    """{"NAM": Library, "IR": Library}, scanned once; call refresh() to pick up new files."""
    libs = {"NAM": Library(MEDIA_ROOT / "NAM", NAM_EXTS), "IR": Library(MEDIA_ROOT / "IR", IR_EXTS)}
    for lib in libs.values():
        lib.refresh()
    return libs


def title(rel_path: str | None) -> str:
    """'CELESTION/G12/V30 SM57.wav' -> 'V30 SM57' (what the LCD shows)."""
    if not rel_path:
        return "None"
    name = rel_path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def folder_of(rel_path: str | None) -> str:
    return rel_path.rsplit("/", 1)[0] if rel_path and "/" in rel_path else ""


def nam_library() -> Library:
    lib = Library(MEDIA_ROOT / "NAM", NAM_EXTS)
    lib.refresh()
    return lib


def ir_library() -> Library:
    lib = Library(MEDIA_ROOT / "IR", IR_EXTS)
    lib.refresh()
    return lib


if __name__ == "__main__":
    # Prints the list like shared/tests/test_library_scan <folder>, to compare both:
    #   python3 library.py /data/media/IR > py.txt ; ./test_library_scan /data/media/IR > cpp.txt ; diff py.txt cpp.txt
    import sys

    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else MEDIA_ROOT / "IR"
    exts = NAM_EXTS if folder.name.upper() == "NAM" else IR_EXTS
    for p in scan(folder, exts):
        print(p)
