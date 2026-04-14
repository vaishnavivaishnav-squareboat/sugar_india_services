from datetime import datetime


def model_to_dict(obj) -> dict:
    """Generic SQLAlchemy model → dict serializer (ISO-formats datetime values)."""
    result = {}
    for c in obj.__table__.columns:
        val = getattr(obj, c.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        result[c.name] = val
    return result
