import platform
import socket
import time
from datetime import datetime, timezone
import psutil

BOOT_TIME = psutil.boot_time()


def _temperature() -> float | None:
    try:
        sensors = psutil.sensors_temperatures()
        values = [entry.current for group in sensors.values() for entry in group if entry.current is not None]
        return round(max(values), 1) if values else None
    except (AttributeError, OSError):
        return None


def server_status() -> dict:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    return {"hostname": socket.gethostname(), "platform": platform.platform(), "cpu_percent": psutil.cpu_percent(interval=0.15), "memory_percent": memory.percent, "memory_used_bytes": memory.used, "memory_total_bytes": memory.total, "disk_percent": disk.percent, "disk_used_bytes": disk.used, "disk_total_bytes": disk.total, "temperature_c": _temperature(), "load_average": list(getattr(psutil, "getloadavg", lambda: (0, 0, 0))()), "uptime_seconds": max(0, int(time.time() - BOOT_TIME)), "boot_time": datetime.fromtimestamp(BOOT_TIME, timezone.utc).isoformat(), "network_bytes_sent": net.bytes_sent, "network_bytes_recv": net.bytes_recv, "collected_at": datetime.now(timezone.utc).isoformat()}
