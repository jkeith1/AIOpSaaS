from .config import Config
from .agent import ClusterTroubleshooterAgent
from .interfaces.router import get_interface

def main():
    config = Config()
    agent = ClusterTroubleshooterAgent(config=config)

    # Example: choose interface dynamically
    platform = "teams"  # or "slack"
    iface = get_interface(platform)

    # Simulate incoming command
    command = "/triage namespace=default"
    args = iface.parse_command(command)

    if "pod" in args:
        result = agent.triage_pod(args["namespace"], args["pod"])
    else:
        result = agent.triage_namespace(args["namespace"])

    print(iface.format_response(result))

if __name__ == "__main__":
    main()

