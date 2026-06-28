# Raspberry Pi — Home Network Hub

## Device Details

| Field | Value |
|-------|-------|
| Model | Raspberry Pi 4 Model B |
| OS | Debian GNU/Linux 13 (Trixie), aarch64 |
| Hostname | `humphrey` |
| User | configured in `.env` |
| SSH | Tailscale SSH + key-based (ed25519) |
| Tailscale | subnet router |
| Tailscale IP | configured in `.env` |
| Building Wi-Fi | upstream internet source |
| mDNS | Avahi active |

## How to Connect

### Tailscale (preferred — works from anywhere)
```bash
ssh $RASPI_USER@$RASPI_TAILSCALE_IP
```

### Local (when on same network)
```bash
ssh $RASPI_USER@<local-ip>
```

### Via the CLI
```bash
raspi connect    # interactive SSH via Tailscale
raspi exec "..." # run a single command
```

### SSH key (for passwordless access)
Add your public key to the Pi:
```bash
ssh-copy-id $RASPI_USER@$RASPI_TAILSCALE_IP
```

## Tailscale Subnet Router

Enables access to devices on the building network (172.16.0.0/21) from anywhere via Tailscale.

- **Route:** `$RASPI_BUILDING_SUBNET` advertised
- **IP forwarding:** enabled (`net.ipv4.ip_forward=1`)
- **Admin action needed:** Approve the route at [login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines) → your Pi → Edit route settings

## Quick Start (after cloning)

```bash
cp .env.example .env
# Edit .env with your Pi's values
uv sync
uv run raspi status
```

## Lessons Learned

1. **Wi-Fi SSID gotchas** — special characters (smart quotes, emoji, Unicode) break `wpa_supplicant`. Keep SSIDs plain ASCII. The Pi silently fails to connect.

2. **iPhone hotspot defaults to 5 GHz** — Pi 4 works on 5 GHz but not all channels. Enable **Maximize Compatibility** on iPhone to force 2.4 GHz.

3. **mDNS hostname collision** — iPhone and Pi both named "Humphrey" → `humphrey.local` always resolved to the iPhone. The Pi was online the whole time but invisible by name. **Fix:** give devices unique hostnames, or connect by IP.

4. **Different networks = invisible** — Mac on Ethernet/Wi-Fi, Pi on iPhone hotspot → can't see each other. Must be on **same network** to discover.

5. **"Rapid green flickering" on Pi 4 is normal during first boot** — cloud-init does filesystem expansion, user creation, package installs. Lots of disk I/O. It's not a boot loop — just wait 2-3 minutes.

6. **Pi 4 USB-C power is picky** — e-marked cables (MacBook chargers) can trigger the Pi 4's USB-C bug. Use a dedicated Pi power supply or a dumb cable.

## Wi-Fi Access Point (Planned)

Goal: create `Humphrey's Den` AP for the LG Smart TV to join the Tailscale network.

| Component | Detail |
|-----------|--------|
| USB dongle | TP-Link TL-WN725N (RTL8188EUS) or similar |
| AP SSID | your choice |
| AP password | your choice |
| Software | hostapd (AP) + dnsmasq (DHCP) |
| Tailscale role | Subnet router — makes TV visible to your devices |

### Architecture
```
Building / home Wi-Fi (upstream internet)
         │
    [wlan0 - Pi 4]
         │
    IP forwarding + Tailscale subnet router
         │
    [wlan1 - USB dongle] → your AP SSID
         │
    Smart TV / devices connect here
```

## Quick Recovery Diagnostic

```bash
# Is Pi on the network?
ping humphrey.local

# Scan hotspot subnet (iPhone hotspot = 172.20.10.0/28)
for i in $(seq 1 15); do ping -c 1 -W 1 172.20.10.$i >/dev/null 2>&1 && echo "172.20.10.$i ALIVE"; done

# Find Raspberry Pi MAC (dc:a6:32, b8:27:eb, e4:5f:01)
arp -a | grep -i "dc:a6:32\|b8:27:eb\|e4:5f:01"
```
