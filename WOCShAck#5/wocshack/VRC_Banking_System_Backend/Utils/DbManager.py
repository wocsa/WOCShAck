import json
import random
import os
import time
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, CheckConstraint, ForeignKey, or_
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

try:
    from Activity.Logger import write_activity
except ImportError:
    # Fallback if Activity.Logger is not available during initialization
    def write_activity(msg):
        print(msg)

# Database file path
DB_PATH = "users.db"

# Create base class for declarative models
Base = declarative_base()


class User(Base):
    """User model representing bank account holders."""
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    ian = Column(Integer, nullable=True)
    payment_number = Column(Integer, nullable=False)
    pin = Column(Integer, nullable=False)
    attempts = Column(Integer, nullable=False)
    balance = Column(Float, nullable=False)
    history = Column(String)

    __table_args__ = (
        CheckConstraint('attempts >= 0 AND attempts <= 3', name='check_attempts'),
    )

    def to_dict(self, secure=False):
        """Convert user to dictionary."""
        return {
            "id": self.id,
            "ian": self.ian or self.payment_number,
            "account_number": self.ian or self.payment_number,
            "payment_number": self.payment_number,
            "pin": "******" if secure else self.pin,
            "attempts": self.attempts,
            "balance": self.balance,
            "history": json.loads(self.history) if self.history else []
        }


class Card(Base):
    """Card model - each user can have multiple cards linked to their account."""
    __tablename__ = 'card'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    card_number = Column(Integer, nullable=False, unique=True)
    card_type = Column(String(10), nullable=False, default='virtual')
    status = Column(String(10), nullable=False, default='active')
    created_at = Column(String(50), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "card_number": self.card_number,
            "card_type": self.card_type,
            "status": self.status,
            "created_at": self.created_at,
        }


# Database engine and session setup
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
Session = scoped_session(sessionmaker(bind=engine))

# Create tables
Base.metadata.create_all(engine)


def ensure_user_ian_column():
    """Backfill the stable ian column for existing SQLite databases."""
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info('user')")}
        if "ian" not in columns:
            connection.exec_driver_sql("ALTER TABLE user ADD COLUMN ian INTEGER")
        

def generate_unique_bank_number(session, excluded_numbers=None):
    """Generate a unique 16-digit bank identifier."""
    excluded_numbers = {int(number) for number in (excluded_numbers or [])}
    for _ in range(50):
        candidate = random.randint(10 ** 15, 10 ** 16 - 1)
        if candidate in excluded_numbers:
            continue
        if session.query(User).filter(
            or_(User.payment_number == candidate, User.ian == candidate)
        ).first():
            continue
        if session.query(Card).filter(Card.card_number == candidate).first():
            continue
        return candidate
    raise RuntimeError("Could not generate unique bank number")


def generate_unique_payment_number(session, excluded_numbers=None):
    """Generate a unique 16-digit payment/card number."""
    return generate_unique_bank_number(session, excluded_numbers)


def generate_unique_ian(session, excluded_numbers=None):
    """Generate a unique 16-digit internal account number."""
    return generate_unique_bank_number(session, excluded_numbers)


def ensure_distinct_random_ians():
    """Assign a stable random IAN to any user missing one or reusing payment_number."""
    session = Session()
    try:
        users_to_backfill = session.query(User).filter(
            or_(User.ian.is_(None), User.ian == User.payment_number)
        ).all()
        for user in users_to_backfill:
            user.ian = generate_unique_ian(session, {user.payment_number})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


ensure_user_ian_column()
ensure_distinct_random_ians()


def get_session():
    """Get a new database session."""
    return Session()


