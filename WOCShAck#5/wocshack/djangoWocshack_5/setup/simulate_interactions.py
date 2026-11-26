"""
simulate_interactions.py — API-driven user interaction simulator.

Mimics realistic user behaviour on the V.R.C platform using the REST API
and Ollama-generated content. Useful for demo traffic and load testing
without touching the Django ORM directly.

Usage:
  python setup/simulate_interactions.py [options]

  --url          Base URL of the running Django app  (env: VRC_URL)
  --ollama-url   Ollama server URL                   (env: OLLAMA_URL)
  --model        Ollama model name                   (env: OLLAMA_MODEL)
  --modules      forum community shopping marketplace (or 'all')
  --rounds       Interaction rounds per module (default 3)
  --delay        Seconds between mutating calls (default 1.0)
  --users        Comma-separated usernames to restrict to
  --dry-run      Log actions without sending POST requests
  -v / --verbose Show full request/response details
"""
import argparse
import csv
import json
import os
import random
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

try:
    from tqdm import tqdm as _tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ---------------------------------------------------------------------------
# Thread-safe printing
# ---------------------------------------------------------------------------

_print_lock = threading.Lock()


def _print(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


# ---------------------------------------------------------------------------
# Fallback content (used when Ollama is unavailable)
# ---------------------------------------------------------------------------

_FORUM_TOPICS = [
    (
        "Thoughts on the new CSS loader trends?",
        "I've been exploring loader animations lately and noticed some fascinating patterns emerging. "
        "Minimalist designs seem to be winning out over complex ones. What are your thoughts on where things are headed?",
    ),
    (
        "Best practices for smooth cross-browser animations",
        "After months of testing CSS loaders across browsers I've settled on a few rules: "
        "always use `transform` and `opacity` for GPU acceleration, keep `@keyframes` simple, "
        "and test on Safari early. Happy to share more details if anyone's interested.",
    ),
    (
        "Looking for feedback on my latest CSS loader",
        "Just published a new spinner to the marketplace. It uses a conic-gradient approach that I haven't "
        "seen done elsewhere. Would love community feedback before I promote it more widely.",
    ),
    (
        "When is JavaScript animation better than CSS?",
        "I know CSS is usually the right call for loaders, but I've hit a few cases where JS gave me "
        "far more control. Physics-based easing and sequenced multi-element loaders come to mind. "
        "Anyone else found CSS falling short?",
    ),
    (
        "CSS custom properties for theming — a game changer",
        "Started using CSS custom properties to make my loaders themeable and it's completely changed "
        "how I work. One file, infinite colour schemes. If you're not doing this yet, start today.",
    ),
]

_REPLIES = [
    "Really great point — I've run into the exact same thing and your approach makes a lot of sense.",
    "Thanks for sharing this. I'm going to experiment with it on my current project.",
    "Interesting take. Have you tried combining this with CSS custom properties for theming?",
    "Agreed on the performance angle — transform/opacity is the only safe bet for 60 fps.",
    "This is exactly the kind of discussion I was hoping to find here. Following for updates.",
    "I had similar results but ran into issues on older Android WebViews. Did you test there?",
    "Good writeup. The Safari gotcha is real — I spent a week debugging that one last year.",
]

_MESSAGES = [
    "Hey! Saw your CSS loader in the marketplace — really clean work, nice job.",
    "Hi there! Wanted to connect with another CSS enthusiast. Hope you're enjoying the platform.",
    "Hello! Your recent forum post was super helpful, thank you for taking the time.",
    "Hey! Great portfolio. Would love to collaborate on something sometime.",
    "Hi! I'm relatively new here and your profile caught my eye. Nice to meet you!",
]

_REVIEWS = [
    ("Great loader!", "Really smooth animation with minimal CPU overhead. Works everywhere I tested."),
    ("Clean and minimal", "Exactly what I was looking for. Integrates in seconds and looks great."),
    ("Good value", "Solid CSS loader — code is clean and the animation is buttery smooth."),
    ("Exactly as described", "Does what it says on the tin. No bloat, no dependencies. Happy with it."),
    ("Nice work", "Smooth, well-optimised, and easy to customise. Would buy from this dev again."),
]

_BLOG_POSTS = [
    (
        "CSS Performance Tricks That Actually Matter",
        "CSS performance is more nuanced than most developers think. The key wins are: use transform "
        "and opacity for animations, minimise paint operations, and leverage will-change sparingly. "
        "I benchmarked these on a real project and saw 40% faster frame rates. Browser DevTools "
        "paint profiling is your best friend here — use it before optimising anything.",
    ),
    (
        "Dark Mode Done Right with Custom Properties",
        "Implementing dark mode with CSS custom properties is the cleanest approach. Define your "
        "colour palette on :root, then override in a [data-theme='dark'] selector. Add "
        "prefers-color-scheme detection for automatic switching. One stylesheet, zero JavaScript "
        "required for the toggle itself.",
    ),
    (
        "Why I Stopped Using CSS Frameworks",
        "After years of Bootstrap and Tailwind, I went back to writing raw CSS. Custom properties, "
        "Grid, and Flexbox cover nearly every layout need. The result is smaller bundles and complete "
        "control over my styles. If you know CSS well, a framework is often more overhead than help.",
    ),
    (
        "Accessible Animations: The prefers-reduced-motion Guide",
        "Beautiful animations should not come at the cost of accessibility. Wrap all non-essential "
        "animations in a @media (prefers-reduced-motion: reduce) block. Provide pause controls for "
        "anything looping. Test with a screen reader before shipping — it takes five minutes and "
        "saves real users real pain.",
    ),
    (
        "Conic-Gradient Spinners: A Deep Dive",
        "The conic-gradient CSS function makes it trivial to build progress-ring and pie-chart "
        "loaders without SVG or JavaScript. Combine it with @property for smooth animated fills. "
        "Browser support is now excellent — only Safari needed a prefix before 2022 and that prefix "
        "is no longer required.",
    ),
]

_EVENTS = [
    (
        "CSS Loader Workshop: Animations from Scratch",
        "A hands-on session covering CSS loader animation techniques, performance considerations, "
        "and cross-browser compatibility. We will build three loaders live — spinner, progress bar, "
        "and skeleton screen. Beginners welcome; bring a code editor.",
    ),
    (
        "Frontend Dev Meetup: Modern CSS in 2026",
        "Monthly meetup focused on modern CSS — Grid subgrid, container queries, @layer, and "
        "the new colour spaces. Come share what you are building and get feedback from the community.",
    ),
    (
        "Webinar: Accessible UI Design Patterns",
        "Learn how to make your CSS work for everyone. Topics include colour contrast ratios, "
        "motion sensitivity, focus management, and keyboard navigation. WCAG 2.2 compliance "
        "walkthrough included.",
    ),
    (
        "CSS Art Challenge: Community Showcase",
        "Submit your best pure-CSS artwork and vote for your favourites. This month's theme is "
        "'Loading States'. Winners get a featured slot on the VRC platform homepage.",
    ),
    (
        "Deep Dive: CSS Custom Properties and Design Tokens",
        "Explore how design tokens powered by CSS custom properties can unify your design system "
        "across light mode, dark mode, and multiple brand themes — all from a single stylesheet.",
    ),
]

_BLOG_COMMENTS = [
    "Great post! This really clarified things for me.",
    "Thanks for sharing — I have been struggling with this exact issue.",
    "Very well explained. Saving this for reference.",
    "Interesting perspective. Worth checking browser support before shipping though.",
    "This approach worked perfectly for my project. Much appreciated.",
    "I had a similar experience. The performance difference is noticeable.",
]

# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are roleplaying as a real user on the V.R.C CSS loader marketplace. "
    "Be concise, natural, and on-topic. Plain text only — no markdown unless asked."
)


