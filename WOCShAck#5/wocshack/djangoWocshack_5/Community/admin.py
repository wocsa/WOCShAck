from django.contrib import admin
from .models.social import FriendRequest, Friendship
from .models.communication import Conversation, Message, MessageReport, MessageRead, UserBlock
from .models.notification import Notification, NotificationPreference
from .models.feed import ActivityFeedItem, FeedPreferences
from .models.social import UserFollow
from .models.content import (
    BlogCategory, BlogPost, BlogComment,
    Tutorial, TutorialStep, TutorialProgress, TutorialQuiz,
    ShowcaseItem, ShowcaseVote,
    Event, EventRegistration,
)
from .models.reactions import ReactionType, Reaction, ReactionSummary
from .models.mentions import MentionPreferences, Mention
from .models.css_comments import CssComment, CommentReply
from .models.email_campaigns import EmailCampaign, EmailTemplate, EmailSend
from .models.push_notifications import PushSubscription, PushNotification
from .models.retention import InactivityTrigger, ReengagementAction
from .models.analytics import EngagementScore, ScoreComponent, ActivityMetric, EngagementFunnel


# ── Social ────────────────────────────────────────────────────────────────────

@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('sender__username', 'receiver__username')
    readonly_fields = ('created_at',)


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ('user1', 'user2', 'user1_blocked', 'user2_blocked', 'created_at')
    list_filter = ('user1_blocked', 'user2_blocked')
    search_fields = ('user1__username', 'user2__username')
    readonly_fields = ('created_at',)


# ── Communication ─────────────────────────────────────────────────────────────

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('user1', 'user2', 'created_at')
    search_fields = ('user1__username', 'user2__username')
    readonly_fields = ('created_at',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'conversation', 'is_deleted', 'is_edited', 'is_reported', 'timestamp')
    list_filter = ('is_deleted', 'is_reported', 'is_edited')
    search_fields = ('sender__username', 'content')
    readonly_fields = ('timestamp',)
    ordering = ('-timestamp',)


@admin.register(MessageReport)
class MessageReportAdmin(admin.ModelAdmin):
    list_display = ('reporter', 'message', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reporter__username', 'reason')
    readonly_fields = ('created_at',)


@admin.register(MessageRead)
class MessageReadAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'read_at')
    search_fields = ('user__username',)
    readonly_fields = ('read_at',)


# ── Notifications ─────────────────────────────────────────────────────────────

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notif_type', 'title', 'is_read', 'priority', 'created_at')
    list_filter = ('notif_type', 'is_read', 'priority', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    readonly_fields = ('created_at',)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'friend_requests', 'messages', 'followers')
    search_fields = ('user__username',)


# ── Feed ──────────────────────────────────────────────────────────────────────

@admin.register(ActivityFeedItem)
class ActivityFeedItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'action_type', 'title', 'visibility', 'created_at')
    list_filter = ('action_type', 'visibility', 'created_at')
    search_fields = ('user__username', 'title')
    readonly_fields = ('created_at',)


@admin.register(FeedPreferences)
class FeedPreferencesAdmin(admin.ModelAdmin):
    list_display = ('user', 'show_friends')
    search_fields = ('user__username',)


# ── Follow ────────────────────────────────────────────────────────────────────

@admin.register(UserFollow)
class UserFollowAdmin(admin.ModelAdmin):
    list_display = ('follower', 'following', 'created_at')
    search_fields = ('follower__username', 'following__username')
    readonly_fields = ('created_at',)


# ── Blog & News ───────────────────────────────────────────────────────────────

@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


class BlogCommentInline(admin.TabularInline):
    model = BlogComment
    extra = 0
    fields = ('author', 'content', 'status', 'parent', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'status', 'is_featured', 'is_pinned', 'view_count', 'published_at')
    list_filter = ('status', 'is_featured', 'is_pinned', 'category')
    search_fields = ('title', 'author__username', 'tags')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at', 'view_count')
    inlines = [BlogCommentInline]
    ordering = ('-created_at',)


@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'post', 'status', 'parent', 'created_at')
    list_filter = ('status',)
    search_fields = ('author__username', 'content', 'post__title')
    readonly_fields = ('created_at',)


# ── Tutorial System ───────────────────────────────────────────────────────────

class TutorialStepInline(admin.TabularInline):
    model = TutorialStep
    extra = 0
    fields = ('order', 'title', 'has_interactive_editor')
    ordering = ('order',)


@admin.register(Tutorial)
class TutorialAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'difficulty', 'estimated_minutes', 'is_premium', 'is_published', 'created_at')
    list_filter = ('difficulty', 'is_premium', 'is_published')
    search_fields = ('title', 'author__username', 'category')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    inlines = [TutorialStepInline]


@admin.register(TutorialStep)
class TutorialStepAdmin(admin.ModelAdmin):
    list_display = ('tutorial', 'order', 'title', 'has_interactive_editor')
    list_filter = ('has_interactive_editor',)
    search_fields = ('tutorial__title', 'title')
    ordering = ('tutorial', 'order')


@admin.register(TutorialProgress)
class TutorialProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'tutorial', 'current_step', 'completed', 'completed_at')
    list_filter = ('completed',)
    search_fields = ('user__username', 'tutorial__title')
    readonly_fields = ('updated_at',)


@admin.register(TutorialQuiz)
class TutorialQuizAdmin(admin.ModelAdmin):
    list_display = ('step', 'question_type', 'question')
    list_filter = ('question_type',)
    search_fields = ('step__title', 'question')


# ── Showcase Gallery ──────────────────────────────────────────────────────────