def add_user(id, pin, attempts, balance, history):
    """Add a new user to the database and create a default virtual card."""
    session = get_session()
    try:
        history_json = json.dumps(history)
        ian = generate_unique_ian(session)
        payment_number = generate_unique_payment_number(session, {ian})

        user = User(
            id=id,
            ian=ian,
            payment_number=payment_number,
            pin=int(pin),
            attempts=attempts,
            balance=balance,
            history=history_json
        )
        session.add(user)

        # Create a default virtual card that keeps the legacy payment/card number.
        default_card = Card(
            user_id=id,
            card_number=payment_number,
            card_type='virtual',
            status='active',
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        session.add(default_card)
        session.commit()
        return json.dumps({
            "success": True,
            "user_id": id,
            "ian": ian,
            "payment_number": payment_number,
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def add_card(user_id, card_type='virtual', card_number=None):
    """Generate a new card for an existing user."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return json.dumps({"success": False, "error": "User not found"})

        # Enforce max 5 cards per user
        existing = session.query(Card).filter(Card.user_id == user_id).count()
        if existing >= 5:
            return json.dumps({"success": False, "error": "Maximum card limit (5) reached"})

        # Generate unique card number if not provided
        if card_number is None:
            for _ in range(20):  # up to 20 attempts to find unique number
                candidate = random.randint(10 ** 15, 10 ** 16 - 1)
                if not session.query(Card).filter(Card.card_number == candidate).first():
                    card_number = candidate
                    break
            if card_number is None:
                return json.dumps({"success": False, "error": "Could not generate unique card number"})

        card = Card(
            user_id=user_id,
            card_number=card_number,
            card_type=card_type,
            status='active',
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        session.add(card)
        session.commit()
        return json.dumps({
            "success": True,
            "card": card.to_dict()
        })
    except Exception as e:
        session.rollback()
        return json.dumps({"success": False, "error": str(e)})
    finally:
        session.close()


def get_cards(user_id):
    """Get all cards for a user."""
    session = get_session()
    try:
        cards = session.query(Card).filter(Card.user_id == user_id).all()
        return json.dumps({
            "success": True,
            "cards": [c.to_dict() for c in cards]
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
    finally:
        session.close()


def get_card_by_number(card_number):
    """Get a card by its card number."""
    session = get_session()
    try:
        card = session.query(Card).filter(Card.card_number == int(card_number)).first()
        if card:
            return json.dumps({"success": True, "card": card.to_dict()})
        return json.dumps({"success": False, "error": "Card not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
    finally:
        session.close()


def set_card_status(card_number, status):
    """Set the status of a card (active, frozen, cancelled)."""
    if status not in ('active', 'frozen', 'cancelled'):
        return json.dumps({"success": False, "error": "Invalid status"})
    session = get_session()
    try:
        card = session.query(Card).filter(Card.card_number == int(card_number)).first()
        if not card:
            return json.dumps({"success": False, "error": "Card not found"})
        card.status = status
        session.commit()
        return json.dumps({"success": True, "card": card.to_dict()})
    except Exception as e:
        session.rollback()
        return json.dumps({"success": False, "error": str(e)})
    finally:
        session.close()


def ensure_default_card(user_id, card_number):
    """Ensure a user has at least one card using the supplied default card number.
    Called during migration for existing users who were created before the Card table existed."""
    session = get_session()
    try:
        existing = session.query(Card).filter(Card.user_id == user_id).first()
        if existing:
            return json.dumps({"success": True, "message": "Card already exists"})
        card = Card(
            user_id=user_id,
            card_number=card_number,
            card_type='virtual',
            status='active',
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        session.add(card)
        session.commit()
        return json.dumps({"success": True, "card": card.to_dict()})
    except Exception as e:
        session.rollback()
        return json.dumps({"success": False, "error": str(e)})
    finally:
        session.close()


def get_user_secure(id):
    """Get user with full details (including PIN) as JSON string."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == id).first()
        if user:
            return json.dumps({
                "success": True,
                "user": user.to_dict(secure=False)
            })
        return json.dumps({
            "success": False,
            "error": "User not found"
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def get_users():
    """Get all users as JSON string."""
    session = get_session()
    try:
        users = session.query(User).all()
        users_dict = {}
        for user in users:
            users_dict[str(user.id)] = user.to_dict(secure=False)
        return json.dumps({
            "success": True,
            "users": users_dict
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def get_user(id):
    """Get user with masked PIN as JSON string."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == id).first()
        if user:
            # Log the raw row data (simulating the original behavior)
            row_data = (user.id, user.payment_number, user.pin, user.attempts,
                        user.balance, user.history)
            write_activity(f"\n\n{row_data}\n\n")
            return json.dumps({
                "success": True,
                "user": user.to_dict(secure=True)
            })
        return json.dumps({
            "success": False,
            "error": "User not found"
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def get_user_by_payment_number(payment_number):
    """Get user by account number (payment_number) or by card number.

    First checks the stable User.ian/account_number and legacy User.payment_number.
    Falls back to Card.card_number so users can be found by any of their
    card numbers — necessary because users may have multiple cards.
    """
    print(f"DEBUG: DbManager.get_user_by_payment_number called with: {payment_number}")
    session = get_session()
    try:
        pn = int(payment_number)
        user = session.query(User).filter(
            or_(User.ian == pn, User.payment_number == pn)
        ).first()
        if not user:
            # Fallback: look up by card number
            card = session.query(Card).filter(Card.card_number == pn).first()
            if card:
                user = session.query(User).filter(User.id == card.user_id).first()
        print(f"DEBUG: Found user: {user}")
        if user:
            return json.dumps({
                "success": True,
                "user": user.to_dict(secure=True)
            })
        return json.dumps({
            "success": False,
            "error": "User not found"
        })
    except Exception as e:
        print(f"DEBUG: Exception in get_user_by_payment_number: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()

def set_pin(id, pin):
    """Update user's PIN."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == id).first()
        if user:
            user.pin = int(pin)
            session.commit()
            return json.dumps({
                "success": True,
                "message": "PIN updated successfully"
            })
        return json.dumps({
            "success": False,
            "error": "User not found"
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def get_attempts(id):
    """Get remaining attempts for a user."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == id).first()
        if user:
            return json.dumps({
                "success": True,
                "attempts": user.attempts
            })
        return json.dumps({
            "success": False,
            "error": "User not found"
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def set_attempts(id, attempts):
    """Set remaining attempts for a user."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == id).first()
        if user:
            user.attempts = int(attempts)
            session.commit()
            print(f"Rows updated: 1")
            return json.dumps({
                "success": True,
                "message": "Attempts updated successfully",
                "rows_updated": 1
            })
        else:
            print(f"Rows updated: 0")
            return json.dumps({
                "success": False,
                "error": "User not found",
                "rows_updated": 0
            })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def delete_user(id):
    """Delete a user from the database."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == id).first()
        if user:
            session.delete(user)
            session.commit()
            return json.dumps({
                "success": True,
                "message": "User deleted successfully"
            })
        return json.dumps({
            "success": False,
            "error": "User not found"
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def set_balance(id, new_balance):
    """Set user's balance to a specific amount."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == id).first()
        if user:
            user.balance = new_balance
            session.commit()
            return json.dumps({
                "success": True,
                "message": "Balance updated successfully",
                "new_balance": new_balance
            })
        return json.dumps({
            "success": False,
            "error": "User not found"
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def add_balance(id, amount):
    """Add amount to user's balance."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == id).first()
        if user:
            user.balance += amount
            session.commit()
            return json.dumps({
                "success": True,
                "message": "Balance added successfully",
                "new_balance": user.balance
            })
        return json.dumps({
            "success": False,
            "error": "User not found"
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def sub_balance(id, amount):
    """Subtract amount from user's balance if sufficient funds exist."""
    import sqlite3 as _sqlite3

    # --- STEP 1: read balance (transaction ends immediately after) ---
    conn = _sqlite3.connect(DB_PATH, timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT balance FROM user WHERE id = ?", (id,))
    row = cur.fetchone()
    conn.close()

    if row is None:
        return json.dumps({"success": False, "error": "User not found"})

    import threading as _threading
    balance = row[0]
    print(f"[TOCTOU] thread={_threading.current_thread().name} read balance={balance}", flush=True)
    if balance < amount:
        return json.dumps({"success": False, "error": "Insufficient balance"})

    time.sleep(2)

    # --- STEP 2: write (separate connection, no re-check) ---
    conn2 = _sqlite3.connect(DB_PATH, timeout=5)
    cur2 = conn2.cursor()
    cur2.execute("UPDATE user SET balance = ? WHERE id = ?", (balance - amount, id))
    conn2.commit()
    conn2.close()

    return json.dumps({"success": True, "message": "Balance deducted successfully", "new_balance": balance - amount})


def add_transaction_history(id, new_entry):
    """Add a transaction to user's history."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == id).first()
        if user is None:
            print("User not found.")
            return json.dumps({
                "success": False,
                "error": "User not found"
            })

        history_list = []
        if user.history:
            try:
                history_list = json.loads(user.history)
            except json.JSONDecodeError:
                print("Corrupted history data. Starting fresh.")

        history_list.append(new_entry)
        user.history = json.dumps(history_list)
        session.commit()
        return json.dumps({
            "success": True,
            "message": "Transaction added to history"
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


def search_user_by_payment(payment_number):
    """Search user by payment number."""
    try:
        with engine.connect() as connection:
            query = f"SELECT id, payment_number, pin, attempts, balance FROM user WHERE payment_number = {payment_number}"
            result = connection.exec_driver_sql(query)
            row = result.fetchone()
            if row:
                return json.dumps({
                    "success": True,
                    "user": {
                        "id": row[0],
                        "payment_number": row[1],
                        "pin": row[2],
                        "attempts": row[3],
                        "balance": row[4]
                    }
                })
            return json.dumps({"success": False, "error": "User not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def initialize_users_db(db_path: str = DB_PATH):
    """Create (or overwrite) the users.db and populate it with predefined users.

    Each user will have:
      - id: matches Django user ID
      - ian: random stable 16-digit account identifier
      - payment_number: predefined 16-digit int
      - pin: predefined 6-digit int
      - attempts: 0 (no failed attempts initially)
      - balance: predefined starting balance
      - history: empty list

    This function re-creates the database file to ensure a fresh start.
    Returns JSON string with created users list.
    """
    # Predefined users matching the Django accounts from setup_database.py
    PREDEFINED_BANK_USERS = [
        {
            'id': 1,
            'payment_number': 1111111111111111,
            'pin': 999999,  # admin user
            'balance': 100000.00,
        },
        {
            'id': 2,
            'payment_number': 2222222222222222,
            'pin': 123456,  # johndoe
            'balance': 5000.00,
        },
        {
            'id': 3,
            'payment_number': 3333333333333333,
            'pin': 234567,  # janedoe
            'balance': 7500.00,
        },
        {
            'id': 4,
            'payment_number': 4444444444444444,
            'pin': 345678,  # bobsmith
            'balance': 3000.00,
        },
        {
            'id': 5,
            'payment_number': 5555555555555555,
            'pin': 456789,  # alicejohnson
            'balance': 10000.00,
        },
        {
            'id': 6,
            'payment_number': 6666666666666666,
            'pin': 567890,  # charliebrown
            'balance': 2500.00,
        },
    ]

    try:
        # Remove existing DB if present
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception as e:
        print(f"Warning: could not remove existing db {db_path}: {e}")
        return json.dumps({
            "success": False,
            "error": f"Could not remove existing database: {str(e)}"
        })

    try:
        # Create new engine for the specified path
        local_engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Base.metadata.create_all(local_engine)

        LocalSession = sessionmaker(bind=local_engine)
        session = LocalSession()

        created = []
        for user_data in PREDEFINED_BANK_USERS:
            ian = generate_unique_ian(session, {user_data['payment_number']})
            user = User(
                id=user_data['id'],
                ian=ian,
                payment_number=user_data['payment_number'],
                pin=user_data['pin'],
                attempts=0,
                balance=user_data['balance'],
                history=json.dumps([])
            )
            session.add(user)

            # Create default virtual card (card_number = account payment_number)
            default_card = Card(
                user_id=user_data['id'],
                card_number=user_data['payment_number'],
                card_type='virtual',
                status='active',
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            )
            session.add(default_card)

            created.append({
                "id": user_data['id'],
                "ian": ian,
                "payment_number": user_data['payment_number'],
                "pin": user_data['pin'],
                "attempts": 0,
                "balance": user_data['balance'],
                "history": [],
            })
            print(f"Created bank account for user ID {user_data['id']}: "
                  f"Account #{ian}, Balance: ${user_data['balance']}")

        session.commit()
        session.close()

        # Reconnect global engine and session to the new DB file
        global engine, Session
        engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Session = scoped_session(sessionmaker(bind=engine))

        print(f"\nSummary: Created {len(created)} bank accounts")
        return json.dumps({
            "success": True,
            "message": f"Created {len(created)} bank accounts",
            "users": created
        })

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })
