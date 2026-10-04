import asyncio
import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from backend.app.core.config import get_settings
from backend.app.db import get_db
from backend.app.models import Alert, AutomationRule, Camera, Device, NetworkHost, ServiceUnit, StatusSample, User
from backend.app.monitoring import server_status
from backend.app.network import discover_neighbors, ping_host
from backend.app.integrations import IntegrationError, capabilities, normalize_mac, systemd_action, wake_on_lan
from backend.app.security import create_session, current_session, verify_password
from backend.app.services import recent_events, record_event

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
login_attempts: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path("data").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    db = next(get_db())
    try:
        if db.scalar(select(User).limit(1)) is None and settings.admin_password_hash:
            db.add(User(username=settings.admin_username, password_hash=settings.admin_password_hash, role="Admin"))
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, docs_url="/docs" if settings.app_env != "production" else None, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-CSRF-Token"])
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self' ws: wss:; style-src 'self'; script-src 'self'; img-src 'self' data:"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def auth(request: Request, db: Session = Depends(get_db)):
    session = current_session(request, db)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    return session


def require_csrf(request: Request, session):
    if request.headers.get("X-CSRF-Token") != session[1].csrf_token:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def require_role(session, *roles: str):
    if session[0].role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def require_write(request: Request, session, *roles: str):
    require_role(session, *roles)
    require_csrf(request, session)


@app.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse("/dashboard" if current_session(request, db) else "/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"app_name": settings.app_name, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    now = time.time()
    attempts = login_attempts[request.client.host if request.client else "unknown"]
    while attempts and now - attempts[0] > 300:
        attempts.popleft()
    attempts.append(now)
    if len(attempts) > 10:
        return templates.TemplateResponse(request=request, name="login.html", context={"app_name": settings.app_name, "error": "Muitas tentativas. Tente novamente em alguns minutos."}, status_code=429)
    user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    if not user or not verify_password(password, user.password_hash):
        record_event(db, "SECURITY", "LoginFailed", f"Falha de login para {username}", username)
        return templates.TemplateResponse(request=request, name="login.html", context={"app_name": settings.app_name, "error": "Credenciais inválidas."}, status_code=401)
    raw, _ = create_session(db, user)
    record_event(db, "SECURITY", "Login", "Login realizado", user.username)
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(settings.session_cookie_name, raw, httponly=True, secure=settings.session_cookie_secure, samesite="lax", max_age=settings.session_ttl_hours * 3600)
    return response


@app.post("/logout")
def logout(request: Request, db: Session = Depends(get_db), session=Depends(auth)):
    require_csrf(request, session)
    db.delete(session[1])
    db.commit()
    record_event(db, "SECURITY", "Logout", "Logout realizado", session[0].username)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(settings.session_cookie_name)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session=Depends(auth)):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"app_name": settings.app_name, "user": session[0], "csrf_token": session[1].csrf_token})


@app.get("/{module}", response_class=HTMLResponse)
def module_page(module: str, request: Request, session=Depends(auth)):
    allowed = {"devices", "network", "cameras", "services", "alerts", "logs", "automation", "settings", "server"}
    if module not in allowed:
        raise HTTPException(404, "Página não encontrada")
    return templates.TemplateResponse(request=request, name="module.html", context={"app_name": settings.app_name, "user": session[0], "csrf_token": session[1].csrf_token, "page": module})


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "homelab-api"}


@app.get("/api/me")
def me(session=Depends(auth)):
    user, record = session
    return {"username": user.username, "role": user.role, "csrf_token": record.csrf_token}


@app.get("/api/server/status")
def api_server_status(session=Depends(auth)):
    return server_status()


@app.get("/api/events")
def api_events(limit: int = 20, db: Session = Depends(get_db), session=Depends(auth)):
    limit = max(1, min(limit, 100))
    return [{"id": e.id, "level": e.level, "event_type": e.event_type, "message": e.message, "actor": e.actor, "created_at": e.created_at.isoformat()} for e in recent_events(db, limit)]


@app.get("/api/network/hosts")
def network_hosts(db: Session = Depends(get_db), session=Depends(auth)):
    hosts = db.scalars(select(NetworkHost).order_by(NetworkHost.ip_address)).all()
    return [{"id": h.id, "hostname": h.hostname, "ip_address": h.ip_address, "mac_address": h.mac_address, "vendor": h.vendor, "status": h.status, "latency_ms": h.latency_ms, "last_seen": h.last_seen.isoformat() if h.last_seen else None} for h in hosts]


