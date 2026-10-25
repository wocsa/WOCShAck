import time


def is_session_expired(session):
    val = session.get('pin_expiry')
    expiry = session.get('pin_expiry', 0)
    if expiry < int(time.time()):
        # Expired: delete from session and return None
        session.pop('pin_expiry', None)
        session.pop('pin_expiry', None)
        return None
    return val
