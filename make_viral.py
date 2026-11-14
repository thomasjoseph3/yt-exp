"""make_viral.py - Produce the 3 researched viral long videos."""
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("make_viral")

sys.path.insert(0, str(Path(__file__).parent))
from thoma import pipeline

VIRAL_IDEAS = [
    (380, "Incognito Mode Is a Lie. Here is Who Can Actually See Everything You Do."),
    (381, "Your Phone Has a Secret Brain. The NPU chip running AI offline without you knowing."),
    (382, "AI Cloned My Mom Voice in 3 Seconds. How the voice clone scam actually works and how to protect yourself."),
]

def main():
    for idea_id, title in VIRAL_IDEAS:
        log.info("==================================================")
        log.info("Starting Long Video for Idea #%d: %s", idea_id, title)
        log.info("==================================================")
        try:
            vid = pipeline.make("long", idea_id=idea_id)
            log.info(">>> SUCCESS: Video #%d is READY!", vid)
        except Exception as e:
            log.exception("Failed making video for idea #%d: %s", idea_id, e)

if __name__ == "__main__":
    main()
