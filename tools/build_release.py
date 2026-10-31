"""
販売・配布用の zip を作る。

    python tools/build_release.py

dist/ に次の2つができる:
  LocaTester-<version>-full.zip   製品版（販売用）
  LocaTester-<version>-check.zip  動作チェック版（無料配布用。位置は変更できない）
"""
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "gps-simulator"
DIST = ROOT / "dist"
TOP = "LocaTester"
# 著作権者名（GPL v3 第4条: 各複製に適切な著作権表示が必要）。出品前に自分の名前に変える
COPYRIGHT_HOLDER = "penmawashi8-ux"

EXCLUDE_DIRS = {"venv", "__pycache__"}
EXCLUDE_FILES = {"edition.txt", "diagnose.txt", ".gitignore"}
EXCLUDE_SUFFIXES = {".log", ".pyc"}
# 動作チェック版には位置を変更するスクリプトを入れない
CHECK_EXCLUDE = {"hold_location.py"}

LICENSE_NOTE = """LocaTester
Copyright (C) 2026 {holder}

このソフトウェアは GNU General Public License v3.0（GPL-3.0）で配布しています。
全文は同梱の LICENSE を参照してください。

- この zip にはソースコードが含まれています（GPL のソースコード提供義務を満たしています）。
- GPL-3.0 の条件の範囲で、複製・改変・再配布ができます。
- 本ソフトウェアは無保証です（GPL-3.0 第15条・第16条）。

使用しているオープンソースソフトウェア:
- pymobiledevice3 (GPL-3.0-or-later) https://github.com/doronz88/pymobiledevice3
- FastAPI (MIT), Uvicorn (BSD-3-Clause), Leaflet (BSD-2-Clause)
- 地図データ: © OpenStreetMap contributors (ODbL)
"""


def app_version() -> str:
    m = re.search(r'APP_VERSION = "([^"]+)"', (SRC / "main.py").read_text(encoding="utf-8"))
    return m.group(1)


def source_files():
    for p in sorted(SRC.rglob("*")):
        rel = p.relative_to(SRC)
        if p.is_dir() or set(rel.parts) & EXCLUDE_DIRS:
            continue
        if p.name in EXCLUDE_FILES or p.suffix in EXCLUDE_SUFFIXES:
            continue
        yield p, rel


def build(edition: str, version: str) -> Path:
    DIST.mkdir(exist_ok=True)
    out = DIST / f"{TOP}-{version}-{edition}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p, rel in source_files():
            if edition == "check" and p.name in CHECK_EXCLUDE:
                continue
            z.write(p, f"{TOP}/{rel.as_posix()}")
        z.write(ROOT / "LICENSE", f"{TOP}/LICENSE")
        # メモ帳で文字化けしないよう BOM 付き UTF-8・CRLF にする
        note = LICENSE_NOTE.format(holder=COPYRIGHT_HOLDER).replace("\n", "\r\n")
        z.writestr(f"{TOP}/LICENSE-ja.txt", note.encode("utf-8-sig"))
        if edition == "check":
            z.writestr(f"{TOP}/edition.txt", "check\n")
    return out


def main():
    if COPYRIGHT_HOLDER.startswith("（"):
        print("警告: tools/build_release.py の COPYRIGHT_HOLDER を自分の名前に変えてください")
    version = app_version()
    for edition in ("full", "check"):
        out = build(edition, version)
        with zipfile.ZipFile(out) as z:
            print(f"{out.relative_to(ROOT)}  ({len(z.namelist())} files)")


if __name__ == "__main__":
    main()
