from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid

User = get_user_model()


# ── Blog & News ───────────────────────────────────────────────────────────────

class BlogCategory(models.Model):
    """Category for organising blog posts."""
    name        = models.CharField(max_length=100, unique=True)
    slug        = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Blog Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class BlogPost(models.Model):
    """A published article or news item."""

    class Status(models.TextChoices):
        DRAFT     = 'draft',     'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED  = 'archived',  'Archived'

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title          = models.CharField(max_length=255)
    slug           = models.SlugField(max_length=255, unique=True)
    content        = models.TextField(help_text='Markdown supported')
    author         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='blog_posts')
    category       = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    tags           = models.CharField(max_length=255, blank=True, help_text='Comma-separated tags')
    featured_image = models.ImageField(upload_to='blog/images/', null=True, blank=True)
    status         = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    is_featured    = models.BooleanField(default=False)
    is_pinned      = models.BooleanField(default=False)
    allow_comments = models.BooleanField(default=True)
    view_count     = models.PositiveIntegerField(default=0)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)
    published_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-is_pinned', '-published_at', '-created_at']

    def __str__(self):
        return self.title

    def publish(self):
        self.status = self.Status.PUBLISHED
        if not self.published_at:
            self.published_at = timezone.now()
        self.save()

    def tag_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]


class BlogComment(models.Model):
    """Comment on a blog post, supports threading via parent FK."""

    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post       = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='comments')
    author     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blog_comments')
    content    = models.TextField(max_length=2000)
    parent     = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    status     = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.author.username} on «{self.post.title}»"


# ── Tutorial System ───────────────────────────────────────────────────────────

class Tutorial(models.Model):
    """Structured learning content."""

    class Difficulty(models.TextChoices):
        BEGINNER     = 'beginner',     'Beginner'
        INTERMEDIATE = 'intermediate', 'Intermediate'
        ADVANCED     = 'advanced',     'Advanced'

    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title             = models.CharField(max_length=255)
    slug              = models.SlugField(max_length=255, unique=True)
    description       = models.TextField()
    author            = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tutorials')
    difficulty        = models.CharField(max_length=14, choices=Difficulty.choices, default=Difficulty.BEGINNER)
    estimated_minutes = models.PositiveIntegerField(default=15)
    prerequisites     = models.TextField(blank=True, help_text='What learners should know beforehand')
    category          = models.CharField(max_length=100, blank=True)
    thumbnail         = models.ImageField(upload_to='tutorials/thumbnails/', null=True, blank=True)
    is_premium        = models.BooleanField(default=False, help_text='Developer-only content')
    is_published      = models.BooleanField(default=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['difficulty', 'title']

    def __str__(self):
        return f"{self.title} [{self.difficulty}]"

    def step_count(self):
        return self.steps.count()


class TutorialStep(models.Model):
    """A single step within a tutorial."""

    id                    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tutorial              = models.ForeignKey(Tutorial, on_delete=models.CASCADE, related_name='steps')
    order                 = models.PositiveIntegerField()
    title                 = models.CharField(max_length=255)
    content               = models.TextField(help_text='Markdown supported')
    code_example          = models.TextField(blank=True, help_text='Code snippet for this step')
    has_interactive_editor = models.BooleanField(default=False)
    created_at            = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        unique_together = ('tutorial', 'order')

    def __str__(self):
        return f"{self.tutorial.title} — Step {self.order}: {self.title}"


class TutorialProgress(models.Model):
    """Tracks a user's progress through a tutorial."""

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tutorial_progress')
    tutorial     = models.ForeignKey(Tutorial, on_delete=models.CASCADE, related_name='progress_records')
    current_step = models.ForeignKey(TutorialStep, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    completed    = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'tutorial')

    def __str__(self):
        status = 'completed' if self.completed else f'step {self.current_step.order if self.current_step else 0}'
        return f"{self.user.username} — {self.tutorial.title} ({status})"


class TutorialQuiz(models.Model):
    """Knowledge-check question attached to a tutorial step."""

    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = 'multiple_choice', 'Multiple Choice'
        CODE            = 'code',            'Code'
        TRUE_FALSE      = 'true_false',      'True / False'

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    step          = models.ForeignKey(TutorialStep, on_delete=models.CASCADE, related_name='quizzes')
    question      = models.TextField()
    question_type = models.CharField(max_length=16, choices=QuestionType.choices, default=QuestionType.MULTIPLE_CHOICE)
    options       = models.JSONField(default=list, help_text='List of answer strings for multiple choice')
    correct_answer = models.TextField()
    hint          = models.TextField(blank=True)

    def __str__(self):
        return f"Quiz for step «{self.step.title}»"


# ── Showcase Gallery ──────────────────────────────────────────────────────────

class ShowcaseItem(models.Model):
    """A featured CSS creation submitted by the community."""

    class Category(models.TextChoices):
        LOADERS    = 'loaders',    'Loaders & Spinners'
        BUTTONS    = 'buttons',    'Buttons & Interactions'
        CARDS      = 'cards',      'Cards & Layouts'
        ART        = 'art',        'Pure CSS Art'
        ANIMATIONS = 'animations', 'Animations'
        TYPOGRAPHY = 'typography', 'Typography'
        DARK_MODE  = 'dark_mode',  'Dark Mode Designs'
        OTHER      = 'other',      'Other'

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title       = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    author      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='showcase_items')
    demo_html   = models.TextField(blank=True, help_text='HTML for the live demo (optional)')
    demo_css    = models.TextField(help_text='CSS source code')
    thumbnail   = models.ImageField(upload_to='showcase/thumbnails/', null=True, blank=True)
    preview_gif = models.ImageField(upload_to='showcase/previews/', null=True, blank=True, help_text='Animated GIF preview of the CSS creation')
    category    = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    is_featured = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    vote_score  = models.IntegerField(default=0)
    view_count  = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_featured', '-vote_score', '-created_at']

    def __str__(self):
        return f"{self.title} by {self.author.username}"


