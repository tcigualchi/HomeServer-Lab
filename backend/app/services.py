from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from backend.app.models import Event


def record_event(db: Session, level: str, event_type: str, message: str, actor: str | None = None) -> Event:
    event = Event(level=level, event_type=event_type, message=message, actor=actor)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def recent_events(db: Session, limit: int = 20) -> list[Event]:
    return list(db.scalars(select(Event).order_by(desc(Event.created_at)).limit(limit)))
