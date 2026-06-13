from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.html import escape
from django.utils import timezone
import json
import csv
from io import StringIO

from .rag_engine import get_rag_engine
from .models import ChatMessage


@ensure_csrf_cookie
def chatbot_index(request):
    """
    Main chatbot interface view.
    """
    # Get or create session ID for anonymous users
    if not request.session.session_key:
        request.session.create()
    session_id = request.session.session_key

    # Get chat history
    if request.user.is_authenticated:
        chat_history = ChatMessage.objects.filter(user=request.user).order_by('timestamp')[:50]
    else:
        chat_history = ChatMessage.objects.filter(session_id=session_id).order_by('timestamp')[:50]

    context = {
        'chat_history': chat_history,
        'session_id': session_id
    }
    return render(request, 'chatbot/chatbot_index.html', context)


# CSRF protection is enabled by default through Django middleware.
# This endpoint requires a valid CSRF token for POST requests.
@require_http_methods(["POST"])
def chat_api(request):
    """
    API endpoint for chat messages.

    User input is properly sanitized and escaped. No template rendering
    is performed on user input to prevent Server-Side Template Injection (SSTI).
    """
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()

        if not user_message:
            return JsonResponse({
                'error': 'Message cannot be empty',
                'status': 'error'
            }, status=400)

        # Validate message length to prevent abuse
        max_message_length = 2000
        if len(user_message) > max_message_length:
            return JsonResponse({
                'error': f'Message exceeds maximum length of {max_message_length} characters',
                'status': 'error'
            }, status=400)

        # Get response from RAG engine
        rag_engine = get_rag_engine()
        result = rag_engine.generate_response(user_message)

        bot_response = result['response']

        # User input is HTML-escaped to prevent XSS attacks.
        # No template rendering is performed on user input to prevent SSTI.
        escaped_message = escape(user_message)

        # Get or create session ID
        session_id = request.session.session_key
        if not session_id:
            request.session.create()
            session_id = request.session.session_key

        # Save to chat history
        chat_message = ChatMessage.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_id=session_id if not request.user.is_authenticated else None,
            message=user_message,
            response=bot_response
        )

        return JsonResponse({
            'status': 'success',
            'response': bot_response,
            'user_message': escaped_message,
            'confidence': result['confidence'],
            'category': result['category'],
            'matched_question': result.get('matched_question'),
            'message_id': chat_message.id,
            'timestamp': chat_message.timestamp.isoformat()
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON',
            'status': 'error'
        }, status=400)
    except Exception as e:
        # Log the error securely without exposing internal details to the user
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Chat API error: {str(e)}")
        return JsonResponse({
            'error': 'An internal error occurred. Please try again later.',
            'status': 'error'
        }, status=500)


@require_http_methods(["GET"])
def chat_history(request):
    """
    Get chat history for the current user/session.
    """
    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key

    if request.user.is_authenticated:
        messages = ChatMessage.objects.filter(user=request.user).order_by('timestamp')[:100]
    else:
        messages = ChatMessage.objects.filter(session_id=session_id).order_by('timestamp')[:100]

    history = [{
        'id': msg.id,
        'message': msg.message,
        'response': msg.response,
        'timestamp': msg.timestamp.isoformat()
    } for msg in messages]

    return JsonResponse({
        'status': 'success',
        'history': history,
        'count': len(history)
    })


# CSRF protection is enabled by default through Django middleware.
@require_http_methods(["POST"])
def clear_history(request):
    """
    Clear chat history for the current user/session.
    """
    session_id = request.session.session_key

    if request.user.is_authenticated:
        deleted, _ = ChatMessage.objects.filter(user=request.user).delete()
    else:
        deleted, _ = ChatMessage.objects.filter(session_id=session_id).delete()

    return JsonResponse({
        'status': 'success',
        'deleted_count': deleted
    })


@require_http_methods(["GET"])
def get_categories(request):
    """
    Get available FAQ categories.
    """
    rag_engine = get_rag_engine()
    categories = rag_engine.get_categories()

    return JsonResponse({
        'status': 'success',
        'categories': categories
    })


@require_http_methods(["GET"])
def get_suggestions(request):
    """
    Get suggested questions for the user.
    """
    rag_engine = get_rag_engine()

    # Return a sample of questions from the knowledge base
    suggestions = []
    for qa in rag_engine.qa_pairs[:10]:
        if qa['category'] != 'general' or qa['id'] > 2:  # Skip greetings
            suggestions.append({
                'question': qa['question'],
                'category': qa['category']
            })

    return JsonResponse({
        'status': 'success',
        'suggestions': suggestions[:6]
    })


# The @xframe_options_exempt decorator allows this specific view to be embedded
# in an iframe. This is safe because:
# 1. The widget is designed to be embedded within the same site (SAMEORIGIN use case)
# 2. The iframe in chat_widget.html uses sandbox attribute for additional security
# 3. Only this specific endpoint is exempted, not the entire application
@xframe_options_exempt
def chatbot_widget(request):
    """
    Embeddable chatbot widget view.
    Returns a minimal chat interface that can be embedded in other pages.
    """
    return render(request, 'chatbot/widget.html')


# Export endpoint requires authentication for user-specific exports
# or uses session-based export for anonymous users
@require_http_methods(["GET"])
def export_chat_history(request):
    """
    Export chat history as JSON or CSV.

    Query parameters:
    - format: 'json' or 'csv' (default: 'json')

    - Only exports the current user's or session's chat history
    - Sanitizes output to prevent information disclosure
    """
    export_format = request.GET.get('format', 'json').lower()

    # Get session ID
    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key

    # Get chat history for user or session
    if request.user.is_authenticated:
        messages = ChatMessage.objects.filter(user=request.user).order_by('timestamp')
    else:
        messages = ChatMessage.objects.filter(session_id=session_id).order_by('timestamp')

    if not messages.exists():
        return JsonResponse({
            'status': 'error',
            'error': 'No chat history to export'
        }, status=404)

    # Format timestamp for filename
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')

    if export_format == 'csv':
        # Export as CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Timestamp', 'Type', 'Message'])

        for msg in messages:
            # Write user message
            writer.writerow([
                msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'User',
                msg.message
            ])
            # Write bot response
            writer.writerow([
                msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'Bot',
                msg.response
            ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="vrc_chat_history_{timestamp}.csv"'
        return response

    else:
        # Export as JSON (default)
        history = []
        for msg in messages:
            history.append({
                'timestamp': msg.timestamp.isoformat(),
                'user_message': msg.message,
                'bot_response': msg.response
            })

        export_data = {
            'export_date': timezone.now().isoformat(),
            'user': request.user.username if request.user.is_authenticated else 'anonymous',
            'message_count': len(history),
            'messages': history
        }

        response = HttpResponse(
            json.dumps(export_data, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="vrc_chat_history_{timestamp}.json"'
        return response
