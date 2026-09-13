KOOLKID MT5 DROP-IN v4.2

1. Copy mt5_bot/, mt5_bridge/, mt5_web.py, SETUP_MT5_BRIDGE.bat and START_MT5_BRIDGE.bat into the ROOT of the existing deriv-bot-site project.
2. Give Codex the project and paste CODEX_MERGE_PROMPT.txt.
3. Codex should read MT5_MERGE_INSTRUCTIONS.md and make only the tiny integration edits.
4. Keep mt5_bridge requirements separate from the main Deriv requirements.
5. Real MT5 bridge is Windows-only; do not force it into a Linux/Render web process.
