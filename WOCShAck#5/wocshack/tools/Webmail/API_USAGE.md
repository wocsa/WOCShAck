# Webmail API Usage

The Webmail application now includes an unauthenticated REST API for easy programmatic access. All endpoints return JSON responses.

**Base URL**: `http://localhost:8080/api`

## Authentication

**None required** - All API endpoints are intentionally unauthenticated for CTF scenarios and testing.

## Endpoints

### Health Check

Check if the API is running.

```bash
GET /api/health
```

**Response**:
```json
{
  "status": "success",
  "message": "API is running",
  "service": "TBox Webmail API"
}
```

---

### List Users

Get all users in the system.

```bash
GET /api/users
```

**Response**:
```json
{
  "status": "success",
  "count": 2,
  "users": [
    {
      "username": "alice@tbox.traced",
      "password_hash": "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
    },
    {
      "username": "bob@tbox.traced",
      "password_hash": "6cf615d5bcaac778352a8f1f3360d23f02f34ec182e259897fd6ce485d7870d4"
    }
  ]
}
```

---

### Create User

Create a new user account.

```bash
POST /api/users
Content-Type: application/json

{
  "username": "alice",
  "password": "password123"
}
```

**Notes**:
- The `@tbox.traced` suffix is automatically added if not present
- Password must be at least 8 characters
- Username is case-insensitive

**Response** (201 Created):
```json
{
  "status": "success",
  "message": "User created successfully",
  "username": "alice@tbox.traced"
}
```

**Error Responses**:
- `400`: Missing fields or password too short
- `409`: User already exists

---

### Delete User

Delete a user account and all their emails.

```bash
DELETE /api/users/{username}
```

**Example**:
```bash
DELETE /api/users/alice
# or
DELETE /api/users/alice@tbox.traced
```

**Response** (200 OK):
```json
{
  "status": "success",
  "message": "User deleted successfully"
}
```

**Error Response**:
- `404`: User not found

---

### List Emails

Get all emails, optionally filtered by user.

```bash
GET /api/emails?user={username}&limit={number}
```

**Query Parameters**:
- `user` (optional): Filter by destination user (e.g., `alice` or `alice@tbox.traced`)
- `limit` (optional): Limit number of results

**Examples**:
```bash
# Get all emails
GET /api/emails

# Get emails for specific user
GET /api/emails?user=alice

# Get first 10 emails
GET /api/emails?limit=10
```

**Response**:
```json
{
  "status": "success",
  "count": 2,
  "emails": [
    {
      "id": 1,
      "source": "TBox",
      "destination": "alice@tbox.traced",
      "subject": "Welcome !",
      "content": "Welcome to TBox webmail..."
    },
    {
      "id": 2,
      "source": "bob@tbox.traced",
      "destination": "alice@tbox.traced",
      "subject": "Hello",
      "content": "Hi Alice!"
    }
  ]
}
```

---

### Get Email

Get a specific email by ID.

```bash
GET /api/emails/{id}
```

**Example**:
```bash
GET /api/emails/1
```

**Response**:
```json
{
  "status": "success",
  "email": {
    "id": 1,
    "source": "TBox",
    "destination": "alice@tbox.traced",
    "subject": "Welcome !",
    "content": "Welcome to TBox webmail..."
  }
}
```

**Error Response**:
- `404`: Email not found

---

### Send Email

Send an email to a user.

```bash
POST /api/emails
Content-Type: application/json

{
  "source": "bob@tbox.traced",
  "destination": "alice",
  "subject": "Test Subject",
  "content": "Test email content"
}
```

**Notes**:
- `source` can be any string (email address or name)
- `destination` must be an existing user (suffix is auto-added)
- All fields are required

**Response** (201 Created):
```json
{
  "status": "success",
  "message": "Email sent successfully"
}
```

**Error Responses**:
- `400`: Missing required fields
- `404`: Destination user does not exist

---

### Delete Email

Delete an email by ID.

```bash
DELETE /api/emails/{id}
```

**Example**:
```bash
DELETE /api/emails/1
```

**Response**:
```json
{
  "status": "success",
  "message": "Email deleted successfully"
}
```

**Error Response**:
- `404`: Email not found

---

## Usage Examples

### Using curl

```bash
# Create a user
curl -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "password123"}'

# Send an email
curl -X POST http://localhost:8080/api/emails \
  -H "Content-Type: application/json" \
  -d '{
    "source": "admin@tbox.traced",
    "destination": "alice",
    "subject": "Welcome",
    "content": "Welcome to our service!"
  }'

# Get user emails
curl http://localhost:8080/api/emails?user=alice

# Delete an email
curl -X DELETE http://localhost:8080/api/emails/1

# Delete a user
curl -X DELETE http://localhost:8080/api/users/alice
```

### Using Python requests

```python
import requests

BASE_URL = "http://localhost:8080/api"

# Create a user
response = requests.post(f"{BASE_URL}/users", json={
    "username": "alice",
    "password": "password123"
})
print(response.json())

# Send an email
response = requests.post(f"{BASE_URL}/emails", json={
    "source": "admin@tbox.traced",
    "destination": "alice",
    "subject": "Test",
    "content": "This is a test email"
})
print(response.json())

# Get emails for a user
response = requests.get(f"{BASE_URL}/emails", params={"user": "alice"})
print(response.json())

# Delete user
response = requests.delete(f"{BASE_URL}/users/alice")
print(response.json())
```

### Using JavaScript fetch

```javascript
const BASE_URL = "http://localhost:8080/api";

// Create a user
fetch(`${BASE_URL}/users`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    username: "alice",
    password: "password123"
  })
}).then(r => r.json()).then(console.log);

// Send an email
fetch(`${BASE_URL}/emails`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    source: "admin@tbox.traced",
    destination: "alice",
    subject: "Test",
    content: "Test email"
  })
}).then(r => r.json()).then(console.log);

// Get emails
fetch(`${BASE_URL}/emails?user=alice`)
  .then(r => r.json())
  .then(console.log);
```

## CTF Scenario Setup

Example script to quickly set up a CTF scenario:

```python
import requests

BASE_URL = "http://localhost:8080/api"

# Create admin user
requests.post(f"{BASE_URL}/users", json={
    "username": "admin",
    "password": "admin123456"
})

# Create victim user
requests.post(f"{BASE_URL}/users", json={
    "username": "victim",
    "password": "victim123456"
})

# Send flag email to admin
requests.post(f"{BASE_URL}/emails", json={
    "source": "system@tbox.traced",
    "destination": "admin",
    "subject": "Secret Flag",
    "content": "FLAG{secret_flag_here}"
})

# Send phishing email to victim
requests.post(f"{BASE_URL}/emails", json={
    "source": "admin@tbox.traced",
    "destination": "victim",
    "subject": "Click this link",
    "content": "Please visit: http://attacker.com/exploit"
})

print("CTF scenario set up successfully!")
```

## Security Notes

⚠️ **This API is intentionally insecure for CTF purposes:**
- No authentication required
- No rate limiting
- Password hashes are exposed in user listings
- No input validation beyond basic checks
- No CSRF protection

**Do not use in production environments!**
