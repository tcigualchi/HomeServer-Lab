import json
import socket
import subprocess
from dataclasses import dataclass
from typing import Any


class IntegrationError(Exception):
    pass


def normalize_mac(value: str) -> str:
    mac = value.replace("-", ":").upper()
    parts = mac.split(":")
    if len(parts) != 6 or any(len(part) != 2 or any(ch not in "0123456789ABCDEF" for ch in part) for part in parts):
        raise IntegrationError("MAC address inválido")
    return mac


def wake_on_lan(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    mac = normalize_mac(mac)
    payload = bytes.fromhex("FF" * 6 + mac.replace(":", "") * 16)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(payload, (broadcast, port))
    finally:
        sock.close()


@dataclass
class ServiceResult:
    action: str
    status: str
    output: str


def systemd_action(unit: str, action: str, allowed_units: set[str], allowed_actions: set[str]) -> ServiceResult:
    if unit not in allowed_units or action not in allowed_actions:
        raise IntegrationError("Serviço ou ação não autorizado")
    if action not in {"start", "stop", "restart", "status"}:
        raise IntegrationError("Ação inválida")
    result = subprocess.run(["systemctl", action, unit], capture_output=True, text=True, timeout=10, check=False)
    return ServiceResult(action, "ok" if result.returncode == 0 else "error", (result.stdout or result.stderr).strip()[:1000])


def capabilities(value: str) -> list[str]:
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