class OllamaClient:
    """Thin HTTP wrapper for Ollama. Returns None on any error so callers fall back gracefully."""

    def __init__(self, base_url: str, model: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.available: Optional[bool] = None  # None = unchecked

    def check(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            self.available = r.ok
        except Exception:
            self.available = False
        return bool(self.available)

    def generate(self, prompt: str, system: Optional[str] = None, timeout: Optional[int] = None) -> Optional[str]:
        if self.available is False:
            return None
        try:
            messages = [{"role": "user", "content": prompt}]
            if system:
                messages.insert(0, {"role": "system", "content": system})

            use_timeout = timeout if timeout is not None else self.timeout
            r = requests.post(f"{self.base_url}/api/chat", json={
                "model": self.model,
                "messages": messages,
                "stream": False
            }, timeout=use_timeout)
            if not r.ok:
                try:
                    err = r.json().get("error", r.text)
                except Exception:
                    err = r.text
                _print(f"  [!] Ollama error ({r.status_code}): {err}")
                # Model-not-found is a config error, not a server outage — fall back per-call
                if r.status_code == 404 and "not found" in err.lower():
                    return None
                self.available = False
                return None
            text = r.json().get("message", {}).get("content", "").strip()
            return text or None
        except requests.exceptions.ConnectionError as e:
            _print(f"  [!] Ollama connection error: {e}")
            self.available = False
            return None
        except Exception as e:
            _print(f"  [!] Ollama generation error: {e}\n{traceback.format_exc()}")
            self.available = False
            return None


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------

@dataclass
class Persona:
    username: str
    email: str
    first_name: str
    last_name: str
    password: str
    biography: str
    bank_pin: str
    initial_balance: float
    api_key: str
    persona_type: str = field(init=False)

    def __post_init__(self):
        bio = self.biography.lower()
        if any(k in bio for k in ["developer", "software", "backend", "frontend", "mobile"]):
            self.persona_type = "developer"
        elif any(k in bio for k in ["designer", "ux/ui", "creative"]):
            self.persona_type = "designer"
        elif any(k in bio for k in ["entrepreneur", "marketing", "content creator"]):
            self.persona_type = "business"
        elif any(k in bio for k in ["manager", "product", "qa", "devops", "cybersecurity"]):
            self.persona_type = "staff"
        else:
            self.persona_type = "user"


def load_personas(csv_path: Path, filter_users: Optional[list] = None) -> list:
    personas = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if filter_users and row["username"] not in filter_users:
                continue
            personas.append(Persona(
                username=row["username"],
                email=row["email"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                password=row["password"],
                biography=row["biography"],
                bank_pin=row["bank_pin"],
                initial_balance=float(row["initial_balance"]),
                api_key=row["api_key"],
            ))
    return personas


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class APIClient:
    """Session-based HTTP client for one persona. Handles login, CSRF, and dry-run."""

    def __init__(self, persona: Persona, base_url: str, delay: float, dry_run: bool, verbose: bool):
        self.persona = persona
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self.dry_run = dry_run
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": persona.api_key})
        self.logged_in = False

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _csrf(self) -> str:
        return self.session.cookies.get("csrftoken", "")

    def login(self) -> bool:
        try:
            # Fetch login page to get CSRF cookie
            self.session.get(self._url("/account/login/"), timeout=10)
            csrf = self._csrf()
            r = self.session.post(
                self._url("/account/login/"),
                data={
                    "username": self.persona.username,
                    "password": self.persona.password,
                    "csrfmiddlewaretoken": csrf,
                },
                headers={"Referer": self._url("/account/login/"), "X-CSRFToken": csrf},
                allow_redirects=True,
                timeout=10,
            )
            if "/account/verification/" in r.url:
                _print(f"  [!] {self.persona.username}: 2FA required — skipping")
                return False
            # If we're still on login with an error, reject
            if "/account/login/" in r.url and r.status_code == 200:
                _print(f"  [!] {self.persona.username}: Login failed (bad credentials?)")
                return False
            self.logged_in = True
            if self.verbose:
                _print(f"  [+] {self.persona.username}: logged in ({r.url})")
            return True
        except Exception as e:
            _print(f"  [!] {self.persona.username}: Login error — {e}\n{traceback.format_exc()}")
            return False

    def get(self, path: str, params: dict = None) -> Optional[dict]:
        try:
            r = self.session.get(self._url(path), params=params, timeout=15)
            if self.verbose:
                _print(f"    GET {path} → {r.status_code}")
            return r.json() if r.ok else None
        except Exception as e:
            if self.verbose:
                _print(f"    GET {path} → error: {e}\n{traceback.format_exc()}")
            return None

    def post(self, path: str, body: dict = None, form: bool = False, raw: bool = False) -> Optional[dict]:
        """Send a POST request.

        raw=True returns the JSON body even on 4xx so callers can inspect error details.
        Without raw=True, any non-2xx response returns None (original behaviour).
        """
        if self.dry_run:
            snippet = json.dumps(body or {})[:80]
            _print(f"  [dry] POST {path}  {snippet}")
            return {"success": True, "data": {}}
        csrf = self._csrf()
        headers = {"X-CSRFToken": csrf, "Referer": self._url(path)}
        try:
            if form:
                data = body or {}
                data["csrfmiddlewaretoken"] = csrf
                r = self.session.post(self._url(path), data=data, headers=headers, timeout=15)
            else:
                headers["Content-Type"] = "application/json"
                r = self.session.post(self._url(path), json=body, headers=headers, timeout=15)
            if self.verbose:
                _print(f"    POST {path} → {r.status_code}")
            time.sleep(self.delay)
            if r.ok:
                try:
                    return r.json()
                except Exception:
                    return {"success": True, "data": {}}
            if self.verbose:
                _print(f"      {r.text}")
            if raw:
                try:
                    return r.json()
                except Exception:
                    return {"success": False, "error": r.text}
            return None
        except Exception as e:
            if self.verbose:
                _print(f"    POST {path} → error: {e}\n{traceback.format_exc()}")
            return None


# ---------------------------------------------------------------------------
# Stats (thread-safe)
# ---------------------------------------------------------------------------

class Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.done = self.skipped = self.failed = 0

    def ok(self):
        with self._lock:
            self.done += 1

    def skip(self):
        with self._lock:
            self.skipped += 1

    def fail(self):
        with self._lock:
            self.failed += 1

    def record(self, result):
        with self._lock:
            if result is None:
                self.failed += 1
            elif result == "skip":
                self.skipped += 1
            else:
                self.done += 1


# ---------------------------------------------------------------------------
# Content generators
# ---------------------------------------------------------------------------

def _forum_topic(ollama: OllamaClient, persona: Persona) -> tuple:
    subjects = [
        "CSS loading animation performance",
        "browser compatibility for CSS animations",
        "best CSS loader designs for dark mode",
        "tips for minimalist loaders",
        "CSS custom properties for theming",
        "using conic-gradient for spinner loaders",
        "SVG vs CSS for loaders",
    ]
    subject = random.choice(subjects)
    raw = ollama.generate(
        f"Write a forum post about '{subject}' from a {persona.persona_type}'s perspective. "
        "Output ONLY: first line = the title, blank line, then 3-5 sentence body. No labels.",
        system=_SYSTEM,
    )
    if raw:
        parts = raw.strip().split("\n", 1)
        title = parts[0].strip()[:180]
        body = parts[1].strip()[:3000] if len(parts) > 1 else raw[:3000]
        if title and body:
            return title, body
    _print("    [!] Falling back to canned forum topic")
    return random.choice(_FORUM_TOPICS)


def _forum_reply(ollama: OllamaClient, topic_title: str) -> str:
    raw = ollama.generate(
        f'Reply to this forum topic in 2-4 sentences: "{topic_title[:120]}"',
        system=_SYSTEM,
    )
    if not raw:
        _print("    [!] Falling back to canned forum reply")
    return (raw.strip()[:2000] if raw else random.choice(_REPLIES))


def _dm_message(ollama: OllamaClient, recipient: str) -> str:
    raw = ollama.generate(
        f"Write a short friendly 2-3 sentence message to {recipient} about CSS loaders or the V.R.C platform.",
        system=_SYSTEM,
    )
    if not raw:
        _print("    [!] Falling back to canned DM")
    return (raw.strip()[:500] if raw else random.choice(_MESSAGES))


def _review(ollama: OllamaClient, name: str, rating: int) -> tuple:
    raw = ollama.generate(
        f"Write a CSS loader review in 1-2 sentences. Product: '{name}'. Rating: {rating}/5. "
        "First line = short title (max 8 words). Second line = review body.",
        system=_SYSTEM,
    )
    if raw:
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        if len(lines) >= 2:
            return lines[0][:100], " ".join(lines[1:])[:500]
        if lines:
            return lines[0][:100], lines[0][:500]
    _print(f"    [!] Falling back to canned review for {name}")
    return random.choice(_REVIEWS)


def _blog_post(ollama: OllamaClient, persona: "Persona") -> tuple:
    subjects = [
        "CSS performance optimisation tips",
        "dark mode with CSS custom properties",
        "conic-gradient spinner loaders",
        "responsive design without a framework",
        "accessible CSS animations",
        "CSS Grid advanced layouts",
        "CSS custom properties for theming",
    ]
    subject = random.choice(subjects)
    raw = ollama.generate(
        f"Write a technical blog post about '{subject}' from a {persona.persona_type}'s perspective. "
        "Output ONLY: first line = blog title (max 10 words), blank line, then 4-6 sentence body. "
        "No markdown headers, no labels.",
        system=_SYSTEM,
    )
    if raw:
        parts = raw.strip().split("\n", 1)
        title = parts[0].strip()[:180]
        body = parts[1].strip()[:4000] if len(parts) > 1 else raw[:4000]
        if title and body:
            return title, body
    _print("    [!] Falling back to canned blog post")
    return random.choice(_BLOG_POSTS)


def _event_content(ollama: OllamaClient, event_type: str) -> tuple:
    topics = [
        f"CSS animations {event_type}",
        f"modern frontend CSS {event_type}",
        f"accessible UI design {event_type}",
        f"CSS loader showcase {event_type}",
        f"CSS custom properties deep dive",
    ]
    topic = random.choice(topics)
    raw = ollama.generate(
        f"Write a community event listing. Event type: {event_type}. Topic: '{topic}'. "
        "Output ONLY: first line = event title (max 8 words), blank line, then 2-3 sentence description.",
        system=_SYSTEM,
    )
    if raw:
        parts = raw.strip().split("\n", 1)
        title = parts[0].strip()[:180]
        desc = parts[1].strip()[:1000] if len(parts) > 1 else raw[:1000]
        if title and desc:
            return title, desc
    _print("    [!] Falling back to canned event content")
    title, desc = random.choice(_EVENTS)
    return title, desc


def _blog_comment(ollama: OllamaClient, post_title: str) -> str:
    raw = ollama.generate(
        f'Write a 1-2 sentence comment on this blog post: "{post_title[:120]}"',
        system=_SYSTEM,
    )
    if not raw:
        _print("    [!] Falling back to canned blog comment")
    return (raw.strip()[:500] if raw else random.choice(_BLOG_COMMENTS))


# ---------------------------------------------------------------------------
# Module simulators — one round each
# ---------------------------------------------------------------------------

def simulate_forum(personas: list, clients: dict, ollama: OllamaClient, args, stats: Stats, rnd: int):
    sample = random.sample(personas, min(len(personas), 5))
    for persona in sample:
        client = clients[persona.username]
        if not client.logged_in:
            continue

        # List categories
        resp = client.get("/api/forum/categories/")
        cats = (resp or {}).get("data", {}).get("categories", [])
        if not cats:
            stats.fail()
            continue
        cat = random.choice(cats)

        # Create a topic
        title, body = _forum_topic(ollama, persona)
        result = client.post("/api/forum/topics/", {"category_id": cat["id"], "title": title, "content": body})
        stats.record(result)
        action = "created" if result else "FAILED"
        _print(f"  [forum] {persona.username} → {action} topic: {title[:55]}")

        # Reply to an existing topic
        resp = client.get("/api/forum/topics/")
        topics = (resp or {}).get("data", {}).get("topics", [])
        if not topics:
            continue
        topic = random.choice(topics)
        reply_text = _forum_reply(ollama, topic["title"])
        result = client.post(f"/api/forum/topics/{topic['id']}/reply/", {"content": reply_text})
        stats.record(result)
        action = "replied to" if result else "FAILED reply on"
        _print(f"  [forum] {persona.username} → {action}: {topic['title'][:55]}")

        # Like a random post in that topic
        detail = client.get(f"/api/forum/topics/{topic['id']}/")
        posts = (detail or {}).get("data", {}).get("posts", [])
        if posts:
            post = random.choice(posts)
            result = client.post(f"/api/forum/posts/{post['id']}/like/", {})
            stats.record(result)


_EVENT_SLOTS = [
    ("2026-05-08T14:00", "2026-05-08T16:00"),
    ("2026-05-12T10:00", "2026-05-12T12:00"),
    ("2026-05-16T15:00", "2026-05-16T17:00"),
    ("2026-05-20T09:00", "2026-05-20T11:00"),
    ("2026-05-24T14:00", "2026-05-24T16:30"),
    ("2026-05-28T11:00", "2026-05-28T13:00"),
]
_EVENT_TYPES = ["workshop", "webinar", "meetup"]


def simulate_community(personas: list, clients: dict, ollama: OllamaClient, args, stats: Stats, rnd: int):
    usernames = [p.username for p in personas]
    creators = [p for p in personas if p.persona_type in ("developer", "staff")]

    sample = random.sample(personas, min(len(personas), 4))
    for persona in sample:
        client = clients[persona.username]
        if not client.logged_in:
            continue

        # Send a friend request
        others = [u for u in usernames if u != persona.username]
        if others:
            target = random.choice(others)
            result = client.post("/api/community/friends/add/", {"username": target}, raw=True)
            already = any(
                phrase in (result or {}).get("error", "").lower()
                for phrase in ("already friends", "already sent", "pending request")
            )
            if already:
                stats.skip()
            elif result and result.get("success") is not False:
                stats.ok()
                _print(f"  [community] {persona.username} → friend request → {target}")
            else:
                stats.fail()
                _print(f"  [community] {persona.username} → FAILED friend request → {target}")

        # Message flow
        resp = client.get("/api/community/messages/")
        convs = (resp or {}).get("data", {}).get("conversations", [])
        if convs:
            conv = random.choice(convs)
            other_name = (conv.get("participants") or ["friend"])[0]
            msg = _dm_message(ollama, other_name)
            result = client.post("/api/community/messages/send/", {
                "conversation_id": conv["id"],
                "content": msg,
            })
            stats.record(result)
            if result:
                _print(f"  [community] {persona.username} → message to {other_name}")
        else:
            # Start a new conversation
            other = random.choice([p for p in personas if p.username != persona.username])
            prof = client.get(f"/api/account/profile/{other.username}/")
            uid = (prof or {}).get("data", {}).get("user", {}).get("id")
            if uid:
                start = client.post(f"/api/community/messages/start/{uid}/", {})
                stats.record(start)
                cid = (start or {}).get("data", {}).get("conversation_id")
                if cid:
                    msg = _dm_message(ollama, other.first_name)
                    client.post("/api/community/messages/send/", {
                        "conversation_id": cid,
                        "content": msg,
                    })
                    _print(f"  [community] {persona.username} → started conversation with {other.username}")

        # Register for an event
        resp = client.get("/api/community/events/")
        events = (resp or {}).get("data", {}).get("events", [])
        if events:
            ev = random.choice(events)
            result = client.post(f"/api/community/events/{ev['id']}/register/", {}, raw=True)
            already = "already registered" in (result or {}).get("error", "").lower()
            if already:
                stats.skip()
            elif result and result.get("success") is not False:
                stats.ok()
                _print(f"  [community] {persona.username} → registered for event: {ev.get('title', ev['id'])[:45]}")
            else:
                stats.fail()

    # ── Blog creation — 1 creator per round ──────────────────────────────────
    if creators:
        creator = random.choice(creators)
        creator_client = clients[creator.username]
        if creator_client.logged_in:
            title, content = _blog_post(ollama, creator)
            result = creator_client.post("/community/blog/create/", {
                "title": title,
                "content": content,
                "status": "published",
                "allow_comments": "on",
            }, form=True)
            stats.record(result)
            if result:
                _print(f"  [community] {creator.username} → created blog: {title[:55]}")
                # Have 1-2 others comment on the most recent post
                posts_resp = creator_client.get("/api/community/blog/")
                posts = (posts_resp or {}).get("data", {}).get("posts", [])
                if posts:
                    slug = posts[0]["slug"]
                    post_title = posts[0]["title"]
                    commenters = random.sample(
                        [p for p in personas if p.username != creator.username],
                        min(2, len(personas) - 1),
                    )
                    for commenter in commenters:
                        c_client = clients[commenter.username]
                        if not c_client.logged_in:
                            continue
                        comment = _blog_comment(ollama, post_title)
                        c_result = c_client.post(
                            f"/api/community/blog/{slug}/comments/",
                            {"content": comment},
                        )
                        stats.record(c_result)
                        if c_result:
                            _print(f"  [community] {commenter.username} → commented on blog: {post_title[:45]}")

    # ── Event creation — 1 creator per round (fixed May 2026 slots) ──────────
    if creators:
        slot = _EVENT_SLOTS[rnd % len(_EVENT_SLOTS)]
        event_type = _EVENT_TYPES[rnd % len(_EVENT_TYPES)]
        creator = random.choice(creators)
        creator_client = clients[creator.username]
        if creator_client.logged_in:
            ev_title, ev_desc = _event_content(ollama, event_type)
            result = creator_client.post("/community/events/create/", {
                "title": ev_title,
                "description": ev_desc,
                "event_type": event_type,
                "format": "online",
                "start_datetime": slot[0],
                "end_datetime": slot[1],
                "capacity": str(random.randint(20, 100)),
                "status": "published",
            }, form=True)
            stats.record(result)
            if result:
                _print(f"  [community] {creator.username} → created event: {ev_title[:55]}")


def simulate_shopping(personas: list, clients: dict, ollama: OllamaClient, args, stats: Stats, rnd: int):
    sample = random.sample(personas, min(len(personas), 5))
    for persona in sample:
        client = clients[persona.username]
        if not client.logged_in:
            continue

        # Browse products
        resp = client.get("/api/shop/products/")
        products = (resp or {}).get("data", {}).get("products", [])
        if not products:
            stats.fail()
            continue

        # Add one to wishlist
        pick = random.choice(products)
        result = client.post(f"/api/shop/wishlist/add/{pick['id']}/", {})
        stats.record(result)
        if result:
            _print(f"  [shopping] {persona.username} → wishlisted: {pick.get('name', pick['id'])[:50]}")

        # Add a different one to cart
        pool = [p for p in products if p["id"] != pick["id"]] or products
        cart_pick = random.choice(pool)
        result = client.post("/api/shop/cart/add/", {"css_id": cart_pick["id"], "quantity": 1})
        stats.record(result)
        if result:
            _print(f"  [shopping] {persona.username} → carted: {cart_pick.get('name', cart_pick['id'])[:50]}")

        # Review a completed-order product
        orders_resp = client.get("/api/shop/orders/")
        orders = (orders_resp or {}).get("data", {}).get("orders", [])
        completed = [o for o in orders if o.get("status") == "completed"]
        for order in completed[:1]:
            detail = client.get(f"/api/shop/orders/{order['id']}/")
            items = (detail or {}).get("data", {}).get("items", [])
            for item in items[:1]:
                css_id = item.get("css_id") or item.get("css_file")
                css_name = item.get("css_name", "CSS Loader")
                if not css_id:
                    continue
                # Skip if already reviewed
                existing = client.get(f"/api/shop/reviews/{css_id}/")
                already = any(
                    r.get("user") == persona.username
                    for r in (existing or {}).get("data", {}).get("reviews", [])
                )
                if already:
                    stats.skip()
                    continue
                rating = random.randint(3, 5)
                rev_title, rev_body = _review(ollama, css_name, rating)
                # Try the API endpoint first; fall back to web form
                result = client.post(f"/api/shop/reviews/{css_id}/", {
                    "rating": rating,
                    "title": rev_title,
                    "content": rev_body,
                })
                if result is None:
                    result = client.post(
                        f"/shop/product/{css_id}/review/add/",
                        {"rating": rating, "title": rev_title, "content": rev_body},
                        form=True,
                    )
                stats.record(result)
                if result:
                    _print(f"  [shopping] {persona.username} → reviewed '{css_name[:40]}' ({rating}★)")


def simulate_marketplace(personas: list, clients: dict, ollama: OllamaClient, args, stats: Stats, rnd: int):
    sample = random.sample(personas, min(len(personas), 5))
    for persona in sample:
        client = clients[persona.username]
        if not client.logged_in:
            continue

        # Browse all public CSS
        resp = client.get("/api/css/")
        css_files = (resp or {}).get("data", {}).get("css_files", [])
        if not css_files:
            stats.fail()
            continue

        # Get currently accessible files to avoid re-purchase
        accessible = client.get("/api/css/accessible/")
        owned_ids = {
            c["id"]
            for c in (accessible or {}).get("data", {}).get("css_files", [])
        }

        purchasable = [c for c in css_files if c["id"] not in owned_ids and float(c.get("price", 0)) > 0]
        if purchasable:
            target = random.choice(purchasable)
            result = client.post(f"/api/css/{target['id']}/purchase/", {
                "pin": client.persona.bank_pin,
            })
            stats.record(result)
            if result and result.get("success"):
                name = target.get("name", target["id"])
                _print(f"  [marketplace] {persona.username} → purchased: {name[:50]}")
                # Leave a review for the purchase
                rating = random.randint(3, 5)
                rev_title, rev_body = _review(ollama, name, rating)
                client.post(f"/api/shop/reviews/{target['id']}/", {
                    "rating": rating,
                    "title": rev_title,
                    "content": rev_body,
                })
            else:
                _print(f"  [marketplace] {persona.username} → purchase attempt failed (balance or already owned?)")
        else:
            stats.skip()
            _print(f"  [marketplace] {persona.username} → nothing to purchase (all owned or free)")

        # Developers download one of their own published files
        if persona.persona_type == "developer":
            my_resp = client.get("/api/css/my/")
            my_files = (my_resp or {}).get("data", {}).get("css_files", [])
            if my_files:
                f = random.choice(my_files)
                dl = client.post(f"/api/css/{f['id']}/download/", {})
                if dl:
                    _print(f"  [marketplace] {persona.username} (dev) → downloaded own: {f.get('name', f['id'])[:50]}")


# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------

_MODULE_FNS = {
    "forum": simulate_forum,
    "community": simulate_community,
    "shopping": simulate_shopping,
    "marketplace": simulate_marketplace,
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    here = Path(__file__).parent
    p = argparse.ArgumentParser(
        description="Simulate user interactions on the V.R.C platform via its REST API.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--url",
        default=os.environ.get("VRC_URL", "http://localhost:8000"),
        metavar="URL",
        help="Base URL of the running Django application (env: VRC_URL)",
    )
    p.add_argument(
        "--ollama-url",
        default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        metavar="URL",
        help="Ollama server base URL (env: OLLAMA_URL)",
    )
    p.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "gemma3:1b"),
        metavar="MODEL",
        help="Ollama model for content generation (env: OLLAMA_MODEL)",
    )
    p.add_argument(
        "--csv",
        default=here / "users.csv",
        type=Path,
        metavar="FILE",
        help="Path to the users CSV file",
    )
    p.add_argument(
        "--modules",
        nargs="+",
        choices=["forum", "community", "shopping", "marketplace", "all"],
        default=["all"],
        metavar="MODULE",
        help="Modules to simulate: forum community shopping marketplace all",
    )
    p.add_argument("--rounds", type=int, default=3, metavar="N",
                   help="Interaction rounds per module")
    p.add_argument("--delay", type=float, default=1.0, metavar="SECS",
                   help="Seconds to wait between mutating API calls")
    p.add_argument("--users", default=None, metavar="U1,U2",
                   help="Comma-separated usernames to restrict to (default: all from CSV)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print actions without making POST requests")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Log full request/response details")
    return p.parse_args()


def main():
    args = parse_args()

    modules = set(args.modules)
    if "all" in modules:
        modules = {"forum", "community", "shopping", "marketplace"}

    print("=" * 70)
    print("  V.R.C — Interaction Simulator")
    print("=" * 70)
    print(f"  App URL    : {args.url}")
    print(f"  Ollama URL : {args.ollama_url}")
    print(f"  Model      : {args.model}")
    print(f"  Modules    : {', '.join(sorted(modules))}")
    print(f"  Rounds     : {args.rounds}")
    print(f"  Delay      : {args.delay}s")
    print(f"  Dry run    : {args.dry_run}")
    print("=" * 70)

    # Load personas
    filter_users = [u.strip() for u in args.users.split(",")] if args.users else None
    personas = load_personas(args.csv, filter_users)
    if not personas:
        print("[!] No personas loaded — check --csv path and --users filter.")
        sys.exit(1)
    print(f"\nLoaded {len(personas)} persona(s) from {args.csv.name}")

    # Ollama check
    ollama = OllamaClient(args.ollama_url, args.model)
    if ollama.check():
        print(f"Ollama ready — model '{args.model}'")
    else:
        print(f"[!] Ollama unavailable at {args.ollama_url} — using canned fallback content")

    # Log in all personas
    print("\nLogging in…")
    clients = {}
    for persona in personas:
        client = APIClient(persona, args.url, args.delay, args.dry_run, args.verbose)
        client.login()
        clients[persona.username] = client

    active = [p for p in personas if clients[p.username].logged_in]
    if not active:
        print("[!] No personas logged in — check --url and user credentials.")
        sys.exit(1)
    print(f"{len(active)}/{len(personas)} persona(s) active")

    # Prepare per-module stats and sorted module list
    active_modules = sorted(modules)
    all_stats = {mod: Stats() for mod in active_modules}
    total_work = args.rounds * len(active_modules)

    pbar = (
        _tqdm(total=total_work, unit="module-round", ncols=72, desc="Starting")
        if HAS_TQDM else None
    )

    # Run all modules in parallel, one shared round loop
    for rnd in range(args.rounds):
        _print(f"\n{'═' * 70}")
        _print(f"  Round {rnd + 1}/{args.rounds}  [{', '.join(active_modules)}]")
        _print(f"{'═' * 70}")

        if pbar:
            pbar.set_description(f"Round {rnd + 1}/{args.rounds}")

        with ThreadPoolExecutor(max_workers=len(active_modules)) as executor:
            futures = {
                executor.submit(
                    _MODULE_FNS[mod], active, clients, ollama, args, all_stats[mod], rnd
                ): mod
                for mod in active_modules
            }
            for future in as_completed(futures):
                mod = futures[future]
                try:
                    future.result()
                except Exception as e:
                    _print(f"[!] {mod} round {rnd + 1} crashed: {e}\n{traceback.format_exc()}")
                if pbar:
                    pbar.update(1)

    if pbar:
        pbar.close()

    # Print summary
    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)
    print(f"  {'Module':<15}  {'Done':>6}  {'Skipped':>7}  {'Failed':>6}")
    print(f"  {'─' * 42}")
    for mod, s in all_stats.items():
        print(f"  {mod:<15}  {s.done:>6}  {s.skipped:>7}  {s.failed:>6}")
    print("=" * 70)


if __name__ == "__main__":
    main()
