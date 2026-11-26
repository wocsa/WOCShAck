"""
RAG (Retrieval Augmented Generation) Engine for V.R.C Chatbot

This module implements a lightweight RAG system using TF-IDF similarity
for retrieving relevant Q&A pairs from the knowledge base.

No external LLM API is required - uses local similarity matching.

Knowledge sources:
1. JSON file (static knowledge base)
2. Database (dynamic entries via admin interface)
"""

import json
import os
import re
import math
import logging
import requests
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

# Use proper logging instead of print statements for production
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "You are a V.R.C support assistant. Be concise and accurate. If unsure, say so."


class OllamaClient:
    """
    Thin HTTP client for the Ollama REST API.
    Returns None on any error so callers can fall back to RAG-only answers.
    """

    def __init__(self):
        try:
            from django.conf import settings
            self.base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://ollama:11434')
            self.model = getattr(settings, 'OLLAMA_MODEL', 'gemma3:1b')
        except Exception:
            self.base_url = os.environ.get('OLLAMA_BASE_URL', 'http://ollama:11434')
            self.model = os.environ.get('OLLAMA_MODEL', 'gemma3:1b')

    def generate(self, prompt: str, system: Optional[str] = None, timeout: int = 15) -> Optional[str]:
        """
        Send a prompt to Ollama and return the generated text.
        Returns None if Ollama is unavailable or returns an error.
        """
        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            }
            if system:
                payload["system"] = system
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip() or None
        except Exception as e:
            logger.debug(f"Ollama unavailable: {e}")
            return None


