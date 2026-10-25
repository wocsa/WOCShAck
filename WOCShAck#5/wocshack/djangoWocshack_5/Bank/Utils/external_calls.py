from contextlib import contextmanager

from .client import Client, make_connection, make_connection_with_sid, build_query
from ..models import PaymentSession
import time


# ---------------------------------------------------------------------------
# Context manager for multi-step backend operations
# ---------------------------------------------------------------------------

@contextmanager
def backend_connection():
    """
    Context manager that opens a backend connection and ensures cleanup.

    Usage::

        with backend_connection() as (cli, sid):
            if cli is None:
                # handle connection failure
                ...
            response = cli.get_user(sid, user_id)
    """
    cli, sid = make_connection()
    if not cli or not sid:
        yield None, None
        return
    try:
        yield cli, sid
    finally:
        try:
            cli.close_session(sid)
            cli.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Individual wrapper functions (one connection per call)
# ---------------------------------------------------------------------------

def is_user_existing(id):
    """
    Check if a user exists in the bank database.
    Returns True if user exists, False otherwise.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.get_user(sid, id)
        cli.close_session(sid)
        cli.close()

        # Response is now a dict like {"success": True, "user": {...}} or {"success": False, "error": "..."}
        if isinstance(response, dict):
            # Check if the request was successful and user data exists
            if response.get("success") and response.get("user"):
                return True
            # If success is False or user is None, user doesn't exist
            return False

        # If response is not a dict (shouldn't happen), assume user doesn't exist
        return False

    # Connection failed
    return False


def add_user(user_id, pin):
    """
    Add a new user to the bank database.
    Returns the response dict from the server.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.add_user(sid, user_id, pin)
        cli.close_session(sid)
        cli.close()
        return response

    # Connection failed
    return {"success": False, "error": "Failed to connect to bank server"}


def delete_user(user_id):
    """
    Delete a user from the bank database.
    Returns the response dict from the server.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.delete_user(sid, user_id)
        cli.close_session(sid)
        cli.close()
        return response

    # Connection failed
    return {"success": False, "error": "Failed to connect to bank server"}


def get_user_balance(user_id):
    """
    Get the balance for a specific user.
    Returns the balance as a float, or None if error.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.get_user(sid, user_id)
        cli.close_session(sid)
        cli.close()

        # Parse response
        if isinstance(response, dict) and response.get("success"):
            user_data = response.get("user", {})
            return user_data.get("balance")

        return None

    return None


def verify_user_pin(user_id, pin):
    """
    Verify a user's PIN.
    Returns True if PIN is correct, False otherwise.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.verify(sid, user_id, pin)
        cli.close_session(sid)
        cli.close()

        # Response is like {"status": "success"} or {"status": "error", "message": "..."}
        if isinstance(response, dict):
            return response.get("status") == "success"

        return False

    return False


def set_balance(user_id, amount):
    """
    Set the balance for a specific user.
    Returns the response dict from the server.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.set_balance(sid, user_id, amount)
        cli.close_session(sid)
        cli.close()
        return response

    # Connection failed
    return {"success": False, "error": "Failed to connect to bank server"}


def get_user_attempts(user_id):
    """
    Get the attempts count for a specific user.
    Returns the attempts count as an integer, or None if error.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.get_attempts(sid, user_id)
        cli.close_session(sid)
        cli.close()

        # Parse response - can be dict like {"status": "success", "attempts": 3} or just the integer
        if isinstance(response, dict):
            if response.get("status") == "success":
                return response.get("attempts")
            return None
        elif isinstance(response, int):
            return response
        else:
            return None

    return None


def reset_attempts(user_id):
    """
    Reset the attempts count for a specific user to 0.
    Returns the response dict from the server.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.reset_attempts(sid, user_id)
        cli.close_session(sid)
        cli.close()
        return response

    # Connection failed
    return {"success": False, "error": "Failed to connect to bank server"}


# ---------------------------------------------------------------------------
# New wrapper functions for backend interactions previously inline in views
# ---------------------------------------------------------------------------

def get_user(user_id):
    """
    Get full user details from the backend.
    Returns the raw response dict.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.get_user(sid, user_id)
        cli.close_session(sid)
        cli.close()
        return response
    return {"success": False, "error": "Failed to connect to bank server"}


def add_amount(user_id, amount):
    """
    Add an amount to a user's balance.
    Returns the response dict from the server.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.add_amount(sid, user_id, amount)
        cli.close_session(sid)
        cli.close()
        return response
    return {"success": False, "error": "Failed to connect to bank server"}


def set_user_pin(user_id, pin):
    """
    Set a user's PIN on the backend.
    Returns the response dict from the server.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.set_pin(sid, user_id, pin)
        cli.close_session(sid)
        cli.close()
        return response
    return {"success": False, "error": "Failed to connect to bank server"}


def increment_user_attempts(user_id):
    """
    Increment the failed PIN attempts counter for a user.
    Returns the response dict from the server.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.increment_attempts(sid, user_id)
        cli.close_session(sid)
        cli.close()
        return response
    return {"success": False, "error": "Failed to connect to bank server"}


def get_user_by_payment_number(payment_number):
    """
    Look up a user by their account number or card number.
    Returns the raw response dict.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.get_user_by_payment_number(sid, payment_number)
        cli.close_session(sid)
        cli.close()
        return response
    return {"success": False, "error": "Failed to connect to bank server"}


def execute_transaction(from_user, to_user, amount):
    """
    Execute a transfer between two users on the backend.
    Returns the raw response dict.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.transaction(sid, from_user, to_user, amount)
        cli.close_session(sid)
        cli.close()
        return response
    return {"success": False, "error": "Failed to connect to bank server"}


def add_card(user_id, card_type='virtual'):
    """
    Add a new card for a user on the backend.
    Returns the raw response dict.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.add_card(sid, user_id, card_type)
        cli.close_session(sid)
        cli.close()
        return response
    return {"success": False, "error": "Failed to connect to bank server"}


def ensure_default_card(user_id, account_number):
    """
    Ensure a user has a default card on the backend.
    Returns the raw response dict.
    """
    cli, sid = make_connection()
    if cli and sid:
        response = cli.ensure_default_card(sid, user_id, account_number)
        cli.close_session(sid)
        cli.close()
        return response
    return {"success": False, "error": "Failed to connect to bank server"}


def create_backend_session():
    """
    Create a new backend session.
    Returns the session ID string, or None on failure.
    """
    cli, sid = make_connection()
    if cli and sid:
        cli.close()
        return sid
    return None


def check_backend_connectivity():
    """
    Check whether the banking backend is reachable.
    Returns True if connected, False otherwise.
    """
    cli, sid = make_connection()
    if cli and sid:
        try:
            cli.close_session(sid)
            cli.close()
        except Exception:
            pass
        return True
    return False
