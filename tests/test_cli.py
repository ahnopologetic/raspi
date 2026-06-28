"""Tests for the raspi CLI."""

from __future__ import annotations

import os
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from typer import Typer
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_env() -> Generator[None, None, None]:
    """Isolate tests from real .env values and module state."""
    with patch.dict(os.environ, {}, clear=True):
        yield


@pytest.fixture
def app() -> Typer:
    """Import the app in a clean environment."""
    from raspi import app as _app

    return _app


# ── Help / registration ─────────────────────────────────────────────


def test_cli_help(app: Typer) -> None:
    """All commands appear in --help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "status" in result.stdout
    assert "connect" in result.stdout
    assert "scan" in result.stdout
    assert "info" in result.stdout
    assert "exec" in result.stdout


def test_cli_no_args_shows_help(app: Typer) -> None:
    """Running with no args shows help."""
    result = runner.invoke(app)
    assert result.exit_code in (0, 2)
    assert "Usage" in result.stdout or "Manage your Raspberry Pi" in result.stdout


# ── Config / env loading ────────────────────────────────────────────


def test_defaults_when_no_env() -> None:
    """Fallback defaults are used when no env vars set."""

    def _noenv(key: str, default: str | None = None) -> str | None:
        return default

    with patch.object(os, "getenv", side_effect=_noenv):
        import importlib

        import raspi

        importlib.reload(raspi)
        assert raspi.PI_USER == "pi"
        assert raspi.PI_HOSTNAME == "raspberrypi"


def test_env_override() -> None:
    """Environment variables override defaults."""
    overrides = {"RASPI_USER": "alice", "RASPI_HOSTNAME": "mypi"}

    def _fake_getenv(key: str, default: str = "") -> str | None:
        return overrides.get(key, default)

    with patch.object(os, "getenv", side_effect=_fake_getenv):
        import importlib

        import raspi

        importlib.reload(raspi)
        assert raspi.PI_USER == "alice"
        assert raspi.PI_HOSTNAME == "mypi"


# ── Status command ──────────────────────────────────────────────────


@patch("raspi._ssh")
def test_status_online(mock_ssh: MagicMock, app: Typer) -> None:
    """Status shows online when SSH succeeds."""
    mock_ssh.return_value = "dummy output"

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "🟢 Online" in result.stdout


@patch("raspi._ssh", side_effect=RuntimeError("SSH failed"))
def test_status_offline(mock_ssh: MagicMock, app: Typer) -> None:
    """Status shows offline when SSH fails."""
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "🔴 Pi is offline" in result.stdout


# ── Connect command ─────────────────────────────────────────────────


@patch("subprocess.run")
def test_connect(mock_run: MagicMock, app: Typer) -> None:
    """Connect invokes SSH with correct args."""
    mock_run.return_value = MagicMock(returncode=0)
    with patch("raspi.PI_USER", "testuser"), patch("raspi.PI_TAILSCALE_IP", "10.0.0.1"):
        result = runner.invoke(app, ["connect"])
    assert result.exit_code == 0
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args == ["ssh", "testuser@10.0.0.1"]


# ── Scan command ────────────────────────────────────────────────────


@patch("subprocess.run")
def test_scan_finds_pi_in_arp(mock_run: MagicMock, app: Typer) -> None:
    """Scan finds Pi when its MAC is in ARP table."""
    arp_output = MagicMock()
    arp_output.stdout = "? (172.16.2.125) at dc:a6:32:72:af:d on en0 ifscope [ethernet]"
    arp_output.returncode = 0
    mock_run.return_value = arp_output

    with patch("raspi.PI_MAC", "dc:a6:32:72:af:d"):
        result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0
    assert "Found at" in result.stdout
    assert "172.16.2.125" in result.stdout


@patch("subprocess.run")
def test_scan_not_found(mock_run: MagicMock, app: Typer) -> None:
    """Scan reports not found when Pi MAC absent."""
    empty_arp = MagicMock()
    empty_arp.stdout = "? (172.16.2.1) at 00:11:22:33:44:55 on en0"
    empty_arp.returncode = 0

    ping_fail = MagicMock()
    ping_fail.returncode = 1

    mock_run.side_effect = [empty_arp] + [ping_fail] * 255

    with patch("raspi.PI_MAC", "dc:a6:32:72:af:d"):
        result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0
    assert "not found" in result.stdout


# ── Info command ────────────────────────────────────────────────────


@patch("raspi._ssh")
def test_info(mock_ssh: MagicMock, app: Typer) -> None:
    """Info prints system details."""
    mock_ssh.return_value = (
        "OS: Debian\nKernel: 6.6\nUptime: 1 hour\n"
        "Disk: 5G / 235G (3%)\nMemory: 200M / 1.8G\n"
        "CPU temp: 42.0'C\nTailscale: 1.98.4"
    )

    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "Debian" in result.stdout
    assert "6.6" in result.stdout


@patch("raspi._ssh", side_effect=RuntimeError("offline"))
def test_info_offline(mock_ssh: MagicMock, app: Typer) -> None:
    """Info shows error when Pi is unreachable."""
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "Failed" in result.stdout


# ── Exec command ────────────────────────────────────────────────────


@patch("raspi._ssh")
def test_exec(mock_ssh: MagicMock, app: Typer) -> None:
    """Exec runs an arbitrary command."""
    mock_ssh.return_value = "hello from pi"

    result = runner.invoke(app, ["exec", "echo hello"])
    assert result.exit_code == 0
    assert "hello from pi" in result.stdout
    mock_ssh.assert_called_once_with("100.105.94.23", "echo hello", timeout=30)


@patch("raspi._ssh", side_effect=RuntimeError("offline"))
def test_exec_failure(mock_ssh: MagicMock, app: Typer) -> None:
    """Exec shows error on failure."""
    result = runner.invoke(app, ["exec", "bad-command"])
    assert result.exit_code == 0
    assert "Failed" in result.stdout
