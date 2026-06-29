#!/usr/bin/env bash
# raspi — turn a Raspberry Pi into a Tailscale subnet router + Wi-Fi access point
#
# One-line install (requires USB Wi-Fi dongle):
#   curl -sSL https://raw.githubusercontent.com/ahnopologetic/raspi/main/setup.sh | sudo bash
#
# Custom values:
#   AP_SSID="MyDen" AP_PASS="hunter2"          \
#   WIFI_SSID="MyWiFi" WIFI_PASS="p@ssword"    \
#   TAILSCALE_AUTHKEY="tskey-..."               \
#   curl -sSL https://raw.githubusercontent.com/ahnopologetic/raspi/main/setup.sh | sudo bash
set -euo pipefail

# ── Configuration (override via env vars) ────────────────────────────

AP_SSID="${AP_SSID:-MyPiAP}"
AP_PASS="${AP_PASS:-change-me-please}"
AP_IP="${AP_IP:-192.168.50.1}"
AP_SUBNET="${AP_SUBNET:-192.168.50.0/24}"
AP_DHCP_START="${AP_DHCP_START:-192.168.50.50}"
AP_DHCP_END="${AP_DHCP_END:-192.168.50.150}"
AP_CHANNEL="${AP_CHANNEL:-6}"

WIFI_SSID="${WIFI_SSID:-MyHomeWiFi}"
WIFI_PASS="${WIFI_PASS:-change-me-please}"

TAILSCALE_AUTHKEY="${TAILSCALE_AUTHKEY:-}"
TAILSCALE_ROUTES="${TAILSCALE_ROUTES:-}"
BUILDING_SUBNET="${BUILDING_SUBNET:-}"

