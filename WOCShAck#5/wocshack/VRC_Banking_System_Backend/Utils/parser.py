from datetime import datetime
import time
from . import DbManager
from Activity.Logger import log, write_audit
import json
from sqlalchemy.exc import SQLAlchemyError

sessions = {}


def cleanup_old_sids(ttl=300):
    now = time.time()
    for sid in list(sessions):
        if now - sessions[sid] > ttl:
            del sessions[sid]


def is_in_session(sid):
    if sid in sessions:
        return True
    return False


def create_session(data):
    try:
        sid = data["sid"]
        sessions[sid] = time.time()
        log("sescr", sid=sid)
        return {"status": "success"}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}


def close_session(data):
    try:
        sid = data["sid"]
        if sid in sessions:
            del sessions[sid]
            log("sescl", sid=sid)
            return {"status": "success", "message": f"Session {sid} closed."}
        else:
            return {"status": "error", "message": "Session ID not found."}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}


def increment_attempts(data):
    try:
        user_id = data["user_id"]
        attempts_result = DbManager.get_attempts(user_id)

        # Parse the JSON string returned by DbManager
        if isinstance(attempts_result, str):
            attempts_result = json.loads(attempts_result)

        # Extract attempts value
        if isinstance(attempts_result, dict):
            if not attempts_result.get("success"):
                return {"status": "error", "message": attempts_result.get("error", "Failed to get attempts")}
            att = attempts_result.get("attempts", 0)
        else:
            att = attempts_result

        if 0 <= att <= 3:
            DbManager.set_attempts(user_id, att + 1)
        else:
            DbManager.set_attempts(user_id, 0)

        log("inca", id=user_id)
        return {"status": "success"}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse attempts data"}


def reset_attempts(data):
    try:
        user_id = data["user_id"]
        result = DbManager.set_attempts(user_id, 0)

        # Parse the JSON string returned by DbManager
        if isinstance(result, str):
            result = json.loads(result)

        log("resa", id=user_id)

        if isinstance(result, dict) and result.get("success"):
            return {"status": "success"}
        return {"status": "error", "message": result.get("error", "Failed to reset attempts")}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse reset response"}


def transaction(data):
    try:
        write_audit(f"Transfer from {data.get('from')} to {data.get('to')} amount {data.get('amount')}")

        # Subtract balance from sender
        sub_result = DbManager.sub_balance(data["from"], data["amount"])
        if isinstance(sub_result, str):
            sub_result = json.loads(sub_result)
        if isinstance(sub_result, dict) and not sub_result.get("success"):
            return {"status": "error", "message": sub_result.get("error", "Transaction failed")}

        # Add transaction history for sender
        DbManager.add_transaction_history(data["from"],
                                          f"{datetime.now()} - You -> -{data['amount']} -> {data['to']}")

        # Add balance to receiver
        DbManager.add_balance(data["to"], data["amount"])

        # Add transaction history for receiver
        DbManager.add_transaction_history(data["to"],
                                          f"{datetime.now()} - {data['from']} -> +{data['amount']} -> You")

        log("tr", origin=data["from"], destination=data["to"], amount=data["amount"])
        return {"status": "success"}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse transaction response"}


def add_user(data):
    try:
        user_id = data["user_id"]
        pin = data["pin"]
        result = DbManager.add_user(user_id, pin, 0, 0, [])

        # Parse the JSON string returned by DbManager
        if isinstance(result, str):
            result = json.loads(result)

        log("adu", id=user_id)

        if isinstance(result, dict) and result.get("success"):
            return {"status": "success"}
        return {"status": "error", "message": result.get("error", "Failed to add user")}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse add user response"}


def delete_user(data):
    try:
        result = DbManager.delete_user(data["user_id"])

        # Parse the JSON string returned by DbManager
        if isinstance(result, str):
            result = json.loads(result)

        log("delu", id=data["user_id"])

        if isinstance(result, dict) and result.get("success"):
            return {"status": "success"}
        return {"status": "error", "message": result.get("error", "Failed to delete user")}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse delete response"}


