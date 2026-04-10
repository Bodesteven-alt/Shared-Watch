"""Minify docs/styles.css (rcssmin). Optionally minify docs/app.js via npx terser when Node/npm is available."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _minify_js_with_terser() -> bool:
    if not shutil.which("npx"):
        return False
    js_path = ROOT / "docs" / "app.js"
    src = js_path.read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".js",
        delete=False,
    ) as tmp:
        tmp.write(src)
        tmp_path = Path(tmp.name)
    out_path = tmp_path.with_suffix(".out.js")
    try:
        subprocess.run(
            [
                "npx",
                "--yes",
                "terser",
                str(tmp_path),
                "-c",
                "passes=2",
                "-m",
                "false",
                "-o",
                str(out_path),
            ],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        js_path.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        return True
    except (OSError, subprocess.CalledProcessError):
        return False
    finally:
        for p in (tmp_path, out_path):
            try:
                p.unlink()
            except OSError:
                pass


def main() -> int:
    try:
        from rcssmin import cssmin
    except ImportError as e:
        raise SystemExit("Install minify deps: pip install rcssmin\n" + str(e)) from e

    css_path = ROOT / "docs" / "styles.css"
    css_path.write_text(cssmin(css_path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    print("Minified docs/styles.css (rcssmin).")

    if _minify_js_with_terser():
        print("Minified docs/app.js (terser via npx).")
    else:
        print("Skipped docs/app.js (install Node.js and run again to minify with terser).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