@admin.register(ShowcaseItem)
class ShowcaseItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'is_featured', 'is_approved', 'vote_score', 'view_count', 'created_at')
    list_filter = ('category', 'is_featured', 'is_approved')
    search_fields = ('title', 'author__username')
    readonly_fields = ('created_at', 'vote_score', 'view_count')
    ordering = ('-created_at',)


@admin.register(ShowcaseVote)
class ShowcaseVoteAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'vote_type', 'created_at')
    list_filter = ('vote_type',)
    search_fields = ('user__username', 'item__title')
    readonly_fields = ('created_at',)


# ── Events & Workshops ────────────────────────────────────────────────────────

class EventRegistrationInline(admin.TabularInline):
    model = EventRegistration
    extra = 0
    fields = ('user', 'status', 'registered_at')
    readonly_fields = ('registered_at',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'organizer', 'event_type', 'format', 'status', 'start_datetime', 'capacity')
    list_filter = ('event_type', 'format', 'status')
    search_fields = ('title', 'organizer__username')
    readonly_fields = ('created_at',)
    inlines = [EventRegistrationInline]
    ordering = ('start_datetime',)


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'status', 'registered_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'event__title')
    readonly_fields = ('registered_at',)


# ── Reactions ─────────────────────────────────────────────────────────────────

@admin.register(ReactionType)
class ReactionTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'emoji', 'category', 'min_level_required', 'is_active', 'order')
    list_filter = ('category', 'is_active')
    ordering = ('order',)


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'reaction_type', 'content_type', 'object_id', 'created_at')
    list_filter = ('reaction_type', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)


@admin.register(ReactionSummary)
class ReactionSummaryAdmin(admin.ModelAdmin):
    list_display = ('content_type', 'object_id', 'reaction_type', 'count', 'last_updated')
    list_filter = ('reaction_type',)


# ── Mentions ──────────────────────────────────────────────────────────────────

@admin.register(MentionPreferences)
class MentionPreferencesAdmin(admin.ModelAdmin):
    list_display = ('user', 'allow_mentions', 'notify_on_mention')
    search_fields = ('user__username',)


@admin.register(Mention)
class MentionAdmin(admin.ModelAdmin):
    list_display = ('mentioned_by', 'mentioned_user', 'is_notified', 'created_at')
    list_filter = ('is_notified',)
    search_fields = ('mentioned_user__username', 'mentioned_by__username')
    readonly_fields = ('created_at',)


# ── User Block ────────────────────────────────────────────────────────────────

@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = ('blocker', 'blocked', 'created_at')
    search_fields = ('blocker__username', 'blocked__username')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


# ── CSS Comments ──────────────────────────────────────────────────────────────

class CommentReplyInline(admin.TabularInline):
    model = CommentReply
    extra = 0
    fields = ('author', 'content', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(CssComment)
class CssCommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'css_item_id', 'is_question', 'status', 'created_at')
    list_filter = ('status', 'is_question')
    search_fields = ('author__username', 'content')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CommentReplyInline]


# ── Email Campaigns ───────────────────────────────────────────────────────────

@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'campaign_type', 'trigger_days_inactive', 'is_active', 'created_at')
    list_filter = ('campaign_type', 'is_active')
    search_fields = ('name',)
    readonly_fields = ('created_at',)


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'subject', 'created_at')
    list_filter = ('campaign',)
    search_fields = ('subject',)
    readonly_fields = ('created_at',)


@admin.register(EmailSend)
class EmailSendAdmin(admin.ModelAdmin):
    list_display = ('user', 'campaign', 'sent_at', 'opened_at', 'is_bounced')
    list_filter = ('campaign', 'is_bounced')
    search_fields = ('user__username',)
    readonly_fields = ('sent_at',)
    ordering = ('-sent_at',)


# ── Push Notifications ────────────────────────────────────────────────────────

@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_active', 'user_agent', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)


@admin.register(PushNotification)
class PushNotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'is_delivered', 'sent_at')
    list_filter = ('is_delivered',)
    search_fields = ('user__username', 'title')
    readonly_fields = ('sent_at',)
    ordering = ('-sent_at',)


# ── Retention ─────────────────────────────────────────────────────────────────

@admin.register(InactivityTrigger)
class InactivityTriggerAdmin(admin.ModelAdmin):
    list_display = ('days_inactive', 'action_type', 'campaign', 'is_active')
    list_filter = ('action_type', 'is_active')
    ordering = ('days_inactive',)


@admin.register(ReengagementAction)
class ReengagementActionAdmin(admin.ModelAdmin):
    list_display = ('user', 'trigger', 'action_taken', 'was_effective')
    list_filter = ('was_effective',)
    search_fields = ('user__username',)
    readonly_fields = ('action_taken',)


# ── Analytics ─────────────────────────────────────────────────────────────────

@admin.register(EngagementScore)
class EngagementScoreAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_score', 'activity_score', 'social_score', 'risk_level', 'computed_at')
    list_filter = ('risk_level',)
    search_fields = ('user__username',)
    readonly_fields = ('computed_at',)
    ordering = ('-total_score',)


@admin.register(ActivityMetric)
class ActivityMetricAdmin(admin.ModelAdmin):
    list_display = ('date', 'dau_count', 'mau_count', 'new_users', 'retention_rate')
    readonly_fields = ('date',)
    ordering = ('-date',)


@admin.register(ScoreComponent)
class ScoreComponentAdmin(admin.ModelAdmin):
    list_display = ('engagement_score', 'component_type', 'value', 'computed_at')
    list_filter = ('component_type',)
    readonly_fields = ('computed_at',)
    ordering = ('-computed_at',)


@admin.register(EngagementFunnel)
class EngagementFunnelAdmin(admin.ModelAdmin):
    list_display = ('name', 'stage', 'user_count', 'conversion_rate', 'date')
    list_filter = ('date',)
    ordering = ('-date', 'stage')
