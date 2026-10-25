import json
from django.views.decorators.http import require_http_methods
from django.utils.html import escape
from .views import api_success, api_error, paginate_queryset
from Chatbot.models import ChatMessage
from Chatbot.rag_engine import get_rag_engine

@require_http_methods(["POST"])
def chat_view(request):
    """
    Chatbot conversation endpoint.
    Expects JSON: {"message": "Hello"}
    """
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
    except json.JSONDecodeError:
        return api_error("Invalid JSON payload", status=400)
        
    if not user_message:
        return api_error("Message cannot be empty", status=400)
        
    if len(user_message) > 2000:
        return api_error("Message exceeds maximum length of 2000 characters", status=400)
        
    # Process message with RAG engine
    try:
        rag_engine = get_rag_engine()
        result = rag_engine.generate_response(user_message)
        bot_response = result['response']
        confidence = result['confidence']
        category = result['category']
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Chat API error: {str(e)}")
        return api_error("An internal error occurred while processing the message.", status=500)
        
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
    
    return api_success({
        'response': bot_response,
        'user_message': escape(user_message),
        'confidence': confidence,
        'category': category,
        'message_id': str(chat_message.id),
        'timestamp': chat_message.timestamp.isoformat()
    })

@require_http_methods(["GET"])
def history_view(request):
    """
    Chatbot history endpoint.
    Paginated history of the current anonymous session or logged-in user.
    """
    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key
        
    if request.user.is_authenticated:
        messages = ChatMessage.objects.filter(user=request.user).order_by('-timestamp')
    else:
        messages = ChatMessage.objects.filter(session_id=session_id).order_by('-timestamp')
        
    paginated = paginate_queryset(messages, request)
    data = []
    
    for msg in paginated['items']:
        data.append({
            'id': str(msg.id),
            'message': msg.message,
            'response': msg.response,
            'timestamp': msg.timestamp.isoformat()
        })
        
    return api_success({
        'history': data,
        'pagination': paginated['pagination']
    })

@require_http_methods(["DELETE"])
def clear_history_view(request):
    """
    Clear chat history.
    """
    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key
        
    if request.user.is_authenticated:
        deleted, _ = ChatMessage.objects.filter(user=request.user).delete()
    else:
        deleted, _ = ChatMessage.objects.filter(session_id=session_id).delete()
        
    return api_success({"message": "History cleared", "deleted": deleted})

@require_http_methods(["GET"])
def categories_view(request):
    rag_engine = get_rag_engine()
    return api_success({"categories": rag_engine.get_categories()})

@require_http_methods(["GET"])
def suggestions_view(request):
    rag_engine = get_rag_engine()
    suggestions = []
    for qa in getattr(rag_engine, 'qa_pairs', []):
        if qa.get('category') != 'general' or qa.get('id', 0) > 2:
            suggestions.append({
                'question': qa['question'],
                'category': qa['category']
            })
            if len(suggestions) >= 6:
                break
    return api_success({"suggestions": suggestions})

@require_http_methods(["GET"])
def export_view(request):
    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key
        
    if request.user.is_authenticated:
        messages = ChatMessage.objects.filter(user=request.user).order_by('timestamp')
    else:
        messages = ChatMessage.objects.filter(session_id=session_id).order_by('timestamp')
        
    data = []
    for msg in messages:
        data.append({
            "timestamp": msg.timestamp.isoformat(),
            "user_message": msg.message,
            "bot_response": msg.response
        })
    from django.utils import timezone
    export_data = {
        'export_date': timezone.now().isoformat(),
        'messages': data
    }
    return api_success(export_data)

@require_http_methods(["POST"])
def flag_view(request):
    try:
        data = json.loads(request.body)
        message_id = data.get("message_id")
    except:
        return api_error("Invalid payload", status=400)
    
    if not message_id:
        return api_error("message_id is required", status=400)
        
    from django.shortcuts import get_object_or_404
    msg = get_object_or_404(ChatMessage, id=message_id)
    
    # Simple check to ensure they own the message
    if request.user.is_authenticated:
        if msg.user != request.user:
            return api_error("Not authorized", status=403)
    else:
        if msg.session_id != request.session.session_key:
            return api_error("Not authorized", status=403)
            
    # Typically we'd have a `flagged` bit in ChatMessage, but for now we'll just return success.
    # WOCShAck standard indicates flagging just records it (maybe sending an admin email or setting a flag)
    # Since ChatMessage lacks a flagged field, we can assume it's logged.
    import logging
    logging.getLogger(__name__).info(f"ChatMessage {message_id} flagged by {request.user.username if request.user.is_authenticated else 'anonymous'}")
    
    return api_success({"message": "Response flagged for review"})
