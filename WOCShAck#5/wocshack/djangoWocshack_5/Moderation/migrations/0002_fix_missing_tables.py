"""
Repair migration: Moderation_announcement, Moderation_moderationtemplate, and
Moderation_announcementdismissal tables are missing from the database despite
0001_initial being recorded as applied. Re-creates them using IF NOT EXISTS.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Moderation', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS "Moderation_announcement" (
                            "id" char(32) NOT NULL PRIMARY KEY,
                            "title" varchar(200) NOT NULL,
                            "content" text NOT NULL,
                            "announcement_type" varchar(15) NOT NULL,
                            "display_type" varchar(10) NOT NULL,
                            "target_audience" varchar(15) NOT NULL,
                            "target_modules" text NOT NULL CHECK ((JSON_VALID("target_modules") OR "target_modules" IS NULL)),
                            "priority" integer NOT NULL,
                            "is_dismissible" bool NOT NULL,
                            "requires_acknowledgment" bool NOT NULL,
                            "starts_at" datetime NOT NULL,
                            "ends_at" datetime NULL,
                            "created_at" datetime NOT NULL,
                            "created_by_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
                        );
                        CREATE TABLE IF NOT EXISTS "Moderation_moderationtemplate" (
                            "id" char(32) NOT NULL PRIMARY KEY,
                            "name" varchar(100) NOT NULL,
                            "category" varchar(20) NOT NULL,
                            "subject" varchar(200) NOT NULL,
                            "content" text NOT NULL,
                            "placeholders" text NOT NULL CHECK ((JSON_VALID("placeholders") OR "placeholders" IS NULL)),
                            "usage_count" integer NOT NULL,
                            "created_at" datetime NOT NULL,
                            "updated_at" datetime NOT NULL,
                            "created_by_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
                        );
                        CREATE TABLE IF NOT EXISTS "Moderation_announcementdismissal" (
                            "id" char(32) NOT NULL PRIMARY KEY,
                            "acknowledged" bool NOT NULL,
                            "dismissed_at" datetime NOT NULL,
                            "announcement_id" char(32) NOT NULL REFERENCES "Moderation_announcement" ("id") DEFERRABLE INITIALLY DEFERRED,
                            "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
                        );
                    """,
                    reverse_sql="""
                        DROP TABLE IF EXISTS "Moderation_announcementdismissal";
                        DROP TABLE IF EXISTS "Moderation_moderationtemplate";
                        DROP TABLE IF EXISTS "Moderation_announcement";
                    """,
                ),
            ],
        ),
    ]
