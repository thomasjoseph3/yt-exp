"""Uploaders. Each returns {"remote_id": ..., "url": ...} or raises."""
from ..config import cfg

DISCLOSURE = "Thoma is an animated character. Narration uses an AI voice; scripts are AI-assisted and reviewed."
DISCLOSURE_OWN_VOICE = "Thoma is an animated character, voiced by the channel's host. Scripts are AI-assisted and reviewed."


def caption(script: dict, kind: str, platform: str) -> str:
    tags = " ".join("#" + h.lstrip("#").replace(" ", "") for h in script.get("hashtags", [])[:5])
    if kind == "short" and platform == "youtube":
        tags += " #Shorts"
    chapters = ""
    if platform == "youtube" and script.get("chapters"):
        chapters = "\n".join(f"{int(t // 60)}:{int(t % 60):02} {name}" for t, name in script["chapters"]) + "\n\n"
    links = _affiliate_links(script)
    credit = ""
    if script.get("music"):
        credit = cfg()["music"]["credit"].format(track=script["music"]) + "\n"
    if script.get("image_credits"):  # CC licenses require the credit wherever the video is posted
        credit += "Photos: " + "; ".join(script["image_credits"]) + "\n"
    sources = ""
    if script.get("sources") and kind == "long":
        sources = "Sources:\n" + "\n".join(f"- {s['outlet']}, {s['title']} ({s['date']}): {s['url']}"
                                            for s in script["sources"][:12]) + "\n\n"
    disclosure = DISCLOSURE_OWN_VOICE if script.get("voice") == "owner" else DISCLOSURE
    handle = (cfg()["channel"].get("youtube_handle") or "").lstrip("@")
    sub = f"New AI explainer every day. Subscribe: https://www.youtube.com/@{handle}?sub_confirmation=1\n\n" if handle else ""
    return f"{script['description']}\n\n{sub}{links}{chapters}{sources}{tags}\n\n{credit}{disclosure}"


def _affiliate_links(script: dict) -> str:
    """Links for tools the video actually mentions, from ai_tools.affiliates, with a disclosure."""
    links = cfg().get("ai_tools", {}).get("affiliates") or {}
    text = (script["title"] + " " + " ".join(s["say"] for s in script["scenes"])).lower()
    found = [f"{name}: {url}" for name, url in links.items() if name.lower() in text]
    if not found:
        return ""
    return ("Tools in this video:\n" + "\n".join(found) +
            "\n(Some links are affiliate links: Thoma may earn a small commission at no extra cost to you.)\n\n")


def platforms_for(kind: str) -> list[str]:
    return cfg()["publish"][f"{kind}_platforms"]