def get_user_secure(data):
    try:
        user = DbManager.get_user_secure(data["user_id"])
        log("getu", id=data["user_id"])
        # Parse the JSON string returned by DbManager if needed
        if isinstance(user, str):
            user = json.loads(user)
        return user
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse user data"}


def get_user(data):
    try:
        user = DbManager.get_user(data["user_id"])
        log("getu", id=data["user_id"])
        # Parse the JSON string returned by DbManager if needed
        if isinstance(user, str):
            user = json.loads(user)
        return user
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse user data"}


def add_card(data):
    try:
        user_id = data["user_id"]
        card_type = data.get("card_type", "virtual")
        result = DbManager.add_card(user_id, card_type)
        if isinstance(result, str):
            result = json.loads(result)
        log("addcard", id=user_id)
        return result
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse response"}


def get_cards(data):
    try:
        user_id = data["user_id"]
        result = DbManager.get_cards(user_id)
        if isinstance(result, str):
            result = json.loads(result)
        return result
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse response"}


def get_card_by_number(data):
    try:
        card_number = data["card_number"]
        result = DbManager.get_card_by_number(card_number)
        if isinstance(result, str):
            result = json.loads(result)
        return result
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse response"}


def set_card_status(data):
    try:
        card_number = data["card_number"]
        status = data["status"]
        result = DbManager.set_card_status(card_number, status)
        if isinstance(result, str):
            result = json.loads(result)
        log("setcardstatus", card=card_number, status=status)
        return result
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse response"}


def ensure_default_card(data):
    try:
        user_id = data["user_id"]
        account_number = data["account_number"]
        result = DbManager.ensure_default_card(user_id, account_number)
        if isinstance(result, str):
            result = json.loads(result)
        return result
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse response"}


def get_user_by_payment_number(data):
    try:
        print(f"DEBUG: get_user_by_payment_number called with data: {data}")
        payment_number = data["payment_number"]
        print(f"DEBUG: Looking for payment_number: {payment_number}")

        result = DbManager.get_user_by_payment_number(payment_number)
        print(f"DEBUG: DbManager returned: {result}")

        if isinstance(result, str):
            result = json.loads(result)

        print(f"DEBUG: Returning result: {result}")
        return result
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse user data"}

def get_users():
    try:
        users = DbManager.get_users()
        log("getu", id=None)
        # Parse the JSON string returned by DbManager if needed
        if isinstance(users, str):
            users = json.loads(users)
        return users
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse users data"}


def get_attempts(data):
    try:
        attempts_result = DbManager.get_attempts(data.get("user_id"))
        # Parse the JSON string returned by DbManager if needed
        if isinstance(attempts_result, str):
            attempts_result = json.loads(attempts_result)

        # If attempts_result has the attempts value, extract it
        if isinstance(attempts_result, dict) and "attempts" in attempts_result:
            return {"status": "success", "attempts": attempts_result["attempts"]}

        return {"status": "success", "attempts": attempts_result}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse attempts data"}


def set_pin(data):
    try:
        result = DbManager.set_pin(data["user_id"], data["pin"])
        log("sp", id=data["user_id"])
        # Parse the JSON string returned by DbManager if needed
        if isinstance(result, str):
            result = json.loads(result)
        # Ensure we return a consistent format
        if isinstance(result, dict) and result.get("success"):
            return {"status": "success"}
        return {"status": "error", "message": result.get("error", "Failed to set PIN")}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse set_pin response"}


def add_amount(data):
    try:
        result = DbManager.add_balance(data["user_id"], data["amount"])
        log("ad", id=data["user_id"], amount=data["amount"])
        # Parse the JSON string returned by DbManager if needed
        if isinstance(result, str):
            result = json.loads(result)
        # Ensure we return a consistent format
        if isinstance(result, dict) and result.get("success"):
            return {"status": "success"}
        return {"status": "error", "message": result.get("error", "Failed to add amount")}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse add_amount response"}


