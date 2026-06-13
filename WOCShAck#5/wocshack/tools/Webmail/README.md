# TBox Webmail

A deliberately vulnerable email provider designed for CTF challenges and security education.

## Quick Start

### Run the Application

```bash
docker-compose up --build
```

Access at: http://localhost:8080

### Database Management

Flush all data:
```bash
python flush_db.py --confirm
```

Preview what would be deleted:
```bash
python flush_db.py --dry-run
```

Flush specific tables:
```bash
python flush_db.py --confirm --tables Emails
python flush_db.py --confirm --tables users
```

## REST API

The application includes an unauthenticated REST API for programmatic access.

### Quick API Examples

```bash
# Create a user
curl -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"password123"}'

# Send an email
curl -X POST http://localhost:8080/api/emails \
  -H "Content-Type: application/json" \
  -d '{"source":"admin","destination":"alice","subject":"Test","content":"Hello!"}'

# Get user's emails
curl http://localhost:8080/api/emails?user=alice

# List all users
curl http://localhost:8080/api/users
```

**Full API documentation**: See [API_USAGE.md](API_USAGE.md)

## CTF Scenario Setup

### Using the Setup Script

Set up pre-configured CTF scenarios:

```bash
# XSS/CSRF challenge
python setup_ctf_scenario.py --scenario xss-csrf

# IDOR challenge
python setup_ctf_scenario.py --scenario idor

# Account takeover challenge
python setup_ctf_scenario.py --scenario account-takeover

# Phishing scenario
python setup_ctf_scenario.py --scenario phishing

# List all scenarios
python setup_ctf_scenario.py --list
```

### Custom Scenarios

Create a JSON configuration file:

```json
{
  "description": "My custom scenario",
  "users": [
    {"username": "admin", "password": "admin123456"},
    {"username": "user", "password": "user123456"}
  ],
  "emails": [
    {
      "source": "system@tbox.traced",
      "destination": "admin",
      "subject": "Secret Flag",
      "content": "FLAG{custom_scenario_flag}"
    }
  ]
}
```

Load it:
```bash
python setup_ctf_scenario.py --scenario custom --config my_scenario.json
```

## Testing

Run API tests:
```bash
python test_api.py
```

This will:
- Create test users
- Send test emails
- Verify all API endpoints
- Clean up test data

## Architecture

### Components

- **Frontend.py** - Flask application entry point
- **Pages.py** - Web UI routes (authentication required)
- **API.py** - REST API routes (no authentication)
- **Backend.py** - Database and business logic
- **DataBase/** - SQLite database storage

### Database Schema

**Users Table:**
- Name (TEXT, PRIMARY KEY) - Email address (username@tbox.traced)
- Password (TEXT) - SHA256 hash of password

**Emails Table:**
- Id (INTEGER, PRIMARY KEY, AUTOINCREMENT)
- Source (TEXT) - Sender email or name
- Destination (TEXT) - Recipient email address
- Subject (TEXT)
- Content (TEXT)

## Security Warnings

⚠️ **This application is INTENTIONALLY VULNERABLE**

Known vulnerabilities:
- No API authentication
- Weak password hashing (SHA256 without salt)
- Missing CSRF protection
- Insecure session management
- Direct object reference vulnerabilities
- GET-based sensitive operations

**DO NOT use in production!** This is for educational purposes only.

## Development

### File Structure

```
Webmail/
├── docker-compose.yml      # Docker configuration
├── Dockerfile              # Container definition
├── requirements.txt        # Python dependencies
├── flush_db.py            # Database reset tool
├── test_api.py            # API test suite
├── setup_ctf_scenario.py  # CTF scenario setup
├── API_USAGE.md           # Complete API documentation
└── src/
    ├── Frontend.py        # Flask app entry point
    ├── Pages.py           # Web UI routes
    ├── API.py             # REST API routes
    ├── Backend.py         # Database & business logic
    ├── new_user_email_content.py
    ├── DataBase/
    │   └── DataBase.db    # SQLite database
    ├── templates/         # HTML templates
    └── static/            # CSS, JS, images
```

### Adding New API Endpoints

1. Edit `src/API.py`
2. Add route with `@api.route()` decorator
3. Use the `handler` object for database operations
4. Return JSON responses with appropriate status codes
5. Document in `API_USAGE.md`

### Dependencies

- Flask - Web framework
- Python 3.9+
- SQLite3

## Troubleshooting

### Port Already in Use

Change port in `docker-compose.yml`:
```yaml
ports:
  - "8081:80"  # Change 8080 to 8081
```

### Database Locked

Stop all containers and restart:
```bash
docker-compose down
docker-compose up --build
```

### API Not Responding

Check if the container is running:
```bash
docker-compose ps
docker-compose logs
```

## License

Educational use only. See repository root for license information.
