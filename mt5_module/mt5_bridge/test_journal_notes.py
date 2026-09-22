from pathlib import Path

from mt5_module.mt5_bridge import journal_manager


def test_daily_journal_note_save_reload_and_clear(monkeypatch, tmp_path: Path):
    notes_file = tmp_path / "journal_notes.json"
    monkeypatch.setattr(journal_manager, "_notes_file", lambda: notes_file)

    saved = journal_manager.save_note("2026-09-22", "Wait for confirmation. Do not chase.")
    assert saved["note"] == "Wait for confirmation. Do not chase."
    assert journal_manager.note_for("2026-09-22") == saved["note"]

    cleared = journal_manager.save_note("2026-09-22", "   ")
    assert cleared["note"] == ""
    assert journal_manager.note_for("2026-09-22") == ""


def test_daily_summary_carries_note():
    day = journal_manager.date(2026, 9, 22)
    summary = journal_manager._daily_summary([], day, "Review patience.")
    assert summary["date"] == "2026-09-22"
    assert summary["note"] == "Review patience."
