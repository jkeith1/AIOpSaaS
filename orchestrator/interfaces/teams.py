from .base import BaseInterface

class TeamsInterface(BaseInterface):
    def parse_command(self, text: str) -> dict:
        # Teams messages often include @mentions, so strip them
        cleaned = text.replace("@AIOpsAgent", "").strip()
        parts = cleaned.split()
        args = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                args[k] = v
        return args

    def format_response(self, result: dict) -> str:
        return (
            "Triage Result:\n"
            f"Summary: {result.get('summary', '')}\n"
        )
