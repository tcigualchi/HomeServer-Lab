import platform
import re
import socket
import subprocess
import time
from datetime import datetime, timezone

MAC_RE = re.compile(r"(?i)([0-9a-f]{2}(?:[:-][0-9a-f]{2}){5})")


def _ping_command(host: str) -> list[str]:
    if platform.system().lower() == "windows":
        return ["ping", "-n", "1", "-w", "1000", host]
    return ["ping", "-c", "1", "-W", "1", host]


def ping_host(host: str) -> tuple[bool, float | None]:
    started = time.perf_counter()
    try:
        result = subprocess.run(_ping_command(host), capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False, None
    if result.returncode != 0:
        return False, None
    return True, round((time.perf_counter() - started) * 1000, 2)


def discover_neighbors() -> list[dict]:
    """Reads the OS neighbor table; it does not scan arbitrary addresses."""
    commands = [["ip", "neigh", "show"]] if platform.system().lower() != "windows" else [["arp", "-a"]]
    try:
        result = subprocess.run(commands[0], capture_output=True, text=True, timeout=3, check=False)
    except OSError:
        return []
    found = []
    for line in result.stdout.splitlines():
        mac = MAC_RE.search(line)
        ip = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line)
        if not ip:
            continue
        host_ip = ip.group(0)
        alive, latency = ping_host(host_ip)
        try:
            hostname = socket.gethostbyaddr(host_ip)[0]
        except (OSError, socket.herror):
            hostname = None
        found.append({"ip_address": host_ip, "mac_address": mac.group(1) if mac else None, "hostname": hostname, "status": "online" if alive else "offline", "latency_ms": latency, "last_seen": datetime.now(timezone.utc).isoformat() if alive else None})
    return found
