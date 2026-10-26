---
name: background-long-jobs
description: "Don't block the conversation waiting on long renders or polls; run them in the background and keep talking"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 9bbeade5-5cd3-4463-92ef-be1207f2f7f5
  modified: 2026-10-26T12:40:13.360Z
---

The owner rejected several long foreground waits (polling loops waiting for renders, a 20-minute "make short" run) and interrupted to give new instructions instead.

**Why:** They want to stay in control and keep the conversation moving while videos render (renders take 3–25 minutes).
**How to apply:** Start renders and other long jobs with run_in_background, tell the owner in one line what's running, and report when the completion notification arrives. Never use foreground until-loops to wait. Related: [[thoma-channel-project]].
