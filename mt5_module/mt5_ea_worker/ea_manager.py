from __future__ import annotations

import shutil
from pathlib import Path


def install_files(data_dir: Path, bot_id: int, ea_source: Path, preset_source: Path | None) -> tuple[str, str | None]:
    if ea_source.suffix.lower() != ".ex5" or not ea_source.is_file():
        raise ValueError("Uploaded .ex5 file was not found.")
    expert_dir = data_dir / "MQL5" / "Experts" / "KOOLKID" / str(bot_id)
    expert_dir.mkdir(parents=True, exist_ok=True)
    ea_dest = expert_dir / ea_source.name
    shutil.copy2(ea_source, ea_dest)
    preset_name = None
    if preset_source:
        if preset_source.suffix.lower() != ".set" or not preset_source.is_file():
            raise ValueError("Selected .set preset was not found.")
        preset_dir = data_dir / "MQL5" / "Presets"
        preset_dir.mkdir(parents=True, exist_ok=True)
        preset_dest = preset_dir / preset_source.name
        shutil.copy2(preset_source, preset_dest)
        preset_name = preset_dest.name
    expert_name = str(Path("KOOLKID") / str(bot_id) / ea_dest.stem).replace("/", "\\")
    return expert_name, preset_name