# ── Helpers ──────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[*]${NC} $*"; }
ok()    { echo -e "${GREEN}[✓]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; }
section() { echo; echo -e "${CYAN}═══ $* ═══${NC}"; echo; }

need_root() {
    if [[ $EUID -ne 0 ]]; then
        err "This script must be run as root (use sudo)."
        exit 1
    fi
}

step_done() {
    local file="$1" pattern="$2" label="${3:-$1}"
    if grep -q "$pattern" "$file" 2>/dev/null; then
        ok "$label (already configured)"
        return 0
    fi
    return 1
}

# ── Preflight ────────────────────────────────────────────────────────

section "Preflight checks"
need_root

if ! lsusb | grep -qi "rtl8188\|rtl8192\|mt7601"; then
    err "No USB Wi-Fi adapter detected. Plug in the dongle and re-run."
    err "Supported chipsets: RTL8188, RTL8192, MT7601"
    exit 1
fi
ok "USB Wi-Fi adapter found"

# Auto-detect building subnet correctly (network address, not host address)
if [[ -z "$BUILDING_SUBNET" ]]; then
    BUILDING_SUBNET=$(ip -4 route show dev wlan1 2>/dev/null \
        | awk '/proto kernel/{print $1}' | head -1 || echo "192.168.1.0/24")
fi

if [[ -z "$TAILSCALE_ROUTES" ]]; then
    TAILSCALE_ROUTES="$BUILDING_SUBNET,$AP_SUBNET"
fi

ok "Building subnet: $BUILDING_SUBNET"
ok "AP subnet: $AP_SUBNET"
ok "Tailscale routes: $TAILSCALE_ROUTES"

# ── Packages ─────────────────────────────────────────────────────────

section "Installing packages"
apt update -qq
apt install -y --no-install-recommends \
    hostapd dnsmasq iptables-persistent iw curl 2>&1 | tail -1
ok "Packages installed"

# ── Tailscale ────────────────────────────────────────────────────────

section "Tailscale"

if ! command -v tailscale &>/dev/null; then
    curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg \
        | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
    curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list \
        | tee /etc/apt/sources.list.d/tailscale.list >/dev/null
    apt update -qq && apt install -y tailscale
    ok "Tailscale installed"
else
    ok "Tailscale already installed ($(tailscale version | head -1))"
fi

# Enable IP forwarding
if ! step_done /etc/sysctl.d/99-tailscale.conf "ip_forward=1" "IP forwarding"; then
    echo 'net.ipv4.ip_forward=1' >/etc/sysctl.d/99-tailscale.conf
    sysctl -w net.ipv4.ip_forward=1
    ok "IP forwarding enabled"
fi

# Tailscale up — use exit code, not brittle JSON grep
if tailscale ip -4 &>/dev/null; then
    ok "Tailscale already authenticated ($(tailscale ip -4))"
else
    if [[ -n "$TAILSCALE_AUTHKEY" ]]; then
        tailscale up --authkey "$TAILSCALE_AUTHKEY" --ssh --accept-routes \
            --advertise-routes="$TAILSCALE_ROUTES"
        ok "Tailscale connected with auth key"
    else
        info "Starting Tailscale — open this URL to authenticate:"
        tailscale up --ssh --accept-routes --advertise-routes="$TAILSCALE_ROUTES"
        ok "Tailscale connected"
    fi
fi

# ── Network: wlan1 → upstream Wi-Fi ──────────────────────────────────

section "Upstream Wi-Fi (wlan1 — USB dongle)"

if nmcli -t -f NAME connection show --active | grep -q "building-wifi"; then
    ok "Already connected to upstream Wi-Fi"
else
    nmcli con delete building-wifi 2>/dev/null || true
    nmcli con add \
        con-name building-wifi \
        type wifi \
        ifname wlan1 \
        ssid "$WIFI_SSID" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "$WIFI_PASS" 2>&1
    nmcli con up building-wifi
    ok "Connected to $WIFI_SSID"
fi

# ── Network: wlan0 → Access Point ────────────────────────────────────

section "Access Point (wlan0 — built-in Wi-Fi)"

# Lock wlan0 from NetworkManager (heredoc — works in curl|bash)
if ! step_done /etc/NetworkManager/conf.d/unmanaged-wlan0.conf "wlan0" "NM unmanaged rule"; then
    cat >/etc/NetworkManager/conf.d/unmanaged-wlan0.conf <<'NMCONF'
[keyfile]
unmanaged-devices=interface-name:wlan0
NMCONF
    systemctl restart NetworkManager
    sleep 2
fi
ok "wlan0 locked from NetworkManager"

# hostapd config (heredoc — no sed, no passwords in ps aux)
if ! step_done /etc/hostapd/hostapd.conf "interface=wlan0" "hostapd config"; then
    cat >/etc/hostapd/hostapd.conf <<HOSTAPDEOF
interface=wlan0
driver=nl80211
ssid=$AP_SSID
hw_mode=g
channel=$AP_CHANNEL
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$AP_PASS
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
rsn_pairwise=CCMP
HOSTAPDEOF
fi

if ! step_done /etc/default/hostapd 'DAEMON_CONF' "hostapd default"; then
    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' >>/etc/default/hostapd
fi

systemctl unmask hostapd 2>/dev/null || true
systemctl enable hostapd
systemctl restart hostapd
ok "hostapd started (SSID: $AP_SSID, ch $AP_CHANNEL)"

# dnsmasq config (heredoc — includes gateway + DNS)
if ! step_done /etc/dnsmasq.d/ap.conf "interface=wlan0" "dnsmasq config"; then
    cat >/etc/dnsmasq.d/ap.conf <<DNSMASQEOF
interface=wlan0
dhcp-range=$AP_DHCP_START,$AP_DHCP_END,255.255.255.0,24h
dhcp-option=3,$AP_IP
dhcp-option=6,1.1.1.1,8.8.8.8
domain=lan
DNSMASQEOF
fi

systemctl enable dnsmasq
systemctl restart dnsmasq
ok "dnsmasq started (DHCP $AP_DHCP_START-$AP_DHCP_END, gateway $AP_IP)"

# Static IP systemd unit (heredoc)
cat >/etc/systemd/system/ap-ip.service <<UNITEOF
[Unit]
Description=Set static IP for access point
After=network-online.target hostapd.service
Wants=network-online.target
Requires=hostapd.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/bash -c 'for i in \$(seq 1 10); do ip link show wlan0 | grep -q UP && exit 0; sleep 1; done; exit 1'
ExecStart=/usr/sbin/ip addr replace $AP_IP/24 dev wlan0
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable ap-ip
systemctl restart ap-ip
sleep 1
# Ensure dnsmasq binds to the now-assigned IP
systemctl restart dnsmasq
ok "Static IP $AP_IP assigned to wlan0"

# ── NAT / Routing ────────────────────────────────────────────────────

section "NAT (AP clients → internet via wlan1)"

iptables -t nat -C POSTROUTING -o wlan1 -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -o wlan1 -j MASQUERADE

iptables -C FORWARD -i wlan0 -o wlan1 -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i wlan0 -o wlan1 -j ACCEPT

iptables -C FORWARD -i wlan1 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i wlan1 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT

netfilter-persistent save 2>&1 | grep -v 'locale\|warning\|perl' || true
ok "NAT rules configured and persisted"

# ── Verification ─────────────────────────────────────────────────────

section "Verification"
fail=0

echo "  hostapd:     $(systemctl is-active hostapd)"
echo "  dnsmasq:     $(systemctl is-active dnsmasq)"
echo "  ap-ip:       $(systemctl is-active ap-ip)"
echo "  nat-persist: $(systemctl is-active netfilter-persistent)"
echo

if /usr/sbin/iw dev wlan0 info 2>/dev/null | grep -q "type AP"; then
    ok "AP broadcasting: $(/usr/sbin/iw dev wlan0 info | grep ssid | awk '{print $2}')"
else
    err "AP is not in AP mode — check: journalctl -u hostapd"
    fail=1
fi

if ip -4 addr show wlan0 | grep -q "$AP_IP"; then
    ok "AP IP: $AP_IP"
else
    err "AP IP not set"
    fail=1
fi

if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
    ok "Internet reachable"
else
    err "No internet — check upstream Wi-Fi on wlan1"
    fail=1
fi

echo
if [[ $fail -eq 0 ]]; then
    ok "All checks passed."
    echo
    info "Next steps:"
    info "  1. Approve Tailscale routes: https://login.tailscale.com/admin/machines"
    info "     Routes to approve: $TAILSCALE_ROUTES"
    info "  2. Connect devices to Wi-Fi: $AP_SSID"
else
    err "Some checks failed. See above."
    exit 1
fi
