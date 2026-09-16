"""Guards on what the distribution contains.

Packaging facts have no other test: the suite imports from the source tree, so
everything here passes whether or not the built artifact is correct. These
assertions stand in for the check nobody runs before a release.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "src" / "dialectical_framework"


class TestInlineTypesReachIntegrators:
    def test_the_py_typed_marker_ships(self):
        """PEP 561: no marker, no types — for everyone outside this repo.

        A type checker must IGNORE a distributed package's inline annotations
        unless this file ships inside the package, so deleting it silently
        downgrades `Advisor` to `Any` in every integrator's checker while every
        test here stays green. That is why the guard is an explicit assertion
        rather than a comment on the file.
        """
        marker = PACKAGE_ROOT / "py.typed"
        assert marker.is_file(), (
            "src/dialectical_framework/py.typed is missing — the package's type "
            "hints stop being visible to integrators (PEP 561)."
        )

    def test_it_is_inside_the_distributed_package(self):
        """Next to the code, not at the repo root.

        The marker is only meaningful in the directory that gets installed. A
        copy at the repo root looks right in a listing and ships nowhere.
        """
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
        packages = pyproject["tool"]["poetry"]["packages"]
        assert [
            p for p in packages if p["include"] == "dialectical_framework"
        ], "the package Poetry ships was renamed; the marker has to move with it"
        assert not (REPO_ROOT / "py.typed").exists(), (
            "a py.typed at the repo root is not distributed and gives false "
            "confidence"
        )