@app.post("/api/network/discover")
def network_discover(request: Request, db: Session = Depends(get_db), session=Depends(auth)):
    require_write(request, session, "Admin")
    discovered = discover_neighbors()
    for item in discovered:
        host = db.scalar(select(NetworkHost).where(NetworkHost.ip_address == item["ip_address"]))
        if not host:
            host = NetworkHost(ip_address=item["ip_address"])
            db.add(host)
        host.hostname = item["hostname"]
        host.mac_address = item["mac_address"]
        host.status = item["status"]
        host.latency_ms = item["latency_ms"]
        if item["last_seen"]:
            from datetime import datetime
            host.last_seen = datetime.fromisoformat(item["last_seen"])
        db.flush()
        db.add(StatusSample(host_id=host.id, status=host.status, latency_ms=host.latency_ms))
    db.commit()
    record_event(db, "INFO", "NetworkDiscovery", f"{len(discovered)} vizinho(s) descoberto(s)", session[0].username)
    return {"count": len(discovered), "hosts": discovered}


@app.post("/api/network/hosts/{host_id}/ping")
def network_ping(host_id: int, request: Request, db: Session = Depends(get_db), session=Depends(auth)):
    require_write(request, session, "Admin", "User")
    host = db.get(NetworkHost, host_id)
    if not host:
        raise HTTPException(404, "Host não encontrado")
    alive, latency = ping_host(host.ip_address)
    host.status, host.latency_ms = ("online" if alive else "offline"), latency
    db.add(StatusSample(host_id=host.id, status=host.status, latency_ms=latency)); db.commit()
    return {"status": host.status, "latency_ms": latency}


@app.get("/api/devices")
def devices(db: Session = Depends(get_db), session=Depends(auth)):
    return [{"id": d.id, "name": d.name, "kind": d.kind, "manufacturer": d.manufacturer, "protocol": d.protocol, "address": d.address, "mac_address": d.mac_address, "capabilities": capabilities(d.capabilities), "enabled": d.is_enabled} for d in db.scalars(select(Device).order_by(Device.name)).all()]


@app.post("/api/devices")
def create_device(request: Request, payload: dict = Body(...), db: Session = Depends(get_db), session=Depends(auth)):
    require_write(request, session, "Admin")
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 120:
        raise HTTPException(422, "Nome inválido")
    mac = payload.get("mac_address")
    if mac:
        try: mac = normalize_mac(str(mac))
        except IntegrationError as exc: raise HTTPException(422, str(exc)) from exc
    device = Device(name=name, kind=str(payload.get("kind", "generic"))[:40], manufacturer=str(payload.get("manufacturer", ""))[:100] or None, protocol=str(payload.get("protocol", "manual"))[:40], address=str(payload.get("address", ""))[:255] or None, mac_address=mac, capabilities=json.dumps(payload.get("capabilities", [])))
    db.add(device); db.commit(); db.refresh(device)
    record_event(db, "INFO", "DeviceCreated", f"Dispositivo cadastrado: {device.name}", session[0].username)
    return {"id": device.id, "name": device.name}


@app.post("/api/devices/{device_id}/wake")
def device_wake(device_id: int, request: Request, db: Session = Depends(get_db), session=Depends(auth)):
    require_write(request, session, "Admin", "User")
    device = db.get(Device, device_id)
    if not device or not device.mac_address:
        raise HTTPException(404, "Dispositivo sem MAC cadastrado")
    try: wake_on_lan(device.mac_address)
    except (OSError, IntegrationError) as exc: raise HTTPException(502, str(exc)) from exc
    record_event(db, "INFO", "WakeOnLanSent", f"Wake-on-LAN enviado para {device.name}", session[0].username)
    return {"status": "sent", "device_id": device.id}


@app.get("/api/services")
def services(db: Session = Depends(get_db), session=Depends(auth)):
    return [{"id": s.id, "name": s.name, "unit_name": s.unit_name, "enabled_actions": s.enabled_actions.split(","), "enabled": s.is_enabled} for s in db.scalars(select(ServiceUnit).order_by(ServiceUnit.name)).all()]


@app.post("/api/services")
def create_service(request: Request, payload: dict = Body(...), db: Session = Depends(get_db), session=Depends(auth)):
    require_write(request, session, "Admin")
    import re
    unit = str(payload.get("unit_name", ""))
    if not re.fullmatch(r"[a-zA-Z0-9_.@-]+\.service", unit):
        raise HTTPException(422, "Unit systemd inválida")
    if db.scalar(select(ServiceUnit).where(ServiceUnit.unit_name == unit)):
        raise HTTPException(409, "Unit já cadastrada")
    actions = [a for a in payload.get("enabled_actions", ["status", "restart"]) if a in {"status", "start", "stop", "restart"}]
    service = ServiceUnit(name=str(payload.get("name", unit))[:120], unit_name=unit, enabled_actions=",".join(actions), is_enabled=bool(payload.get("enabled", False)))
    db.add(service); db.commit(); db.refresh(service)
    record_event(db, "SECURITY", "ServiceAllowlisted", f"Unit autorizada: {unit}", session[0].username)
    return {"id": service.id, "unit_name": service.unit_name, "enabled": service.is_enabled}


