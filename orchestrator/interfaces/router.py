from .slack import SlackInterface
from .teams import TeamsInterface

def get_interface(platform: str):
    platform = platform.lower()

    if platform == "slack":
        return SlackInterface()

    if platform == "teams":
        return TeamsInterface()

    raise ValueError(f"Unsupported platform: {platform}")

