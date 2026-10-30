---
name: writers-no-opus
description: "Who writes scripts: Qoder (free model while credits are out) then Gemini Flash; Claude Sonnet only checks; never Opus; save Claude limits"
metadata:
  type: feedback
---

Owner (2026-10-29): "never use opus to write scripts it is too technical, I need these videos understandable even for a 10th class student". Wants GPT/Gemini/Sonnet-class writers, Qoder doing the work, and Claude only validating so Claude's limits aren't used up.

**Why:** Opus scripts (the RAG vs OKF gold series) read as too technical for the audience; Claude usage is limited and the owner wants it spent on checking.
**How to apply:** config.yaml llm.roles: research/write/triage = [qoder, gemini], review = [claude (Sonnet), gemini]. The claude-opus provider was removed; don't add it back or use `--llm claude-opus`. Qoder's paid credits ran out on 2026-10-29 (`qodercli -p -m auto` says credits exhausted; plain `qodercli -p` still answers with its free model). When the owner tops up, add `"-m", "<model>"` to the qoder command (pick a GPT/Gemini/Sonnet-class model from `qodercli --list-models`, never Opus). Gemini text uses the free AI Studio key (Flash only; Pro has no free quota). Related: [[simple-language-required]], [[thoma-channel-project]].
- 2026-10-29 later: owner found the batch too slow. Writer order is now Gemini first, Qoder backup (Qoder still researches). Owner wants each video made one at a time: write -> Claude validates -> render -> Telegram, then the next.

Enforced in code (2026-10-30, owner repeated it): `llm._chain()` drops any provider whose config mentions opus.
