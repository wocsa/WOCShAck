"""
Functional tests for the Community & Engagement module.
Covers activity feed, reactions, and messaging.
"""
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from Account.models import PurchasedFeature
from Community.models.content import BlogCategory, BlogPost
from Community.models.content import Event, Tutorial
from Community.models.feed import ActivityFeedItem
from Community.models.reactions import ReactionType
from Community.models.communication import Conversation, Message

User = get_user_model()


def _make_user(username='testuser', password='testpass123'):
    return User.objects.create_user(username=username, password=password, email=f'{username}@example.com')


# ── Activity Feed ─────────────────────────────────────────────────────────────

class TestActivityFeed(TestCase):
    def setUp(self):
        self.user = _make_user('feeder')

    def test_feed_item_created(self):
        item = ActivityFeedItem.objects.create(
            user=self.user,
            action_type='friend_added',
            title='Made a new friend',
            visibility='public',
        )
        self.assertEqual(ActivityFeedItem.objects.filter(user=self.user).count(), 1)
        self.assertEqual(item.action_type, 'friend_added')

    def test_feed_view_requires_login(self):
        response = Client().get(reverse('community:activity_feed'))
        self.assertNotEqual(response.status_code, 200)


# ── Reactions ─────────────────────────────────────────────────────────────────

class TestReactions(TestCase):
    def setUp(self):
        self.user = _make_user('reactor')
        self.rtype = ReactionType.objects.create(name='Like', emoji='👍', category='standard', order=1)

    def test_react_endpoint_requires_login(self):
        response = Client().post(reverse('community:react'), {
            'content_type': 'blog.blogpost',
            'object_id': str(uuid.uuid4()),
            'reaction_type_id': str(self.rtype.id),
        })
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(response.status_code, 200)


# ── Messaging ─────────────────────────────────────────────────────────────────

class TestMessaging(TestCase):
    def setUp(self):
        self.u1 = _make_user('sender')
        self.u2 = _make_user('receiver')

    def test_conversation_created(self):
        conv = Conversation.objects.create(user1=self.u1, user2=self.u2)
        self.assertIsNotNone(conv.pk)

    def test_message_sent(self):
        conv = Conversation.objects.create(user1=self.u1, user2=self.u2)
        msg = Message.objects.create(conversation=conv, sender=self.u1, content='Hello!')
        self.assertEqual(Message.objects.filter(conversation=conv).count(), 1)
        self.assertEqual(msg.content, 'Hello!')

    def test_send_message_view_requires_login(self):
        conv = Conversation.objects.create(user1=self.u1, user2=self.u2)
        response = Client().post(
            reverse('community:send_message', kwargs={'conversation_id': conv.id}),
            {'content': 'Hi'},
        )
        self.assertNotEqual(response.status_code, 200)


class TestBlogCreationFlow(TestCase):
    def setUp(self):
        self.user = _make_user('blogauthor')
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.category = BlogCategory.objects.create(name='Announcements', slug='announcements')
        self.client = Client()
        self.client.force_login(self.user)

    def test_blog_create_template_removes_required_attribute_after_simplemde_init(self):
        response = self.client.get(reverse('community:blog_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "contentTextarea.removeAttribute('required');")

    def test_event_create_template_removes_required_attribute_after_simplemde_init(self):
        response = self.client.get(reverse('community:event_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "descTextarea.removeAttribute('required');")

    def test_tutorial_create_template_removes_required_attribute_after_simplemde_init(self):
        response = self.client.get(reverse('community:tutorial_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "el.removeAttribute('required');")

    def test_blog_create_persists_featured_image(self):
        featured_image = SimpleUploadedFile(
            'cover.gif',
            (
                b'GIF87a\x01\x00\x01\x00\x80\x00\x00'
                b'\x00\x00\x00\xff\xff\xff!\xf9\x04\x01'
                b'\x00\x00\x00\x00,\x00\x00\x00\x00\x01'
                b'\x00\x01\x00\x00\x02\x02D\x01\x00;'
            ),
            content_type='image/gif',
        )

        response = self.client.post(
            reverse('community:blog_create'),
            {
                'title': 'Launch Notes',
                'content': 'Markdown body',
                'category': str(self.category.id),
                'tags': 'release, notes',
                'status': BlogPost.Status.PUBLISHED,
                'allow_comments': 'on',
                'featured_image': featured_image,
            },
        )

        post = BlogPost.objects.get(slug='launch-notes')
        self.assertRedirects(response, reverse('community:blog_detail', kwargs={'slug': post.slug}))
        self.assertEqual(post.status, BlogPost.Status.PUBLISHED)
        self.assertIsNotNone(post.published_at)
        self.assertTrue(post.featured_image.name.startswith('blog/images/'))
        self.assertIn('cover', post.featured_image.name)

    def test_event_create_allows_published_status_for_content_creator(self):
        creator = _make_user('eventcreator')
        PurchasedFeature.objects.create(
            user=creator,
            feature_type=PurchasedFeature.FEATURE_DEVELOPER_ROLE,
            price_paid=PurchasedFeature.get_price(PurchasedFeature.FEATURE_DEVELOPER_ROLE),
        )
        self.client.force_login(creator)

        response = self.client.post(
            reverse('community:event_create'),
            {
                'title': 'Creator Webinar',
                'description': 'Markdown event description',
                'event_type': Event.EventType.WEBINAR,
                'format': Event.Format.ONLINE,
                'start_datetime': '2030-01-10T10:00',
                'end_datetime': '2030-01-10T11:00',
                'timezone': 'UTC',
                'status': Event.Status.PUBLISHED,
            },
        )

        event = Event.objects.get(title='Creator Webinar')
        self.assertRedirects(response, reverse('community:event_detail', kwargs={'event_id': event.id}))
        self.assertEqual(event.status, Event.Status.PUBLISHED)

    def test_tutorial_create_allows_published_status_for_content_creator(self):
        creator = _make_user('tutorialcreator')
        PurchasedFeature.objects.create(
            user=creator,
            feature_type=PurchasedFeature.FEATURE_DEVELOPER_ROLE,
            price_paid=PurchasedFeature.get_price(PurchasedFeature.FEATURE_DEVELOPER_ROLE),
        )
        self.client.force_login(creator)

        response = self.client.post(
            reverse('community:tutorial_create'),
            {
                'title': 'Published Tutorial',
                'description': 'Tutorial overview',
                'difficulty': Tutorial.Difficulty.BEGINNER,
                'estimated_minutes': '20',
                'category': 'Guides',
                'is_published': 'on',
                'steps-TOTAL_FORMS': '1',
                'steps-INITIAL_FORMS': '0',
                'steps-MIN_NUM_FORMS': '0',
                'steps-MAX_NUM_FORMS': '1000',
                'steps-0-order': '1',
                'steps-0-title': 'Step One',
                'steps-0-content': 'Do the thing',
                'steps-0-code_example': '',
            },
        )

        tutorial = Tutorial.objects.get(slug='published-tutorial')
        self.assertRedirects(response, reverse('community:tutorial_detail', kwargs={'slug': tutorial.slug}))
        self.assertTrue(tutorial.is_published)
