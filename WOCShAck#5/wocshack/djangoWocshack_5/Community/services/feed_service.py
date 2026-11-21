from Community.models.feed import ActivityFeedItem
from Community.models.social import UserFollow
from django.db.models import Q


def emit(user, action_type, title, description='', icon='📌',
         related_user=None, related_object_id='', visibility=None):
    """Creates an item in the user's activity feed."""
    if visibility is None:
        try:
            visibility = user.feed_prefs.default_visibility
        except Exception:
            visibility = ActivityFeedItem.Visibility.PUBLIC

    ActivityFeedItem.objects.create(
        user=user,
        action_type=action_type,
        title=title,
        description=description,
        icon=icon,
        related_user=related_user,
        related_object_id=str(related_object_id) if related_object_id else '',
        visibility=visibility,
    )


def _excluded_action_types_for_prefs(prefs):
    """Return a list of action_type values that should be hidden based on prefs."""
    AT = ActivityFeedItem.ActionType
    excluded = []
    if not prefs.show_friends:
        excluded += [AT.FRIEND_ADDED, AT.FOLLOWER_GAINED]
    if not prefs.show_blog_posts:
        excluded.append(AT.BLOG_POST_CREATED)
    if not prefs.show_forum_posts:
        excluded += [AT.FORUM_TOPIC_CREATED, AT.FORUM_POST_CREATED]
    if not prefs.show_showcases:
        excluded.append(AT.SHOWCASE_ADDED)
    if not prefs.show_tutorials:
        excluded.append(AT.TUTORIAL_PUBLISHED)
    if not prefs.show_css:
        excluded.append(AT.CSS_PUBLISHED)
    if not prefs.show_reviews:
        excluded.append(AT.REVIEW_POSTED)
    if not prefs.show_events:
        excluded.append(AT.EVENT_JOINED)
    return excluded


def get_feed_for_user(viewer, page_size=20, offset=0):
    """
    Returns the activity feed visible to `viewer`:
    - Their own items
    - Public items from users they follow
    - 'Followers' items from users they follow
    Respects the viewer's FeedPreferences toggles.
    """
    try:
        following_ids = UserFollow.objects.filter(follower=viewer).values_list('following_id', flat=True)

        qs = ActivityFeedItem.objects.filter(
            Q(user=viewer) |
            Q(user_id__in=following_ids, visibility=ActivityFeedItem.Visibility.PUBLIC) |
            Q(user_id__in=following_ids, visibility=ActivityFeedItem.Visibility.FOLLOWERS)
        ).select_related('user', 'related_user').order_by('-created_at')

        # Apply FeedPreferences filters
        from Community.models.feed import FeedPreferences
        try:
            prefs = viewer.feed_prefs
            excluded = _excluded_action_types_for_prefs(prefs)
            if excluded:
                qs = qs.exclude(action_type__in=excluded)
        except FeedPreferences.DoesNotExist:
            pass

        return qs[offset:offset + page_size]
    except Exception:
        return ActivityFeedItem.objects.none()


def create_feed_item(user, action_type, title, description='', icon='📌',
                     related_user=None, related_object_id='', visibility=None):
    """Alias for emit for expected API."""
    return emit(user, action_type, title, description, icon, 
                related_user, related_object_id, visibility)


def get_public_feed(page_size=20, offset=0):
    """Get public feed items visible to all users."""
    try:
        qs = ActivityFeedItem.objects.filter(
            visibility=ActivityFeedItem.Visibility.PUBLIC
        ).select_related('user', 'related_user').order_by('-created_at')
        
        return qs[offset:offset + page_size]
    except Exception:
        return ActivityFeedItem.objects.none()
