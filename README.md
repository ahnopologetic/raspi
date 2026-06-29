# raspi

> Turn a Raspberry Pi into a Tailscale subnet router + Wi-Fi access point, then manage it with a CLI.

## One-line install (on a fresh Pi)

```bash
curl -sSL https://raw.githubusercontent.com/ahnopologetic/raspi/main/setup.sh | sudo bash
```

With custom values:

```bash
AP_SSID="MyDen" AP_PASS="hunter2"            \
WIFI_SSID="MyWiFi" WIFI_PASS="p@ssword"      \
TAILSCALE_AUTHKEY="tskey-..."                 \
curl -sSL https://raw.githubusercontent.com/ahnopologetic/raspi/main/setup.sh | sudo bash
```

## What it sets up

| Component | Interface | Purpose |
|-----------|-----------|---------|
| Tailscale subnet router | `tailscale0` | Access your home network from anywhere |
| Wi-Fi access point | `wlan0` (built-in) | Devices connect here (TV, speakers, etc.) |
| Upstream Wi-Fi client | `wlan1` (USB dongle) | Connects to your building/home Wi-Fi |
| NAT + DHCP | `hostapd` + `dnsmasq` | AP clients get internet via upstream |

Requires: Raspberry Pi 4/5 + USB Wi-Fi dongle (RTL8188 or similar).

## CLI (optional — runs on your laptop)

```bash
git clone https://github.com/ahnopologetic/raspi
cd raspi
cp .env.example .env    # fill in your Pi's Tailscale IP
uv sync
uv run raspi status
```

Commands: `status`, `connect`, `scan`, `info`, `exec`

## Structure

```
├── setup.sh              ← provision a Pi from scratch
├── conf/                 ← config templates
│   ├── hostapd.conf
│   ├── dnsmasq.conf
│   ├── networkmanager.conf
│   └── systemd/ap-ip.service
├── src/raspi/            ← Python CLI (typer + rich)
├── tests/
└── SETUP.md              ← detailed walkthrough
```

## Requirements

- Raspberry Pi 4 Model B (or Pi 5)
- USB Wi-Fi dongle (RTL8188EUS, MT7601, or similar)
- Raspberry Pi OS (64-bit, Bookworm or newer)
- [Tailscale](https://tailscale.com) account (free tier works)
- [uv](https://docs.astral.sh/uv/) (for CLI only)
