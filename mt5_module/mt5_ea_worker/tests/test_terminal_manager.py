from pathlib import Path

from mt5_ea_worker import terminal_manager


def test_dedicated_terminal_skips_live_runtime_caches(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "terminal64.exe").write_bytes(b"terminal")
    (source / "Bases").mkdir()
    (source / "Bases" / "locked.hcc").write_bytes(b"history")
    (source / "logs").mkdir()
    (source / "logs" / "old.log").write_text("old", encoding="utf-8")
    (source / "MQL5").mkdir()
    (source / "MQL5" / "Experts").mkdir()
    (source / "MQL5" / "Experts" / "keep.ex5").write_bytes(b"EX5")
    source_data = tmp_path / "data"
    (source_data / "config").mkdir(parents=True)
    (source_data / "config" / "accounts.dat").write_bytes(b"account")
    monkeypatch.setattr(terminal_manager, "TERMINAL_ROOT", tmp_path / "targets")

    terminal, data_dir = terminal_manager.prepare_dedicated_terminal(
        str(source / "terminal64.exe"), str(source_data), "diag",
    )

    assert terminal.is_file()
    assert (data_dir / "MQL5" / "Experts" / "keep.ex5").is_file()
    assert not (data_dir / "Bases").exists()
    assert not (data_dir / "logs").exists()
    assert (data_dir / "Config" / "accounts.dat").read_bytes() == b"account"
