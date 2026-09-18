from pathlib import Path
root = Path(r'C:\Users\jjmje\Desktop\deriv-bot-site')
app = root/'mt5_module'/'mt5_multi_account'/'app.py'
text = app.read_text(encoding='utf-8')
old = '''    assistant_ini = target_dir / "config" / "assistant.ini"
    if assistant_ini.is_file():
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        raw = assistant_ini.read_bytes()
        encoding = "utf-16" if raw.startswith((b"\\xff\\xfe", b"\\xfe\\xff")) else "utf-8-sig"
        parser.read_string(raw.decode(encoding))
        changed = False
        for section in ("MCP.MetaEditor", "MCP.MetaTrader"):
            if parser.has_section(section) and parser.get(section, "Enable", fallback="0") != "0":
                parser.set(section, "Enable", "0")
                changed = True
        if changed:
            with assistant_ini.open("w", encoding=encoding) as handle:
                parser.write(handle, space_around_delimiters=False)
'''
new = '''    # Disable MetaTrader/MetaEditor MCP before the very first terminal start.
    # Fresh portable clones do not have assistant.ini yet; waiting for the file to
    # appear is too late because MT5 may already bind 22345/22346 and break IPC.
    config_dir = target_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    assistant_ini = config_dir / "assistant.ini"
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    encoding = "utf-8"
    if assistant_ini.is_file():
        raw = assistant_ini.read_bytes()
        encoding = "utf-16" if raw.startswith((b"\\xff\\xfe", b"\\xfe\\xff")) else "utf-8-sig"
        parser.read_string(raw.decode(encoding))
    for section in ("MCP.MetaEditor", "MCP.MetaTrader"):
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, "Enable", "0")
    if not parser.has_section("MCP.Custom"):
        parser.add_section("MCP.Custom")
    with assistant_ini.open("w", encoding=encoding) as handle:
        parser.write(handle, space_around_delimiters=False)
'''
if old not in text:
    raise SystemExit('assistant block not found')
text = text.replace(old, new, 1)
app.write_text(text, encoding='utf-8')
print('APP_ASSISTANT_PATCHED')
