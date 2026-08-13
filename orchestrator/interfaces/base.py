class BaseInterface:
    def parse_command(self, text: str) -> dict:
        """Extracts command + args from incoming message."""
        raise NotImplementedError

    def format_response(self, result: dict) -> str:
        """Formats agent output for the chat platform."""
        raise NotImplementedError

