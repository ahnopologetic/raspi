# raspi

> CLI to manage a Raspberry Pi home network hub from anywhere via Tailscale.

## What it does

- **`raspi status`** — check if your Pi is online, see IP and Wi-Fi info
- **`raspi connect`** — open an interactive SSH session (via Tailscale)
- **`raspi info`** — system details: uptime, disk, memory, CPU temp
- **`raspi scan`** — hunt for your Pi on the local network by MAC address
- **`raspi exec "..."`** — run any command on the Pi remotely

## Quick start

```bash
git clone <repo-url>
cd raspi
cp .env.example .env
# edit .env with your Pi's details
uv sync
uv run raspi status
```

## Requirements

- [uv](https://docs.astral.sh/uv/) for package management
- A Raspberry Pi with [Tailscale](https://tailscale.com) installed
- SSH key added to your Pi for passwordless access

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description |
|----------|-------------|
| `RASPI_TAILSCALE_IP` | Your Pi's Tailscale IP (`tailscale status`) |
| `RASPI_USER` | SSH username on the Pi |
| `RASPI_HOSTNAME` | Pi hostname (for mDNS) |
| `RASPI_MAC` | Pi's Wi-Fi MAC for local scanning |
| `RASPI_BUILDING_SUBNET` | Subnet to scan in CIDR notation |

## Setup guide

See [SETUP.md](SETUP.md) for a detailed walkthrough of setting up a Pi as a Tailscale subnet router and Wi-Fi access point — including lessons learned from real-world gotchas.
