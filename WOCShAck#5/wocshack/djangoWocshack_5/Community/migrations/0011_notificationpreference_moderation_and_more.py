# Generated migration for issue #26 — add moderation preference flag
# and REVIEW_SUBMITTED notification type (choices-only, no schema change).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('community_engagement', '0010_notificationpreference_advertisements_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationpreference',
            name='moderation',
            field=models.BooleanField(default=True),
        ),
        # NotifType is a TextChoices used in a CharField — adding a new choice
        # does not require a schema change, but we record the field alteration
        # so the migration state stays in sync with the model.
        migrations.AlterField(
            model_name='notification',
            name='notif_type',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('friend_request', "Demande d'ami"),
                    ('friend_accept', 'Demande acceptée'),
                    ('new_message', 'Nouveau message'),
                    ('level_up', 'Niveau supérieur'),
                    ('achievement', 'Achievement débloqué'),
                    ('daily_reward', 'Récompense journalière'),
                    ('new_follower', 'Nouveau suiveur'),
                    ('streak_broken', 'Streak perdu'),
                    ('streak_shield', 'Shield utilisé'),
                    ('system', 'Système'),
                    ('new_blog_post', 'Nouveau article'),
                    ('blog_comment', 'Commentaire blog'),
                    ('forum_reply', 'Réponse forum'),
                    ('forum_mention', 'Mention forum'),
                    ('order_update', 'Mise à jour commande'),
                    ('ad_status', 'Statut publicité'),
                    ('new_review', 'Nouvel avis'),
                    ('mission_assigned', 'Mission assignée'),
                    ('review_submitted', 'Content submitted for review'),
                ],
            ),
        ),
    ]
