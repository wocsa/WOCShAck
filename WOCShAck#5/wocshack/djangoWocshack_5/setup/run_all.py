"""
Main setup orchestrator.

Runs all setup steps in order from the djangoWocshack_5/ working directory:
  1. makemigrations
  2. migrate
  3. setup/setup_webmail.py   — wait for webmail service, create accounts, send welcome emails
  4. setup/setup_database.py  — Django users, profiles, API keys, bank accounts, CSS files
  5. setup/seed/seed_all.py    — populate forum, community, marketplace, and other demo content

Exit code mirrors the first failed step, or 0 on full success.
"""
import os
import subprocess
import sys

# Always run from djangoWocshack_5/ regardless of where this script is invoked from
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env():
    env = os.environ.copy()
    env['PYTHONPATH'] = BASE_DIR + os.pathsep + env.get('PYTHONPATH', '')
    return env


def run(args, description):
    print()
    print("=" * 80)
    print(f"  {description}")
    print("=" * 80)
    result = subprocess.run(args, cwd=BASE_DIR, env=_env())
    if result.returncode != 0:
        print(f"\n[X] Step failed: {description} (exit code {result.returncode})")
        sys.exit(result.returncode)


def main():
    print("=" * 80)
    print("  V.R.C Platform — Full Setup")
    print("=" * 80)

    run([sys.executable, "manage.py", "makemigrations"], "Applying makemigrations")
    run([sys.executable, "manage.py", "migrate"],        "Applying migrations")
    run([sys.executable, "setup/setup_webmail.py"],      "Setting up webmail accounts")
    run([sys.executable, "setup/setup_database.py"],     "Setting up database")
    run([sys.executable, "setup/seed/seed_all.py", "--flush"], "Seeding demo data")

    print()
    print("=" * 80)
    print("  [+] All setup steps completed successfully.")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
