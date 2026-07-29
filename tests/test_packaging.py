"""Metadata limits PyPI enforces at upload time, checked before we get there.

`twine check` validates that the README renders; it does *not* check the
core-metadata length limits. A 36-character `[project.urls]` label sailed
through the build, through `twine check`, and was only rejected by PyPI itself
with a 400 after a release had already been cut. These assertions move that
failure to the test suite, where it costs seconds instead of a version number.
"""

from __future__ import annotations

from pathlib import Path

import pytest

tomllib = pytest.importorskip(
    "tomllib", reason="tomllib is 3.11+; the metadata check runs on newer runtimes"
)

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# https://packaging.python.org/specifications/core-metadata
# Project-URL labels are limited to 32 characters.
_MAX_URL_LABEL = 32


@pytest.fixture(scope="module")
def project():
    with open(PYPROJECT, "rb") as handle:
        return tomllib.load(handle)["project"]


def test_url_labels_fit_pypi_limit(project):
    too_long = {
        label: len(label)
        for label in project.get("urls", {})
        if len(label) > _MAX_URL_LABEL
    }
    assert not too_long, (
        f"PyPI rejects Project-URL labels over {_MAX_URL_LABEL} characters: {too_long}"
    )


def test_version_matches_the_package(project):
    from ossie_guard import __version__

    assert project["version"] == __version__


def test_required_metadata_is_present(project):
    for field in ("name", "version", "description", "readme", "license"):
        assert project.get(field), f"missing {field}"
    # A summary over 512 characters is also rejected at upload.
    assert len(project["description"]) <= 512
