"""
Raspberry Pi Home Hub CLI — manage and connect to your Pi from anywhere.

Configuration is read from environment variables or a `.env` file.
Copy `.env.example` to `.env` and fill in your values.
"""

from __future__ import annotations

import os
import subprocess

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Load .env from the project root or current directory
load_dotenv()

app = typer.Typer(
    name="raspi",
    help="Manage your Raspberry Pi home network hub.",
    no_args_is_help=True,
)
console = Console()

# ── Config (override via .env or environment) ───────────────────────
PI_TAILSCALE_IP = os.getenv("RASPI_TAILSCALE_IP", "100.105.94.23")
PI_USER = os.getenv("RASPI_USER", "pi")
PI_HOSTNAME = os.getenv("RASPI_HOSTNAME", "raspberrypi")
PI_MAC = os.getenv("RASPI_MAC", "b8:27:eb:00:00:00")
BUILDING_SUBNET = os.getenv("RASPI_BUILDING_SUBNET", "192.168.1.0/24")


def _ssh(ip: str, cmd: str | None = None, timeout: int = 10) -> str:
    """Run a command on the Pi via SSH. Returns stdout or raises."""
    ssh_cmd = [
        "ssh",
        "-o",
        "ConnectTimeout=3",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        f"{PI_USER}@{ip}",
    ]
    if cmd:
        ssh_cmd.append(cmd)
    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "SSH failed")
    return result.stdout.strip()


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    """Run a local command, raise on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result


# ── Commands ────────────────────────────────────────────────────────


@app.command()
def status() -> None:
    """Check if the Pi is online and show its current state."""
    online = False

    # Try Tailscale first
    try:
        output = _ssh(PI_TAILSCALE_IP, timeout=5)
        online = True
    except Exception:
        output = None

    if online and output:
        # Parse key info
        table = Table(title="Pi Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Status", "🟢 Online")
        table.add_row("Tailscale IP", PI_TAILSCALE_IP)

        # Get fresh details
        try:
            hostname = _ssh(PI_TAILSCALE_IP, "hostname", timeout=5)
            wifi_cmd = (
                "iwgetid -r 2>/dev/null || "
                "nmcli -t -f NAME con show --active | grep wifi | cut -d: -f1"
            )
            wifi = _ssh(PI_TAILSCALE_IP, wifi_cmd, timeout=5)
            ip_cmd = "ip -4 addr show wlan0 | grep inet | awk '{print $2}'"
            ip_raw = _ssh(PI_TAILSCALE_IP, ip_cmd, timeout=5)
            table.add_row("Hostname", hostname)
            table.add_row("Wi-Fi SSID", wifi)
            table.add_row("Wi-Fi IP", ip_raw)
        except Exception:
            pass

        console.print(table)
    else:
        console.print("[red]🔴 Pi is offline[/red]")
        console.print(f"Tried: {PI_TAILSCALE_IP} (Tailscale)")
        console.print("Make sure the Pi is powered on and Tailscale is connected.")


@app.command()
def connect() -> None:
    """Open an interactive SSH session to the Pi (via Tailscale)."""
    console.print(f"[cyan]Connecting to {PI_USER}@{PI_TAILSCALE_IP}...[/cyan]")
    subprocess.run(
        [
            "ssh",
            f"{PI_USER}@{PI_TAILSCALE_IP}",
        ]
    )


@app.command()
def scan() -> None:
    """Scan the building subnet for the Pi by its MAC address."""
    console.print("[cyan]Scanning building network for the Pi...[/cyan]")

    # Quick ARP check
    result = _run(["arp", "-a"], timeout=10)
    for line in result.stdout.split("\n"):
        if PI_MAC.lower() in line.lower():
            ip = line.split("(")[1].split(")")[0] if "(" in line else line.split()[1]
            console.print(f"[green]Found at {ip}[/green]")
            return

    # Deeper scan — ping sweep the building subnet
    console.print("[cyan]ARP miss — ping sweeping building subnet...[/cyan]")
    found = False
    for i in range(1, 255):
        result = _run(["ping", "-c", "1", "-W", "1", f"172.16.{i}.1"], timeout=2)
        if result.returncode == 0:
            # Check ARP after each successful ping
            arp_result = _run(["arp", "-a"], timeout=5)
            if PI_MAC.lower() in arp_result.stdout.lower():
                console.print(f"[green]Found at 172.16.{i}.1[/green]")
                found = True
                break

    if not found:
        console.print("[red]Pi not found on building network[/red]")


@app.command()
def info() -> None:
    """Show detailed system info about the Pi."""
    try:
        output = _ssh(
            PI_TAILSCALE_IP,
            """
echo "OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')"
echo "Kernel: $(uname -r)"
echo "Uptime: $(uptime -p | sed 's/up //')"
echo "Disk: $(df -h / | awk 'NR==2{print $3 " / " $2 " (" $5 ")"}')"
echo "Memory: $(free -h | awk '/^Mem:/{print $3 " / " $2}')"
echo "CPU temp: $(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 || echo 'N/A')"
echo "Tailscale: $(tailscale version | head -1)"
""",
            timeout=10,
        )
        console.print(output)
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")


@app.command()
def exec(cmd: str = typer.Argument(..., help="Command to run on the Pi")) -> None:
    """Run an arbitrary command on the Pi."""
    try:
        output = _ssh(PI_TAILSCALE_IP, cmd, timeout=30)
        console.print(output)
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")


if __name__ == "__main__":
    app()
