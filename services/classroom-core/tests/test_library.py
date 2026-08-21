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


def test_the_profession_names_no_language_and_no_subject() -> None:
    """NS-7: the deployment declares itself; software never names a language.

    `how-to-teach.md` is CONDUCT, which NS-6 calls portable across every
    subject, and `skills/` is the profession. Neither may name English,
    Vietnamese, or a subject -- a school in Laos teaching maths replaces
    `index.md` and adds unit files, and touches nothing here.

    Reviewed 2026-08-20 and found in breach in five places, the worst a
    verbatim child-facing script: *"I'm your AI English friend!"*. No test
    looked at `content/` at all -- `test_no_unit_pedagogy.py` scans three
    source files -- so the abstraction the same file already used ten lines
    further down had simply not been applied to the rest of it.

    `index.md` is exempt: naming the languages is precisely what it is for.
    """
    import re

    from library import LIBRARY_ROOT

    NAMED = ("english", "vietnamese", "maths", "mathematics", "h'mông", "hmong")
    files = [LIBRARY_ROOT / "how-to-teach.md", LIBRARY_ROOT / "skills" / "index.md"]
    files += sorted(LIBRARY_ROOT.glob("skills/*/SKILL.md"))

    offenders = []
    for path in files:
        body = path.read_text(encoding="utf-8").lower()
        for word in NAMED:
            if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", body):
                offenders.append(f"{path.relative_to(LIBRARY_ROOT)}: {word!r}")
    assert not offenders, (
        "the portable profession names a language or a subject: "
        + "; ".join(offenders)
        + ". Use target_language / school_language / home_language, which "
        "index.md declares and how-to-teach.md already uses."
    )


def test_the_deployment_is_the_only_place_that_names_a_language() -> None:
    """The other half of the same rule: `index.md` MUST name them, or the
    abstraction above points at nothing."""
    from library import LIBRARY_ROOT

    body = (LIBRARY_ROOT / "index.md").read_text(encoding="utf-8").lower()
    for field in ("home_language", "school_language", "target_language"):
        assert field in body, f"index.md must declare {field}"


def test_the_deployment_declares_its_own_day() -> None:
    """NS-7 lists `timetable` among the things a deployment declares, and until
    2026-08-20 nothing in the system knew what time a class was.

    Worse than missing: the nightly preparation -- the one job justified
    entirely by "nobody is waiting" -- ran on a hardcoded hour with the
    scheduler pinned to UTC. 03:00 UTC is ten in the morning in Hà Giang, in
    the middle of school. It had almost certainly never once run when it was
    meant to.
    """
    from library import timetable

    got = timetable()
    assert got["timezone"], "the appliance must know which clock it keeps"
    assert got["prepare_at"], "preparation needs an hour that is not hardcoded"
    assert ":" in got["prepare_at"]

    hour = int(got["prepare_at"].split(":")[0])
    assert 0 <= hour <= 6, (
        f"prepare_at is {got['prepare_at']} local -- preparation is only "
        "allowed to be slow because nobody is waiting, which stops being true "
        "once the building is open"
    )


def test_a_room_with_no_declared_day_still_runs(tmp_path) -> None:
    """A school that has not filled the timetable in is not a broken school.
    The room still opens when someone appears; it simply cannot know in advance
    that a class is coming."""
    from library import timetable

    (tmp_path / "index.md").write_text("# no timetable here\n", encoding="utf-8")
    got = timetable(root=tmp_path)
    assert got == {"timezone": None, "prepare_at": None, "periods": []}


def test_list_periods_reads_what_an_author_wrote() -> None:
    """The front door renders from this, so it must be the map's own words."""
    from library import list_periods

    periods = list_periods("gs3-u1-hello")
    assert [p["n"] for p in periods] == [1, 2, 3], "the map declares three periods"
    assert periods[0]["title"], "a period without a title is an unpressable card"
    # The ids are the map's, and they are the same ids record_evidence accepts.
    assert "greet-and-name" in periods[0]["objectives"]
    # Period 3 says "all of them, plus `hear-h-and-b`". Rendering only the id
    # would show the widest period in the unit as the narrowest one.
    assert "all of them" in periods[2]["inPlay"]


def test_list_periods_is_quiet_about_units_that_do_not_exist() -> None:
    """A dark front door beats a 500. Neither case is an error."""
    from library import list_periods

    assert list_periods("no-such-unit") == []
    assert list_periods("../../../etc") == []
    assert list_periods("") == []


def test_the_holding_lines_are_read_not_written() -> None:
    """The only text that becomes speech without the model in the loop.

    Which is the point -- they cover the wait FOR the model. So the rule they
    live under matters: Core may quote the curriculum, Core may never compose.
    These come out of the unit map verbatim, like an arrival line.
    """
    from library import holding_lines

    lines = holding_lines("gs3-u1-hello")
    assert lines, "the authored unit declares holding lines"
    # Verbatim, from the map, in the school's own language -- not composed.
    text = (
        Path(__file__).resolve().parents[3]
        / "content" / "library" / "units" / "gs3-u1-hello" / "map.md"
    ).read_text(encoding="utf-8")
    for line in lines:
        assert line in text, line

    # No header row, no table rule, no syllabus item from the neighbouring
    # tables -- putting a locked target-language phrase in a child's ear as
    # though the room had answered them is the failure this guards.
    assert "Say exactly" not in lines
    assert not any(set(line) <= {"-", " ", ":"} for line in lines)
    assert "Hello." not in lines and "Hi." not in lines

    # Short. One breath, or it is no longer covering a silence, it is adding to
    # one.
    for line in lines:
        assert len(line) <= 40, line


def test_a_unit_with_no_holding_table_simply_says_nothing() -> None:
    """Absence is a legal answer, and must not raise on a turn."""
    from library import holding_lines

    assert holding_lines("no-such-unit") == []
    assert holding_lines("../secret") == []
    assert holding_lines("") == []
