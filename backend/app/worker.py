"""Worker local de observabilidade. Não chama serviços externos nem executa shell arbitrário."""
import time
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import desc, select
from backend.app.db import SessionLocal
from backend.app.models import Alert, NetworkHost
from backend.app.monitoring import server_status
from backend.app.network import ping_host

logger = logging.getLogger(__name__)


def _alert_once(db, event_type: str, severity: str, message: str):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    recent = db.scalar(select(Alert).where(Alert.event_type == event_type, Alert.created_at >= cutoff).order_by(desc(Alert.created_at)))
    if not recent:
        db.add(Alert(event_type=event_type, severity=severity, message=message))
        db.commit()


def monitor_once() -> None:
    with SessionLocal() as db:
        status = server_status()
        if status["cpu_percent"] >= 90: _alert_once(db, "HighCPU", "warning", f"CPU em {status['cpu_percent']:.1f}%")
        if status["memory_percent"] >= 90: _alert_once(db, "HighRAM", "warning", f"RAM em {status['memory_percent']:.1f}%")
        if status["disk_percent"] >= 90: _alert_once(db, "DiskFull", "critical", f"Disco em {status['disk_percent']:.1f}%")
        for host in db.scalars(select(NetworkHost)).all():
            alive, latency = ping_host(host.ip_address)
            new_status = "online" if alive else "offline"
            if host.status != new_status:
                _alert_once(db, "DeviceOnline" if alive else "DeviceOffline", "info" if alive else "warning", f"{host.hostname or host.ip_address} ficou {new_status}")
            host.status, host.latency_ms = new_status, latency
        db.commit()


def run_forever(interval: int = 30):
    while True:
        try: monitor_once()
        except Exception:
            logger.exception("Falha no ciclo do worker")
        time.sleep(interval)


if __name__ == "__main__":
    run_forever()
