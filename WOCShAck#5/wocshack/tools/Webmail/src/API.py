from flask import Blueprint, request, jsonify
from Backend import Handler
import hashlib

api = Blueprint('api', __name__, url_prefix='/api')
handler = Handler()


@api.route("/users", methods=['GET'])
def get_users():
    """List all users in the system"""
    users = handler.database.get_all_users()
    user_list = [{"username": user[0], "password_hash": user[1]} for user in users]
    return jsonify({
        "status": "success",
        "count": len(user_list),
        "users": user_list
    }), 200


@api.route("/users", methods=['POST'])
def create_user():
    """Create a new user

    Body (JSON):
        - username: string (without @tbox.traced suffix)
        - password: string (min 8 characters)
    """
    data = request.get_json()

    if not data or 'username' not in data or 'password' not in data:
        return jsonify({
            "status": "error",
            "message": "Missing username or password"
        }), 400

    username = data['username'].strip()
    password = data['password']

    # Add @tbox.traced suffix if not present
    if not username.endswith("@tbox.traced"):
        username += "@tbox.traced"

    username = username.casefold()

    # Validate password length
    if len(password) < 8:
        return jsonify({
            "status": "error",
            "message": "Password must be at least 8 characters"
        }), 400

    # Check if user already exists
    if handler.database.get_user_by_id(username) is not None:
        return jsonify({
            "status": "error",
            "message": "User already exists"
        }), 409

    # Create user
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    handler.add_user(username, hashed_password)

    return jsonify({
        "status": "success",
        "message": "User created successfully",
        "username": username
    }), 201


@api.route("/users/<username>", methods=['DELETE'])
def delete_user(username):
    """Delete a user by username

    Query params:
        - force: boolean (optional) - Skip password verification
    """
    # Add @tbox.traced suffix if not present
    if not username.endswith("@tbox.traced"):
        username += "@tbox.traced"

    username = username.casefold()

    # Check if user exists
    if handler.database.get_user_by_id(username) is None:
        return jsonify({
            "status": "error",
            "message": "User not found"
        }), 404

    # Force delete without password check
    handler.database.delete_user(username)
    handler.database.delete_email_by_id(username)

    return jsonify({
        "status": "success",
        "message": "User deleted successfully"
    }), 200


@api.route("/emails", methods=['GET'])
def get_emails():
    """Get emails, optionally filtered by user

    Query params:
        - user: string (optional) - Filter by destination user
        - limit: int (optional) - Limit number of results
    """
    user = request.args.get('user')
    limit = request.args.get('limit', type=int)

    if user:
        # Add @tbox.traced suffix if not present
        if not user.endswith("@tbox.traced"):
            user += "@tbox.traced"
        user = user.casefold()
        emails = handler.get_emails(user)
    else:
        # Get all emails
        handler.database.cursor.execute('SELECT * FROM Emails')
        emails = handler.database.cursor.fetchall()

    # Apply limit if specified
    if limit:
        emails = emails[:limit]

    email_list = [{
        "id": email[0],
        "source": email[1],
        "destination": email[2],
        "subject": email[3],
        "content": email[4]
    } for email in emails]

    return jsonify({
        "status": "success",
        "count": len(email_list),
        "emails": email_list
    }), 200


@api.route("/emails/<int:email_id>", methods=['GET'])
def get_email(email_id):
    """Get a specific email by ID"""
    email = handler.get_email_by_id(email_id)

    if not email or len(email) == 0:
        return jsonify({
            "status": "error",
            "message": "Email not found"
        }), 404

    email_data = email[0]
    return jsonify({
        "status": "success",
        "email": {
            "id": email_data[0],
            "source": email_data[1],
            "destination": email_data[2],
            "subject": email_data[3],
            "content": email_data[4]
        }
    }), 200


@api.route("/emails", methods=['POST'])
def send_email():
    """Send an email

    Body (JSON):
        - source: string (sender email or name)
        - destination: string (recipient username)
        - subject: string
        - content: string
    """
    data = request.get_json()

    if not data:
        return jsonify({
            "status": "error",
            "message": "Invalid JSON body"
        }), 400

    source = data.get('source', '')
    destination = data.get('destination', '')
    subject = data.get('subject', '')
    content = data.get('content', '')

    # Add @tbox.traced suffix to destination if not present
    if destination and not destination.endswith("@tbox.traced"):
        destination += "@tbox.traced"

    destination = destination.casefold()

    result = handler.send_email(source, destination, subject, content)

    if result == -1:
        return jsonify({
            "status": "error",
            "message": "All fields are required"
        }), 400
    elif result == -2:
        return jsonify({
            "status": "error",
            "message": "Destination user does not exist"
        }), 404
    elif result == 0:
        return jsonify({
            "status": "success",
            "message": "Email sent successfully"
        }), 201

    return jsonify({
        "status": "error",
        "message": "Unknown error"
    }), 500


@api.route("/emails/<int:email_id>", methods=['DELETE'])
def delete_email(email_id):
    """Delete an email by ID"""
    # Check if email exists
    email = handler.get_email_by_id(email_id)
    if not email or len(email) == 0:
        return jsonify({
            "status": "error",
            "message": "Email not found"
        }), 404

    # Delete the email
    handler.database.cursor.execute('DELETE FROM Emails WHERE Id = ?', (email_id,))
    handler.database.conn.commit()

    return jsonify({
        "status": "success",
        "message": "Email deleted successfully"
    }), 200


@api.route("/health", methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        "status": "success",
        "message": "API is running",
        "service": "TBox Webmail API"
    }), 200
