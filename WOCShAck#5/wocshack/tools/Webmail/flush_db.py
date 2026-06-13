#!/usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path

# Add src directory to path to allow importing Backend
SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

from Backend import Database

DB_PATH = SRC_DIR / "DataBase" / "DataBase.db"
TABLES = ["Emails", "users"]


def main():
    parser = argparse.ArgumentParser(
        description="Flush the webmail database tables."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm deletion of data. Without this flag the script will exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which tables would be cleared without deleting.",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        default=TABLES,
        help="Specify which tables to delete (default: all known tables).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not DB_PATH.exists():
        logging.error("Database file %s does not exist.", DB_PATH)
        sys.exit(1)

    if args.dry_run:
        logging.info("Dry-run mode: no changes will be made.")
        logging.info("Tables that would be cleared: %s", ", ".join(args.tables))
        sys.exit(0)
        
    if not args.confirm:
        logging.warning(
            "Deletion not confirmed. Use --confirm to proceed."
        )
        sys.exit(0)

    db = None
    try:
        db = Database(str(DB_PATH))
        cursor = db.cursor
        # Verify tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        )
        existing = {row[0] for row in cursor.fetchall()}
        missing = set(args.tables) - existing
        if missing:
            logging.warning("The following tables do not exist: %s", ", ".join(missing))

        # Delete data
        cursor.execute("PRAGMA foreign_keys = OFF;")
        for table in args.tables:
            if table in existing:
                cursor.execute(f"DELETE FROM {table};")
                logging.info("All records deleted from %s table.", table)
            else:
                logging.info("Skipping missing table %s.", table)
        cursor.execute("PRAGMA foreign_keys = ON;")
        db.conn.commit()

        cursor.execute("VACUUM;")
        logging.info("Database vacuumed.")
    except Exception as exc:
        logging.exception("An error occurred while flushing the database: %s", exc)
        sys.exit(1)
    finally:
        if db:
            db.conn.close()
            logging.info("Database connection closed")

    logging.info("Database flush completed successfully.")


if __name__ == "__main__":
    main()
