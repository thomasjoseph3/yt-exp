"""Uploaders. Each returns {"remote_id": ..., "url": ...} or raises."""
from ..config import cfg

DISCLOSURE = "Thoma is an animated character. Narration uses an AI voice; scripts are AI-assisted and reviewed."


def caption(script: dict, kind: str, platform: str) -> str:
    tags = " ".join("#" + h.lstrip("#").replace(" ", "") for h in script.get("hashtags", [])[:5])
    if kind == "short" and platform == "youtube":
        tags += " #Shorts"
    chapters = ""
    if platform == "youtube" and script.get("chapters"):
        chapters = "\n".join(f"{int(t // 60)}:{int(t % 60):02} {name}" for t, name in script["chapters"]) + "\n\n"
    credit = ""
    if script.get("music"):
        credit = cfg()["music"]["credit"].format(track=script["music"]) + "\n"
    return f"{script['description']}\n\n{chapters}{tags}\n\n{credit}{DISCLOSURE}"


def platforms_for(kind: str) -> list[str]:
    return cfg()["publish"][f"{kind}_platforms"]