class ShowcaseVote(models.Model):
    """Community vote on a showcase item."""

    class VoteType(models.TextChoices):
        UPVOTE   = 'upvote',   'Upvote'
        DOWNVOTE = 'downvote', 'Downvote'

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='showcase_votes')
    item       = models.ForeignKey(ShowcaseItem, on_delete=models.CASCADE, related_name='votes')
    vote_type  = models.CharField(max_length=8, choices=VoteType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'item')

    def __str__(self):
        return f"{self.user.username} {self.vote_type} «{self.item.title}»"


# ── Events & Workshops ────────────────────────────────────────────────────────

class Event(models.Model):
    """A community event: workshop, webinar, or meetup."""

    class EventType(models.TextChoices):
        WORKSHOP = 'workshop', 'Workshop'
        WEBINAR  = 'webinar',  'Webinar'
        MEETUP   = 'meetup',   'Meetup'

    class Format(models.TextChoices):
        ONLINE    = 'online',    'Online'
        IN_PERSON = 'in_person', 'In-Person'
        HYBRID    = 'hybrid',    'Hybrid'

    class Status(models.TextChoices):
        DRAFT     = 'draft',     'Draft'
        PUBLISHED = 'published', 'Published'
        CANCELLED = 'cancelled', 'Cancelled'

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title          = models.CharField(max_length=255)
    description    = models.TextField()
    organizer      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='organized_events')
    event_type     = models.CharField(max_length=10, choices=EventType.choices, default=EventType.WORKSHOP)
    format         = models.CharField(max_length=10, choices=Format.choices, default=Format.ONLINE)
    start_datetime = models.DateTimeField()
    end_datetime   = models.DateTimeField()
    timezone       = models.CharField(max_length=50, default='UTC')
    capacity       = models.PositiveIntegerField(null=True, blank=True, help_text='Leave blank for unlimited')
    meeting_link   = models.URLField(blank=True)
    status         = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_datetime']

    def __str__(self):
        return f"{self.title} ({self.get_event_type_display()})"

    def registration_count(self):
        return self.registrations.filter(status='registered').count()

    def is_full(self):
        if self.capacity is None:
            return False
        return self.registration_count() >= self.capacity

    def is_upcoming(self):
        return self.start_datetime > timezone.now()


class EventRegistration(models.Model):
    """A user's registration for an event."""

    class Status(models.TextChoices):
        REGISTERED = 'registered', 'Registered'
        ATTENDED   = 'attended',   'Attended'
        CANCELLED  = 'cancelled',  'Cancelled'

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event         = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations')
    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='event_registrations')
    status        = models.CharField(max_length=10, choices=Status.choices, default=Status.REGISTERED)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'user')
        ordering = ['registered_at']

    def __str__(self):
        return f"{self.user.username} @ {self.event.title} [{self.status}]"
