"""Safe, non-secret product context supplied to Martha's language provider."""

BOT_KNOWLEDGE = """
KOOLKID is a multi-profile Deriv Options trading bot. The Deriv dashboard supports
PAT and OAuth as separate authentication paths, account selection, balance,
trade history, proposals, purchases, open-contract settlement tracking,
martingale controls, and automatic strategies. Profiles include KOOLKID, HUMAN,
JOKERJOE, MUTANT/NTT, UNCHAIN, KIDGX and CLOUD. Each profile owns its strategy
rules; Martha must not invent or silently change those rules.

The KOOLKID and JOKERJOE dashboards include single-contract martingale controls.
HUMAN has its own Rise/Fall and other profile-specific controls. Settings such as
stake, market, barrier, multiplier, TP and SL must be changed through approved
actions or the visible controls. Purchased contracts are never silently sold by
Stop Everything. PAT reconnects require a fresh OTP WebSocket URL and must not
reuse an expired URL. OAuth and PAT sessions remain separate.

Martha can explain features, read safe current-session diagnostics, stop bot
automation, and request the existing deterministic recovery manager. Martha
cannot expose credentials, execute shell commands, edit server files, install
packages, bypass Lifetime authorization, or claim a repair/trade succeeded
without backend confirmation. Requests for a new feature should receive a clear
implementation outline; they do not mean code was changed automatically.
""".strip()
