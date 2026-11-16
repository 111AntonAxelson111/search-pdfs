import os
import time
import json
from pathlib import Path
from datetime import datetime

TARGET = Path(r"C:\Users\anton\Downloads\pdfs_ny")
LOG    = Path("log2.txt")
INTERVAL = 2.0


def snapshot(root: Path) -> dict:
    """Return {abs_path: (mtime, size)} for every file under root."""
    snap = {}
    if not root.exists():
        return snap
    for p in root.rglob("*"):
        try:
            if p.is_file():
                st = p.stat()
                snap[str(p)] = (st.st_mtime, st.st_size)
        except (OSError, PermissionError):
            continue
    return snap


def write_log(kind: str, path: str, ts: float, dt: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps([kind, path, ts, dt]) + "\n")


def main() -> None:
    print(f"watching: {TARGET}")
    print(f"logging : {LOG.resolve()}")
    prev = snapshot(TARGET)

    while True:
        time.sleep(INTERVAL)
        now = snapshot(TARGET)
        ts = time.time()
        dt = datetime.now().isoformat(timespec="seconds")

        added   = [p for p in now  if p not in prev]
        updated = [p for p in now  if p in prev and now[p] != prev[p]]

        if not added and not updated:
            write_log("nothing", "nothing", ts, dt)
        else:
            for p in added:
                write_log("added", p, ts, dt)
            for p in updated:
                write_log("updatad", p, ts, dt)   # keep your spelling

        prev = now


if __name__ == "__main__":
    main()