import json
import re
import socket
import time
from .generate import generate_sid

class Client:
    def __init__(self, auto_connect=False, timeout=10):
        self.HOST = "172.28.0.2"
        self.PORT = 7051
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(timeout)
        if auto_connect:
            self.connect()

    def connect(self):
        try:
            self.s.connect((self.HOST, self.PORT))
        except ConnectionRefusedError as e:
            print("Connection error:", e)

    def send(self, payload: dict):
        data = json.dumps(payload)
        self.s.sendall(data.encode())

    def receive(self, buffer_size=1024, max_chunks=100):
        buffer = ""
        chunks_received = 0
        while chunks_received < max_chunks:
            try:
                chunk = self.s.recv(buffer_size).decode()
            except socket.timeout:
                return None
            if not chunk:  # Connection closed
                return None
            buffer += chunk
            chunks_received += 1
            try:
                fixed = re.sub(r"(?<!\\)'", '"', buffer)
                return json.loads(fixed)
            except json.JSONDecodeError:
                # Keep receiving more data
                continue
        # Max chunks reached without valid JSON - prevent infinite loop
        return None

    def close(self):
        self.s.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _send_with_retry(self, payload: dict, retries=5, delay=1):
        for attempt in range(retries):
            self.send(payload)
            response = self.receive()
            if response != {"error": "Rate limit exceeded"}:
                return response
            # Only retry on rate-limit errors; never resend mutating commands
            # that already succeeded (e.g. addcard creating duplicate cards).
            if attempt < retries - 1:
                time.sleep(delay)
        return {"error": "Rate limit still exceeded after retries"}

    # === COMMAND METHODS ===

    def ping(self):
        return self._send_with_retry({"command": "ping"})

    def check(self, sid):
        return self._send_with_retry({"command": "check", "sid":sid})

    def create_session(self, sid):
        return self._send_with_retry({"command": "sescr", "sid": sid})

    def close_session(self, sid):
        return self._send_with_retry({"command": "sescl", "sid": sid})

    def get_users(self, sid):
        return self._send_with_retry({"command": "getau", "sid": sid})

    def get_user(self, sid, user_id):
        return self._send_with_retry({"command": "getu", "sid": sid, "user_id": user_id})

    def get_user_by_payment_number(self, sid, payment_number):
        return self._send_with_retry({"command": "getubypn", "sid": sid, "payment_number": payment_number})

    def verify(self, sid, user_id, pin):
        return self._send_with_retry({"command": "ver", "sid": sid, "user_id": user_id, "pin": pin})

    def increment_attempts(self, sid, user_id):
        return self._send_with_retry({"command": "inca", "sid": sid, "user_id": user_id})

    def reset_attempts(self, sid, user_id):
        return self._send_with_retry({"command": "resa", "sid": sid, "user_id": user_id})

    def get_attempts(self, sid, user_id):
        return self._send_with_retry({"command": "getat", "sid": sid, "user_id": user_id})

    def add_user(self, sid, user_id, pin):
        return self._send_with_retry({"command": "adu", "sid": sid, "user_id": user_id, "pin": pin})

    def delete_user(self, sid, user_id):
        return self._send_with_retry({"command": "delu", "sid": sid, "user_id": user_id})

    def add_amount(self, sid, user_id, amount):
        return self._send_with_retry({"command": "ad", "sid": sid, "user_id": user_id, "amount": amount})

    def set_balance(self, sid, user_id, amount):
        return self._send_with_retry({"command": "sb", "sid": sid, "user_id": user_id, "amount": amount})

    def set_pin(self, sid, user_id, pin):
        return self._send_with_retry({"command": "sp", "sid": sid, "user_id": user_id, "pin": pin})

    def transaction(self, sid, from_user, to_user, amount):
        return self._send_with_retry({"command": "tr", "sid": sid, "from": from_user, "to": to_user, "amount": amount})

    def try_command(self, sid):
        return self._send_with_retry({"command": "try", "sid": sid})

    # === CARD METHODS ===

    def add_card(self, sid, user_id, card_type='virtual'):
        return self._send_with_retry({"command": "addcard", "sid": sid, "user_id": user_id, "card_type": card_type})

    def get_cards(self, sid, user_id):
        return self._send_with_retry({"command": "getcards", "sid": sid, "user_id": user_id})

    def get_card_by_number(self, sid, card_number):
        return self._send_with_retry({"command": "getcardbn", "sid": sid, "card_number": card_number})

    def set_card_status(self, sid, card_number, status):
        return self._send_with_retry({"command": "setcardstatus", "sid": sid, "card_number": card_number, "status": status})

    def ensure_default_card(self, sid, user_id, account_number):
        return self._send_with_retry({"command": "ensuredefaultcard", "sid": sid, "user_id": user_id, "account_number": account_number})


def make_connection():
    cli = Client(auto_connect=True)
    if cli.ping() == {'status': 'success'}:
        sid = generate_sid()
        if cli.create_session(sid) == {'status': 'success'}:
            time.sleep(1)
            return cli, sid
        time.sleep(1)
    return False, None

def make_connection_with_sid(sid):
    cli = Client(auto_connect=True)
    if cli.ping() == {'status': 'success'}:
        if cli.check(sid) == {'status': 'success'}:
            return cli, True
        return cli, False
    return None, False

def build_query(cmd, sid):
    cmd = cmd.split("+")
    if len(cmd) == 1:
        return False, None
    result = {}
    try:
        for x in range(0, len(cmd)-1, 2):
            value = cmd[x+1]
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass
            result[cmd[x]] = value
        result["sid"] = sid
        return True, result
    except IndexError:
        return False, None
