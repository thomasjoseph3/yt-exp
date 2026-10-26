# Thoma Studio rules (always apply)

Read AGENTS.md at the project root before changing anything; it has the map, commands and rules.

- Run commands with `uv run thoma <command>`. Check visual changes with `uv run thoma preview assets/samples/short_rag.json short` and look at the PNGs.
- Never publish publicly or set publish.auto_publish to true unless the owner asks.
- Never copy wording, visuals, audio or code from the source channels (IBM Technology, ByteMonk, Fireship). They are topic and fact sources only.
- Don't change Thoma's drawing (assets/web/mascot.js) or the chosen voice unless the owner asks.
- Only Qoder or Claude write scripts (owner's rule); every LLM call goes through thoma/llm.py ask_json(). Gemini keys are for the voice only.
- Secrets live in .env and ~/.config/thoma-studio/. Never print or commit them.
