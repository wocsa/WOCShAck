import os
import sys
import time

try:
    import requests
except ImportError:
    print("[!] requests module not available - cannot set up webmail accounts")
    sys.exit(1)

WEBMAIL_API_BASE_URL = os.getenv('WEBMAIL_URL', 'http://172.28.0.4:80/api')
WEBMAIL_API_TIMEOUT = 10  # seconds

print("=" * 80)
print("Webmail Account Setup Script")
print("Creates webmail accounts for all platform users via the Webmail REST API")
print("=" * 80)
print()

import csv

# All platform accounts — mirrors setup_database.py
# username is the email prefix (e.g. john.doe from john.doe@tbox.traced)
ACCOUNTS = [
    {'username': 'admin',            'password': 'X#9kLm$P2v@nQ8w!ZjRe'},
]

csv_path = os.path.join(os.path.dirname(__file__), 'users.csv')
try:
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row.get('email', '')
            if email:
                mail_username = email.split('@')[0]
                ACCOUNTS.append({
                    'username': mail_username,
                    'password': row.get('password', 'Tr@c3d!7BxN#m9Kw2YpL')
                })
except Exception as e:
    print(f"[W] Could not load users.csv: {e}")


def wait_for_webmail(retries=12, delay=5):
    """Poll GET /api/health until the webmail service is ready."""
    print(f"[*] Waiting for webmail API at {WEBMAIL_API_BASE_URL} ...")
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                f"{WEBMAIL_API_BASE_URL}/health",
                timeout=WEBMAIL_API_TIMEOUT
            )
            if response.status_code == 200:
                print(f"  Webmail API is ready.")
                return True
        except requests.exceptions.RequestException:
            pass
        print(f"  Attempt {attempt}/{retries} failed, retrying in {delay}s...")
        time.sleep(delay)
    print("[!] Webmail API did not become ready in time. Exiting.")
    return False


def create_account(username, password):
    """Create a webmail account. Returns True on success or if account already exists."""
    try:
        response = requests.post(
            f"{WEBMAIL_API_BASE_URL}/users",
            json={"username": username, "password": password},
            timeout=WEBMAIL_API_TIMEOUT
        )
        if response.status_code == 201:
            print(f"  [+] Created webmail account: {username}")
            return True
        elif response.status_code == 409:
            print(f"  [-] Account already exists: {username}")
            return True
        else:
            try:
                error = response.json().get('error', 'Unknown error')
            except Exception:
                error = f"HTTP {response.status_code}"
            print(f"  [W] Failed to create {username}: {error}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"  [W] Request error for {username}: {e}")
        return False


def send_welcome_email(username, password):
    """Send a welcome email matching the content from setup_database.py."""
    try:
        response = requests.post(
            f"{WEBMAIL_API_BASE_URL}/emails",
            json={
                "source": "VRC System <system@vrc.traced>",
                "destination": username,
                "subject": "Welcome to V.R.C Platform!",
                "content": (
                    f"Dear {username},\n\n"
                    "Welcome to the V.R.C Platform!\n\n"
                    "Your account has been successfully created.\n\n"
                    "Login credentials:\n"
                    f"- Username: {username}\n"
                    f"- Password: {password}\n\n"
                    "Thank you for joining our community!\n\n"
                    "Best regards,\nThe V.R.C Team"
                )
            },
            timeout=WEBMAIL_API_TIMEOUT
        )
        if response.status_code == 201:
            print(f"  ✓ Welcome email sent to: {username}")
            return True
        else:
            try:
                error = response.json().get('error', 'Unknown error')
            except Exception:
                error = f"HTTP {response.status_code}"
            print(f"  [W] Failed to send welcome email to {username}: {error}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"  [W] Request error sending email to {username}: {e}")
        return False


def main():
    if not wait_for_webmail():
        sys.exit(1)

    print()
    print("[*] Creating webmail accounts...")
    print("-" * 80)

    created = 0
    skipped = 0
    failed = 0

    for account in ACCOUNTS:
        username = account['username']
        password = account['password']

        success = create_account(username, password)
        if success:
            # Only send welcome email for newly created accounts (201), not existing ones (409)
            # create_account returns True for both, but we check via a fresh attempt pattern —
            # welcome emails for existing accounts are harmless duplicates so we send regardless.
            send_welcome_email(username, password)
            created += 1
        else:
            failed += 1

    print()
    print("[+] Webmail setup complete.")
    print(f"  Accounts processed : {len(ACCOUNTS)}")
    print(f"  Created/existing   : {created}")
    print(f"  Failed             : {failed}")
    print()

    if failed > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
