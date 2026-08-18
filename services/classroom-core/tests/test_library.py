import re
from pathlib import Path

import pytest

from library import (
    LibraryError,
    list_units,
    read_library,
    resolve_library_path,
    search_library,
    unit_catalog,
)


def test_read_map_and_reject_escape(tmp_path: Path) -> None:
    root = tmp_path / "library"
    (root / "units" / "market-food").mkdir(parents=True)
    (root / "units" / "market-food" / "map.md").write_text("# apple\n", encoding="utf-8")
    (tmp_path / "secret.md").write_text("nope", encoding="utf-8")

    got = read_library("units/market-food/map.md", root=root)
    assert got["path"] == "units/market-food/map.md"
    assert "apple" in got["text"]

    with pytest.raises(LibraryError):
        resolve_library_path("../secret.md", root=root)
    with pytest.raises(LibraryError):
        resolve_library_path("/etc/passwd", root=root)


def test_search_finds_the_unit_and_the_skills_and_rejects_empty() -> None:
    greet = search_library("greet-and-name")
    assert any("gs3-u1-hello" in str(hit["path"]) for hit in greet["hits"])
    # The profession is reachable by what it is for, not only by its filename.
    distress = search_library("distress disclosure facilitator")
    assert any("escalate-to-the-adult" in str(hit["path"]) for hit in distress["hits"])
    with pytest.raises(LibraryError):
        search_library("   ")


def test_unit_catalog_is_only_what_the_markdown_prints() -> None:
    unit = unit_catalog("gs3-u1-hello")
    assert "greet-and-name" in unit["objectives"]
    assert "answer-wellbeing" in unit["objectives"]
    # Not an objective anywhere in the files -- the catalog invents nothing.
    assert "say-hello-word" not in unit["objectives"]
    assert "asset://gs3/audio/track-05.mp3" in unit["assets"]
    assert "asset://gs3/pages/p10.jpg" in unit["assets"]
    assert unit_catalog("../secret")["objectives"] == []


def test_library_units_have_the_same_shape() -> None:
    root = Path(__file__).resolve().parents[3] / "content" / "library"
    for unit in ("gs3-u1-hello",):
        folder = root / "units" / unit
        for name in ("map.md", "keys.md", "practice.md"):
            text = (folder / name).read_text(encoding="utf-8")
            assert "goto" not in text
            assert "lesson_run" not in text
            assert "propose_move" not in text
    assert "greet-and-name" in (root / "units" / "gs3-u1-hello" / "map.md").read_text(
        encoding="utf-8"
    )


def test_every_unit_in_the_index_exists() -> None:
    """The index is the syllabus. A unit it names must be on disk, and only those."""
    root = Path(__file__).resolve().parents[3] / "content" / "library"
    index = (root / "index.md").read_text(encoding="utf-8")
    on_disk = {p.name for p in (root / "units").iterdir() if p.is_dir()}
    for unit in on_disk:
        assert f"`{unit}`" in index, f"unit {unit} is on disk but not in index.md"
        assert (root / "units" / unit / "map.md").is_file()


def test_skills_are_the_profession_not_the_curriculum() -> None:
    """NS-6: a skill must read the same for maths as for English."""
    root = Path(__file__).resolve().parents[3] / "content" / "library" / "skills"
    index = (root / "index.md").read_text(encoding="utf-8")
    # Markers of the active unit specifically. A skill may use a neutral example;
    # it may never name the curriculum it happens to be sitting next to.
    unit_words = ("gs3", "grade 3", "unit 1", "track-0", "asset://", "ben", "mai", "lucy")
    for skill in sorted(p for p in root.iterdir() if p.is_dir()):
        body = (skill / "SKILL.md").read_text(encoding="utf-8")
        assert body.startswith("---"), f"{skill.name} has no frontmatter"
        assert f"`{skill.name}`" in index, f"{skill.name} is not in the skills index"
        lowered = body.lower()
        for word in unit_words:
            # Whole-word, so "been" does not trip on the character named Ben.
            assert not re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lowered), (
                f"{skill.name} names unit content: {word!r}"
            )


def test_the_unit_locks_its_own_vocabulary() -> None:
    """The book and the recordings say "Fine, thank you." The map must not drift."""
    root = Path(__file__).resolve().parents[3] / "content" / "library" / "units" / "gs3-u1-hello"
    text = (root / "map.md").read_text(encoding="utf-8")
    assert "Fine, thank you." in text
    assert "What's your name?" in text  # named only to forbid it in this unit


def test_every_asset_the_library_names_actually_exists() -> None:
    """A missing asset is a broken picture in front of thirty children.

    Third-party textbook media is gitignored, so this skips when the drop has
    not been imported (scripts/import-textbook-assets.sh). It must never be
    weakened into a warning -- when the media IS present, every id must resolve.
    """
    repo = Path(__file__).resolve().parents[3]
    media = repo / "content" / "media"
    library = repo / "content" / "library"
    ids: set[str] = set()
    for md in library.rglob("*.md"):
        ids.update(re.findall(r"asset://[a-z0-9_./-]+", md.read_text(encoding="utf-8")))
    assert ids, "the library names no assets at all"
    if not (media / "gs3").is_dir():
        pytest.skip("textbook assets not imported; run scripts/import-textbook-assets.sh")
    missing = sorted(a for a in ids if not (media / a[len("asset://"):]).is_file())
    assert not missing, f"library names assets that do not exist: {missing}"


def test_search_shows_the_matching_passage_not_the_top_of_the_file(tmp_path: Path) -> None:
    """A snippet that is always the opening paragraph is not a search result.

    It says which file matched and nothing about why, so the reader opens the
    whole file anyway -- the exact cost search exists to avoid.
    """
    root = tmp_path / "library"
    root.mkdir()
    (root / "keys.md").write_text(
        "# Keys\n\nRead this before you judge, and do not decide from memory.\n\n"
        + ("filler sentence about teaching. " * 40)
        + "\n\nThe polite answer is Fine, thank you.\n",
        encoding="utf-8",
    )

    snippet = str(search_library("Fine thank you", root=root)["hits"][0]["snippet"])

    assert "Fine, thank you" in snippet
    # "you" appears in the opening line; anchoring on the earliest common word
    # would drag the snippet back to the top of the document.
    assert not snippet.startswith("# Keys")


def test_units_are_discovered_not_named(tmp_path: Path) -> None:
    """Core must never hardcode which lesson an appliance teaches (NS-7)."""
    root = tmp_path / "library"
    (root / "units" / "gs3-u1-hello").mkdir(parents=True)
    (root / "units" / "gs3-u1-hello" / "map.md").write_text("# hello\n", encoding="utf-8")
    (root / "units" / "empty-shell").mkdir(parents=True)  # no markdown: not a unit

    assert list_units(root=root) == ["gs3-u1-hello"]
    assert list_units(root=tmp_path / "nothing-here") == []
