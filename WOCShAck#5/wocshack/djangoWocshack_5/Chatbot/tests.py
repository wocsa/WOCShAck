from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
import json

from .models import ChatMessage, KnowledgeBase
from .rag_engine import RAGEngine, get_rag_engine


class RAGEngineTestCase(TestCase):
    """Tests for the RAG engine."""

    def setUp(self):
        self.engine = get_rag_engine()

    def test_engine_initialization(self):
        """Test that the RAG engine initializes correctly."""
        self.assertIsInstance(self.engine, RAGEngine)
        self.assertGreater(len(self.engine.qa_pairs), 0)

    def test_retrieve_relevant_qa(self):
        """Test retrieval of relevant Q&A pairs."""
        results = self.engine.retrieve("How do I create an account?")
        self.assertGreater(len(results), 0)
        # Should match account-related question
        best_match = results[0][0]
        self.assertIn('account', best_match['question'].lower())

    def test_generate_response(self):
        """Test response generation."""
        response = self.engine.generate_response("What is V.R.C?")
        self.assertIn('response', response)
        self.assertIn('confidence', response)
        self.assertGreater(response['confidence'], 0)

    def test_fallback_response(self):
        """Test fallback when no match found."""
        response = self.engine.generate_response("xyzabc123nonsense")
        self.assertEqual(response['source'], 'fallback')
        self.assertEqual(response['confidence'], 0.0)


class ChatAPITestCase(TestCase):
    """Tests for the chat API endpoints."""

    def setUp(self):
        self.client = Client()

    def test_chat_api_success(self):
        """Test successful chat API call."""
        response = self.client.post(
            reverse('chatbot:chat_api'),
            data=json.dumps({'message': 'Hello'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('response', data)

    def test_chat_api_empty_message(self):
        """Test chat API with empty message."""
        response = self.client.post(
            reverse('chatbot:chat_api'),
            data=json.dumps({'message': ''}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_chat_api_invalid_json(self):
        """Test chat API with invalid JSON."""
        response = self.client.post(
            reverse('chatbot:chat_api'),
            data='not valid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_chat_history_endpoint(self):
        """Test chat history endpoint."""
        # First, create a message
        self.client.post(
            reverse('chatbot:chat_api'),
            data=json.dumps({'message': 'Test message'}),
            content_type='application/json'
        )

        # Then get history
        response = self.client.get(reverse('chatbot:history'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('history', data)

    def test_get_suggestions(self):
        """Test suggestions endpoint."""
        response = self.client.get(reverse('chatbot:suggestions'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('suggestions', data)

    def test_get_categories(self):
        """Test categories endpoint."""
        response = self.client.get(reverse('chatbot:categories'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('categories', data)


class ChatbotViewTestCase(TestCase):
    """Tests for chatbot views."""

    def setUp(self):
        self.client = Client()

    def test_chatbot_index_view(self):
        """Test main chatbot page loads."""
        response = self.client.get(reverse('chatbot:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'chatbot')

    def test_widget_view(self):
        """Test widget page loads."""
        response = self.client.get(reverse('chatbot:widget'))
        self.assertEqual(response.status_code, 200)


class ChatMessageModelTestCase(TestCase):
    """Tests for the ChatMessage model."""

    def test_create_message(self):
        """Test creating a chat message."""
        message = ChatMessage.objects.create(
            session_id='test-session-123',
            message='Test question',
            response='Test answer'
        )
        self.assertIsNotNone(message.id)
        self.assertEqual(message.message, 'Test question')
        self.assertIsNotNone(message.timestamp)


class ChatExportTestCase(TestCase):
    """Tests for chat export functionality."""

    def setUp(self):
        self.client = Client()
        # Create some test messages
        self.client.post(
            reverse('chatbot:chat_api'),
            data=json.dumps({'message': 'Test message 1'}),
            content_type='application/json'
        )
        self.client.post(
            reverse('chatbot:chat_api'),
            data=json.dumps({'message': 'Test message 2'}),
            content_type='application/json'
        )

    def test_export_json(self):
        """Test exporting chat history as JSON."""
        response = self.client.get(reverse('chatbot:export') + '?format=json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('attachment', response['Content-Disposition'])

        # Verify JSON structure
        data = json.loads(response.content)
        self.assertIn('messages', data)
        self.assertIn('message_count', data)

    def test_export_csv(self):
        """Test exporting chat history as CSV."""
        response = self.client.get(reverse('chatbot:export') + '?format=csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])

    def test_export_empty_history(self):
        """Test exporting with no chat history."""
        # Create a new client without any messages
        new_client = Client()
        response = new_client.get(reverse('chatbot:export'))
        self.assertEqual(response.status_code, 404)


class KnowledgeBaseModelTestCase(TestCase):
    """Tests for the KnowledgeBase model."""

    def test_create_entry(self):
        """Test creating a knowledge base entry."""
        entry = KnowledgeBase.objects.create(
            question='Test question?',
            answer='Test answer.',
            category='test',
            keywords='test, question, answer'
        )
        self.assertIsNotNone(entry.id)
        self.assertEqual(entry.category, 'test')
        self.assertTrue(entry.is_active)

    def test_entry_string_representation(self):
        """Test the string representation of an entry."""
        entry = KnowledgeBase.objects.create(
            question='A very long question that should be truncated?',
            answer='Answer.',
            category='test',
            keywords='test'
        )
        self.assertIn('[test]', str(entry))


class RAGEngineDatabaseIntegrationTestCase(TestCase):
    """Tests for RAG engine integration with database entries."""

    def setUp(self):
        # Create a test knowledge base entry
        self.entry = KnowledgeBase.objects.create(
            question='What is the special test feature?',
            answer='This is a special test feature for unit testing.',
            category='test',
            keywords='special, test, feature, unit'
        )

    def test_database_entries_loaded(self):
        """Test that database entries are loaded into the RAG engine."""
        # Force reload the engine to pick up the new entry
        engine = get_rag_engine()
        engine.reload_knowledge_base()

        # Search for our test entry
        results = engine.retrieve('special test feature', top_k=5, threshold=0.1)

        # Should find our database entry
        found = False
        for qa, score in results:
            if 'special test feature' in qa['answer'].lower():
                found = True
                break

        self.assertTrue(found, "Database entry should be found by RAG engine")
