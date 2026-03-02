# Description

A Stored Cross-Site Scripting (XSS) vulnerability exists in the user profile page. The biography field accepts HTML code such as `<script>` tags without sanitization. When this content is saved and later displayed to other users, the malicious script executes in their browsers.

# Exploitation

1. Navigate to the Profile page (`/index.php?page=user/profile.php`).
2. In the Biography field, inject:
```html
<script>alert('XSS')</script>
```
3. Save the profile.
4. The script is stored without any protection and will execute when any user views the profile.

# PoC

Payload used:

```html
<script>alert('XSS')</script>
```

Result: the code is saved and executed without being blocked or escaped when the profile page is rendered.

# Risk

This Stored XSS vulnerability (CVSS 7.3) allows an attacker to execute JavaScript in the browser of other users who visit the compromised profile. This can be used to steal session cookies, perform actions on behalf of victims, or redirect users to malicious sites. Since it is stored, it persists and affects every visitor.

# Remediation

Block or escape HTML code (`<`, `>`, `"`, `'`) using `htmlspecialchars()` in PHP before rendering user-supplied content. Validate all fields server-side to prevent script injection.

```php
<?php echo htmlspecialchars($user['bio'], ENT_QUOTES, 'UTF-8'); ?>
```

# Author
Amnesia
