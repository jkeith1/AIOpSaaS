from .base import BaseInterface

class SlackInterface(BaseInterface):
    def parse_command(self, text: str) -> dict:
        # Example: "/triage namespace=foo pod=bar"
        parts = text.split()
        args = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                args[k] = v
        return args

    def format_response(self, result: dict) -> str:
        return f"*Triage Result*\n{result.get('summary', '')}"

