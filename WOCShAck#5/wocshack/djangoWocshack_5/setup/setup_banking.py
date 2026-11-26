"""
Banking Backend Account Setup

Creates bank accounts for all platform users via the banking backend TCP API.
Mirrors setup_webmail.py: waits for the service, then creates accounts idempotently.

User IDs are sequential starting from 1 (admin) because db.sqlite3 is always
started from the committed clean state.
"""
import os
import sys
import socket
import time
import csv

# Ensure /app is on the path so Django can find the djangoWocshack_5 settings package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')

import django
django.setup()

from Bank.Utils import external_calls

BANKING_HOST = os.getenv('BANKING_HOST', '172.28.0.2')
BANKING_PORT = 7051
BANKING_TIMEOUT = 3
WAIT_RETRIES = 12
WAIT_DELAY = 5

print("=" * 80)
print("Banking Backend Account Setup Script")
print("Creates bank accounts for all platform users via the banking TCP API")
print("=" * 80)
print()

# Admin account (always ID 1 — first user created by setup_database.py)
ACCOUNTS = [
    {'user_id': 1, 'username': 'admin', 'pin': '999999', 'balance': 100000.00},
]

# CSV users get sequential IDs starting from 2, in CSV order
csv_path = os.path.join(os.path.dirname(__file__), 'users.csv')
try:
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            ACCOUNTS.append({
                'user_id': idx,
                'username': row['username'],
                'pin': row['bank_pin'],
                'balance': float(row['initial_balance']),
            })
except Exception as e:
    print(f"[!] Could not load users.csv: {e}")
    sys.exit(1)


def wait_for_banking(retries=WAIT_RETRIES, delay=WAIT_DELAY):
    print(f"[*] Waiting for banking backend at {BANKING_HOST}:{BANKING_PORT} ...")
    for attempt in range(1, retries + 1):
        try:
            with socket.create_connection((BANKING_HOST, BANKING_PORT), timeout=BANKING_TIMEOUT):
                print("  Banking backend is ready.")
                return True
        except (socket.error, OSError):
            pass
        print(f"  Attempt {attempt}/{retries} failed, retrying in {delay}s...")
        time.sleep(delay)
    print("[!] Banking backend did not become ready in time. Exiting.")
    return False


def create_bank_account(user_id, username, pin, balance):
    """Create a bank account. Returns True on success or if account already exists."""
    try:
        if external_calls.is_user_existing(user_id):
            print(f"  [-] Account already exists: {username} (ID: {user_id})")
            return True

        result = external_calls.add_user(user_id=user_id, pin=pin)
        if result and result.get('status') == 'success':
            time.sleep(1)
            external_calls.set_balance(user_id=user_id, amount=balance)
            print(f"  [+] Created bank account: {username} (ID: {user_id}, PIN: {pin}, Balance: ${balance:.2f})")
            return True

        error = result.get('error', 'Unknown error') if result else 'No response'
        print(f"  [W] Failed to create account for {username}: {error}")
        return False
    except Exception as e:
        print(f"  [W] Error creating account for {username}: {e}")
        return False


def main():
    if not wait_for_banking():
        sys.exit(1)

    print()
    print("[*] Creating bank accounts...")
    print("-" * 80)

    created = 0
    skipped = 0
    failed = 0

    for account in ACCOUNTS:
        success = create_bank_account(
            account['user_id'],
            account['username'],
            account['pin'],
            account['balance'],
        )
        if success:
            created += 1
        else:
            failed += 1

    print()
    print("[+] Banking setup complete.")
    print(f"  Accounts processed : {len(ACCOUNTS)}")
    print(f"  Created/existing   : {created}")
    print(f"  Failed             : {failed}")
    print()

    if failed > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