@app.post("/api/services/{service_id}/{action}")
def service_action(service_id: int, action: str, request: Request, db: Session = Depends(get_db), session=Depends(auth)):
    require_write(request, session, "Admin")
    service = db.get(ServiceUnit, service_id)
    if not service or not service.is_enabled:
        raise HTTPException(404, "Serviço não autorizado")
    try:
        result = systemd_action(service.unit_name, action, {service.unit_name}, set(service.enabled_actions.split(",")))
    except IntegrationError as exc: raise HTTPException(403, str(exc)) from exc
    record_event(db, "INFO" if result.status == "ok" else "ERROR", "ServiceAction", f"{action} {service.unit_name}: {result.status}", session[0].username)
    return {"action": result.action, "status": result.status, "output": result.output}


@app.get("/api/cameras")
def cameras(db: Session = Depends(get_db), session=Depends(auth)):
    return [{"id": c.id, "name": c.name, "address": c.address, "protocol": c.protocol, "snapshot_url_configured": bool(c.snapshot_url), "status": c.last_status} for c in db.scalars(select(Camera).order_by(Camera.name)).all()]


@app.post("/api/cameras")
def create_camera(request: Request, payload: dict = Body(...), db: Session = Depends(get_db), session=Depends(auth)):
    require_write(request, session, "Admin")
    name, address = str(payload.get("name", "")).strip(), str(payload.get("address", "")).strip()
    if not name or not address or len(name) > 120 or len(address) > 255:
        raise HTTPException(422, "Nome e endereço são obrigatórios")
    protocol = str(payload.get("protocol", "rtsp")).lower()
    if protocol not in {"rtsp", "http", "onvif"}:
        raise HTTPException(422, "Protocolo de câmera inválido")
    camera = Camera(name=name, address=address, protocol=protocol, snapshot_url=str(payload.get("snapshot_url", ""))[:500] or None)
    db.add(camera); db.commit(); db.refresh(camera)
    record_event(db, "INFO", "CameraCreated", f"Câmera cadastrada: {camera.name}", session[0].username)
    return {"id": camera.id, "name": camera.name, "status": "unknown"}


@app.get("/api/alerts")
def alerts(db: Session = Depends(get_db), session=Depends(auth)):
    return [{"id": a.id, "event_type": a.event_type, "severity": a.severity, "message": a.message, "acknowledged": a.is_acknowledged, "created_at": a.created_at.isoformat()} for a in db.scalars(select(Alert).order_by(desc(Alert.created_at)).limit(100)).all()]


@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, request: Request, db: Session = Depends(get_db), session=Depends(auth)):
    require_write(request, session, "Admin", "User")
    alert = db.get(Alert, alert_id)
    if not alert: raise HTTPException(404, "Alerta não encontrado")
    alert.is_acknowledged = True; db.commit()
    return {"status": "acknowledged"}


@app.get("/api/automations")
def automations(db: Session = Depends(get_db), session=Depends(auth)):
    return [{"id": r.id, "name": r.name, "trigger_type": r.trigger_type, "condition": json.loads(r.condition_json), "action_type": r.action_type, "action": json.loads(r.action_json), "enabled": r.enabled} for r in db.scalars(select(AutomationRule).order_by(AutomationRule.name)).all()]


@app.post("/api/automations")
def create_automation(request: Request, payload: dict = Body(...), db: Session = Depends(get_db), session=Depends(auth)):
    require_write(request, session, "Admin")
    allowed_triggers = {"DeviceOnline", "DeviceOffline", "ServiceDown", "CameraOffline", "HighCPU", "HighRAM", "DiskFull", "Schedule"}
    allowed_actions = {"record_event", "create_alert", "discord_notify", "device_command"}
    trigger, action = str(payload.get("trigger_type", "")), str(payload.get("action_type", ""))
    if trigger not in allowed_triggers or action not in allowed_actions:
        raise HTTPException(422, "Trigger ou ação não suportado")
    rule = AutomationRule(name=str(payload.get("name", "Nova regra"))[:120], trigger_type=trigger, condition_json=json.dumps(payload.get("condition", {})), action_type=action, action_json=json.dumps(payload.get("action", {})), enabled=False)
    db.add(rule); db.commit(); db.refresh(rule)
    return {"id": rule.id, "enabled": rule.enabled}


@app.websocket("/ws/server")
async def ws_server(websocket: WebSocket):
    await websocket.accept()
    try:
        db = next(get_db())
        try:
            if not current_session(websocket, db):
                await websocket.close(code=1008)
                return
        finally:
            db.close()
        while True:
            await websocket.send_json(server_status())
            await asyncio.sleep(5)
    except (WebSocketDisconnect, RuntimeError):
        return
