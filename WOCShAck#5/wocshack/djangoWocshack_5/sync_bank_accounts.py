"""
Sync Bank Accounts - Create bank accounts for existing Django users

This script creates bank accounts for Django users who don't have one yet.
Useful when:
- Users were created before the centralized setup_database.py
- Bank backend was down during user creation
- Manual user creation via Django admin

Usage:
    python sync_bank_accounts.py
"""

import os
import django
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings')
django.setup()

from django.contrib.auth.models import User
from Bank.Utils import external_calls

print("=" * 80)
print("Bank Account Sync Script")
print("Creates bank accounts for existing Django users")
print("=" * 80)
print()


def sync_bank_accounts():
    """Create bank accounts for all Django users who don't have one"""

    # Default PINs for different user types
    DEFAULT_PINS = {
        'admin': '999999',
        'johndoe': '123456',
        'janedoe': '234567',
        'bobsmith': '345678',
        'alicejohnson': '456789',
        'charliebrown': '567890',
    }

    # Default balances
    DEFAULT_BALANCES = {
        'admin': 100000.00,
        'johndoe': 5000.00,
        'janedoe': 7500.00,
        'bobsmith': 3000.00,
        'alicejohnson': 10000.00,
        'charliebrown': 2500.00,
    }

    users = User.objects.all().order_by('id')

    if not users.exists():
        print("✗ No Django users found. Please run setup_database.py first.")
        return

    print(f"Found {users.count()} Django user(s)")
    print("-" * 80)
    print()

    created = 0
    skipped = 0
    failed = 0

    for user in users:
        username = user.username
        user_id = user.id

        # Check if bank account exists
        try:
            bank_user = external_calls.get_user(user_id)

            if bank_user is not None:
                print(f"  - {username} (ID: {user_id}): Bank account already exists ✓")
                skipped += 1
                continue

            # Determine PIN and balance
            if username in DEFAULT_PINS:
                pin = DEFAULT_PINS[username]
                balance = DEFAULT_BALANCES[username]
            elif user.is_superuser:
                pin = '999999'
                balance = 100000.00
            else:
                # Generate default PIN based on user ID
                pin = f"{user_id:06d}"  # e.g., user ID 7 → PIN 000007
                balance = 1000.00

            # Create bank account
            result = external_calls.add_user(user_id=user_id, pin=pin)

            if result and result.get('status') == 'success':
                print(f"  ✓ {username} (ID: {user_id}): Bank account created")
                print(f"    PIN: {pin}, Balance: ${balance:.2f}")

                # Set initial balance
                time.sleep(1)
                external_calls.set_balance(user_id=user_id, amount=balance)
                created += 1
            else:
                error = result.get('error', 'Unknown error') if result else 'No response'
                print(f"  ✗ {username} (ID: {user_id}): Failed to create - {error}")
                failed += 1

        except Exception as e:
            print(f"  ✗ {username} (ID: {user_id}): Exception - {e}")
            failed += 1

        time.sleep(0.5)  # Rate limiting

    print()
    print("=" * 80)
    print("Sync Summary")
    print("=" * 80)
    print(f"  Created:  {created}")
    print(f"  Skipped:  {skipped}")
    print(f"  Failed:   {failed}")
    print()

    if created > 0:
        print("=" * 80)
        print("New Bank Accounts Created")
        print("=" * 80)
        print()
        print("If using default credentials:")
        print("  admin           → PIN: 999999")
        print("  johndoe         → PIN: 123456")
        print("  janedoe         → PIN: 234567")
        print("  bobsmith        → PIN: 345678")
        print("  alicejohnson    → PIN: 456789")
        print("  charliebrown    → PIN: 567890")
        print()
        print("Other users      → PIN: User ID padded to 6 digits (e.g., ID 7 = 000007)")
        print()
        print("=" * 80)

    if failed > 0:
        print()
        print("⚠ Some accounts failed to create.")
        print("  - Check if the banking backend is running")
        print("  - Verify network connectivity (172.28.0.2:7051)")
        print()


def main():
    try:
        sync_bank_accounts()
    except Exception as e:
        print(f"\n✗ Sync failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
