"""
Repair migration: Forum_announcement and Forum_moderationtemplate tables are
missing from the database despite their migrations being recorded as applied.
Re-creates them using IF NOT EXISTS so it is safe to run on databases that
already have the tables.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Forum', '0004_forumrole_stickypost_tag_forumimage_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS "Forum_moderationtemplate" (
                            "id" char(32) NOT NULL PRIMARY KEY,
                            "name" varchar(100) NOT NULL UNIQUE,
                            "template_type" varchar(20) NOT NULL,
                            "subject" varchar(200) NOT NULL,
                            "content" text NOT NULL,
                            "is_active" bool NOT NULL,
                            "usage_count" integer unsigned NOT NULL CHECK ("usage_count" >= 0),
                            "created_at" datetime NOT NULL,
                            "updated_at" datetime NOT NULL,
                            "created_by_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
                        );
                        CREATE TABLE IF NOT EXISTS "Forum_announcement" (
                            "id" char(32) NOT NULL PRIMARY KEY,
                            "title" varchar(200) NOT NULL,
                            "message" text NOT NULL,
                            "announcement_type" varchar(20) NOT NULL,
                            "is_active" bool NOT NULL,
                            "is_dismissible" bool NOT NULL,
                            "audience" varchar(20) NOT NULL,
                            "starts_at" datetime NOT NULL,
                            "ends_at" datetime NULL,
                            "priority" smallint unsigned NOT NULL CHECK ("priority" >= 0),
                            "created_at" datetime NOT NULL,
                            "updated_at" datetime NOT NULL,
                            "view_count" integer unsigned NOT NULL CHECK ("view_count" >= 0),
                            "dismiss_count" integer unsigned NOT NULL CHECK ("dismiss_count" >= 0),
                            "created_by_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED,
                            "target_category_id" char(32) NULL REFERENCES "Forum_category" ("id") DEFERRABLE INITIALLY DEFERRED
                        );
                        CREATE INDEX IF NOT EXISTS "Forum_announcement_created_at_054b8749" ON "Forum_announcement" ("created_at");
                        CREATE INDEX IF NOT EXISTS "Forum_announcement_created_by_id_142b7d63" ON "Forum_announcement" ("created_by_id");
                        CREATE INDEX IF NOT EXISTS "Forum_announcement_target_category_id_e24a816a" ON "Forum_announcement" ("target_category_id");
                        CREATE INDEX IF NOT EXISTS "Forum_annou_is_acti_f9ab32_idx" ON "Forum_announcement" ("is_active", "priority" DESC, "starts_at" DESC);
                        CREATE INDEX IF NOT EXISTS "Forum_annou_target__49b085_idx" ON "Forum_announcement" ("target_category_id", "is_active");
                    """,
                    reverse_sql='DROP TABLE IF EXISTS "Forum_announcement"; DROP TABLE IF EXISTS "Forum_moderationtemplate";',
                ),
            ],
        ),
    ]