def set_balance(data):
    try:
        result = DbManager.set_balance(data["user_id"], data["amount"])
        log("sb", id=data["user_id"], amount=data["amount"])
        # Parse the JSON string returned by DbManager if needed
        if isinstance(result, str):
            result = json.loads(result)
        # Ensure we return a consistent format
        if isinstance(result, dict) and result.get("success"):
            return {"status": "success"}
        return {"status": "error", "message": result.get("error", "Failed to set balance")}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse set_balance response"}


def verify_pin(data):
    try:
        user_result = DbManager.get_user_secure(data["user_id"])
        # Parse the JSON string returned by DbManager if needed
        if isinstance(user_result, str):
            user_result = json.loads(user_result)

        # Extract user dict from the response
        if isinstance(user_result, dict) and "user" in user_result:
            user = user_result["user"]
        else:
            user = user_result

        if str(user["pin"]) == data["pin"]:
            return {"status": "success"}
        return {"status": "error", "message": "Invalid PIN"}
    except SQLAlchemyError as e:
        log("err", error=str(e))
        return {"status": "error", "message": str(e)}
    except KeyError as e:
        log("err", error=f"Missing field {e}")
        return {"status": "error", "message": f"Missing field {e}"}
    except json.JSONDecodeError as e:
        log("err", error=f"JSON decode error: {e}")
        return {"status": "error", "message": "Failed to parse user data"}


def parse(data):
    """
    Expects data as JSON string with at least a "command" field.
    Other fields depend on command.
    Always returns a dictionary.
    """
    try:
        parsed_data = json.loads(data)
        command = parsed_data.get("command")

        if command == "ping":
            return {"status": "success"}

        if command == "sescr":
            return create_session(parsed_data)

        sid = parsed_data.get('sid')

        cleanup_old_sids()

        if not is_in_session(sid):
            return {"error": "No session"}

        if command == "check":
            return {"status": "success"}

        sessions[sid] = time.time()

        if command == "tr":
            return transaction(parsed_data)
        elif command == "adu":
            return add_user(parsed_data)
        elif command == "delu":
            return delete_user(parsed_data)
        elif command == "getu":
            return get_user(parsed_data)
        elif command == "getau":
            return get_users()
        elif command == "getubypn":  # Get User By Payment Number
            return get_user_by_payment_number(parsed_data)
        elif command == "ad":
            return add_amount(parsed_data)
        elif command == "sb":
            return set_balance(parsed_data)
        elif command == "sp":
            return set_pin(parsed_data)
        elif command == "ver":
            return verify_pin(parsed_data)
        elif command == "sescl":
            return close_session(parsed_data)
        elif command == "inca":
            return increment_attempts(parsed_data)
        elif command == "resa":
            return reset_attempts(parsed_data)
        elif command == "getat":
            return get_attempts(parsed_data)
        elif command == "addcard":
            return add_card(parsed_data)
        elif command == "getcards":
            return get_cards(parsed_data)
        elif command == "getcardbn":
            return get_card_by_number(parsed_data)
        elif command == "setcardstatus":
            return set_card_status(parsed_data)
        elif command == "ensuredefaultcard":
            return ensure_default_card(parsed_data)
        elif command == "su":
            payment_number = parsed_data.get("payment_number", "")
            result = DbManager.search_user_by_payment(payment_number)
            if isinstance(result, str):
                import json as _json
                result = _json.loads(result)
            return result
        elif command == "try":
            return {"status": "success", "message": "Try passed successfully"}
        else:
            log("err", error=f"Unknown command {command}")
            return {"status": "error", "message": f"Unknown command {command}"}

    except json.JSONDecodeError:
        log("err", error="Invalid JSON")
        return {"status": "error", "message": "Invalid JSON"}

    except Exception as e:
        log("err", error=str(e))
        return {"status": "error", "message": "Server error", "error": str(e)}