class RAGEngine:
    """
    Lightweight RAG engine using TF-IDF for document retrieval.
    """

    def __init__(self, knowledge_base_path: str = None):
        """
        Initialize the RAG engine with a knowledge base.

        Args:
            knowledge_base_path: Path to the JSON knowledge base file
        """
        if knowledge_base_path is None:
            # Default path relative to this file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            knowledge_base_path = os.path.join(current_dir, 'data', 'knowledge_base.json')

        self.knowledge_base_path = knowledge_base_path
        self.qa_pairs = []
        self.fallback_responses = []
        self.categories = {}

        # TF-IDF components
        self.document_vectors = []
        self.idf_scores = {}
        self.vocabulary = set()

        # Load and index the knowledge base
        self._load_knowledge_base()
        self._build_index()

    def _load_knowledge_base(self):
        """
        Load Q&A pairs from multiple sources:
        1. JSON knowledge base file (static)
        2. Database KnowledgeBase model (dynamic)
        """
        # Load from JSON file
        try:
            with open(self.knowledge_base_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.qa_pairs = data.get('qa_pairs', [])
            self.fallback_responses = data.get('fallback_responses', [
                "I'm sorry, I couldn't understand your question. Please try again."
            ])
            self.categories = data.get('categories', {})

        except FileNotFoundError:
            logger.warning(f"Knowledge base not found at {self.knowledge_base_path}")
            self.qa_pairs = []
            self.fallback_responses = [
                "I'm sorry, I couldn't understand your question. Please try again."
            ]
            self.categories = {}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing knowledge base JSON: {e}")
            self.qa_pairs = []
            self.fallback_responses = [
                "I'm sorry, I couldn't understand your question. Please try again."
            ]
            self.categories = {}

        # Load dynamic entries from database
        self._load_database_entries()

    def _load_database_entries(self):
        """
        Load Q&A pairs from the KnowledgeBase database model.
        This allows admins to add dynamic entries via the admin interface.
        """
        try:
            # Import here to avoid circular imports
            from .models import KnowledgeBase

            # Get all active knowledge base entries
            db_entries = KnowledgeBase.objects.filter(is_active=True)

            # Starting ID for database entries (to avoid conflicts with JSON IDs)
            next_id = max([qa.get('id', 0) for qa in self.qa_pairs], default=0) + 1000

            for entry in db_entries:
                # Parse keywords from comma-separated string
                keywords = [k.strip() for k in entry.keywords.split(',') if k.strip()]

                qa_pair = {
                    'id': next_id,
                    'category': entry.category,
                    'question': entry.question,
                    'answer': entry.answer,
                    'keywords': keywords,
                    'source': 'database'
                }
                self.qa_pairs.append(qa_pair)

                # Add category if not exists
                if entry.category not in self.categories:
                    self.categories[entry.category] = f"{entry.category.title()} questions"

                next_id += 1

            logger.info(f"Loaded {db_entries.count()} entries from database")

        except Exception as e:
            # This can fail during migrations or when DB is not ready
            logger.debug(f"Could not load database entries: {e}")

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into lowercase words.

        Args:
            text: Input text to tokenize

        Returns:
            List of lowercase tokens
        """
        # Convert to lowercase and extract words
        text = text.lower()
        # Remove punctuation and split
        tokens = re.findall(r'\b[a-z]+\b', text)
        return tokens

    def _build_index(self):
        """Build TF-IDF index from Q&A pairs."""
        if not self.qa_pairs:
            return

        # Build vocabulary and document frequency
        doc_freq = defaultdict(int)
        documents = []

        for qa in self.qa_pairs:
            # Combine question and keywords for matching
            text = qa['question'] + ' ' + ' '.join(qa.get('keywords', []))
            tokens = self._tokenize(text)
            documents.append(tokens)

            # Track document frequency (number of docs containing each term)
            unique_tokens = set(tokens)
            for token in unique_tokens:
                doc_freq[token] += 1
                self.vocabulary.add(token)

        # Calculate IDF scores
        num_docs = len(documents)
        for term, freq in doc_freq.items():
            # IDF = log(N / df) + 1 (smoothed)
            self.idf_scores[term] = math.log(num_docs / freq) + 1

        # Build TF-IDF vectors for each document
        for tokens in documents:
            vector = self._compute_tfidf_vector(tokens)
            self.document_vectors.append(vector)

    def _compute_tfidf_vector(self, tokens: List[str]) -> Dict[str, float]:
        """
        Compute TF-IDF vector for a list of tokens.

        Args:
            tokens: List of tokens

        Returns:
            Dictionary mapping terms to TF-IDF scores
        """
        # Calculate term frequency
        tf = defaultdict(int)
        for token in tokens:
            tf[token] += 1

        # Normalize TF and multiply by IDF
        vector = {}
        max_tf = max(tf.values()) if tf else 1

        for term, freq in tf.items():
            normalized_tf = freq / max_tf
            idf = self.idf_scores.get(term, 1)
            vector[term] = normalized_tf * idf

        return vector

    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """
        Calculate cosine similarity between two TF-IDF vectors.

        Args:
            vec1: First TF-IDF vector
            vec2: Second TF-IDF vector

        Returns:
            Cosine similarity score (0 to 1)
        """
        # Find common terms
        common_terms = set(vec1.keys()) & set(vec2.keys())

        if not common_terms:
            return 0.0

        # Calculate dot product
        dot_product = sum(vec1[term] * vec2[term] for term in common_terms)

        # Calculate magnitudes
        mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def retrieve(self, query: str, top_k: int = 3, threshold: float = 0.1) -> List[Tuple[Dict, float]]:
        """
        Retrieve the most relevant Q&A pairs for a query.

        Args:
            query: User's question
            top_k: Number of top results to return
            threshold: Minimum similarity score threshold

        Returns:
            List of (qa_pair, similarity_score) tuples
        """
        if not self.qa_pairs or not self.document_vectors:
            return []

        # Tokenize and vectorize the query
        query_tokens = self._tokenize(query)
        query_vector = self._compute_tfidf_vector(query_tokens)

        # Calculate similarity with all documents
        similarities = []
        for i, doc_vector in enumerate(self.document_vectors):
            similarity = self._cosine_similarity(query_vector, doc_vector)
            if similarity >= threshold:
                similarities.append((self.qa_pairs[i], similarity))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]

    def generate_response(self, query: str) -> Dict:
        """
        Generate a response for the user's query using RAG + Ollama.

        Flow:
        1. Retrieve top-3 relevant Q&A pairs via TF-IDF (RAG step)
        2. Build a grounded prompt and call Ollama (generate step)
        3. Fall back to the top-1 RAG answer if Ollama is unavailable
        4. Fall back to fallback_responses if RAG also finds nothing

        Args:
            query: User's question

        Returns:
            Dictionary containing response, confidence, source, and metadata
        """
        ollama = OllamaClient()

        # Retrieve top-3 relevant Q&A pairs
        results = self.retrieve(query, top_k=3, threshold=0.1)

        if results:
            best_match, confidence = results[0]

            # Build context block from retrieved Q&A pairs
            context_lines = []
            for qa, _ in results:
                context_lines.append(f"Q: {qa['question']}\nA: {qa['answer']}")
            context_block = "\n\n".join(context_lines)

            prompt = (
                "Answer the user's question using ONLY the context provided below.\n"
                "If the context does not address the question, say you don't know.\n\n"
                f"Context:\n{context_block}\n\n"
                f"User: {query}\nAssistant:"
            )

            ollama_response = ollama.generate(prompt, system=SYSTEM_PROMPT)
            if ollama_response:
                return {
                    'response': ollama_response,
                    'confidence': round(confidence, 3),
                    'matched_question': best_match['question'],
                    'category': best_match.get('category', 'general'),
                    'source': 'ollama+rag',
                }

            # Ollama unavailable — return top-1 RAG answer directly
            return {
                'response': best_match['answer'],
                'confidence': round(confidence, 3),
                'matched_question': best_match['question'],
                'category': best_match.get('category', 'general'),
                'source': 'knowledge_base',
            }

        # No RAG results — let Ollama answer freely within platform scope
        prompt = (
            "Answer the user's question as best you can.\n\n"
            f"User: {query}\nAssistant:"
        )
        ollama_response = ollama.generate(prompt, system=SYSTEM_PROMPT)
        if ollama_response:
            return {
                'response': ollama_response,
                'confidence': 0.0,
                'matched_question': None,
                'category': 'general',
                'source': 'ollama',
            }

        # Both RAG and Ollama failed — use static fallback
        import random
        fallback = random.choice(self.fallback_responses) if self.fallback_responses else \
            "I'm sorry, I couldn't understand your question."
        return {
            'response': fallback,
            'confidence': 0.0,
            'matched_question': None,
            'category': 'fallback',
            'source': 'fallback',
        }

    def get_categories(self) -> Dict[str, str]:
        """Return available categories."""
        return self.categories

    def add_qa_pair(self, question: str, answer: str, category: str = 'general',
                    keywords: List[str] = None):
        """
        Dynamically add a Q&A pair to the engine.
        Note: This does not persist to the JSON file.

        Args:
            question: The question text
            answer: The answer text
            category: Category for the Q&A pair
            keywords: List of keywords for matching
        """
        qa_pair = {
            'id': len(self.qa_pairs) + 1,
            'category': category,
            'question': question,
            'answer': answer,
            'keywords': keywords or []
        }

        self.qa_pairs.append(qa_pair)

        # Update the index
        text = question + ' ' + ' '.join(keywords or [])
        tokens = self._tokenize(text)
        vector = self._compute_tfidf_vector(tokens)
        self.document_vectors.append(vector)

    def reload_knowledge_base(self):
        """Reload the knowledge base from disk."""
        self.qa_pairs = []
        self.document_vectors = []
        self.idf_scores = {}
        self.vocabulary = set()

        self._load_knowledge_base()
        self._build_index()


# Singleton instance for the application
_engine_instance = None


def get_rag_engine() -> RAGEngine:
    """
    Get the singleton RAG engine instance.

    Returns:
        RAGEngine instance
    """
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = RAGEngine()
    return _engine_instance
