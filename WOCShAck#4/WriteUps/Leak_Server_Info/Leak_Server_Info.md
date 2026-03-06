# Description  

An Information Disclosure vulnerability via HTTP Headers has been identified.
Regardless of the endpoint accessed on the domain <IP>, the application returns sensitive information regarding its server environment within the HTTP response headers, including:

The web server in use (Server: nginx)

The PHP version (X-Powered-By: PHP/8.2.28)

This information leak is systematic and allows an attacker to identify the technologies and versions being used, thereby facilitating the discovery and exploitation of known vulnerabilities.

# Exploitation  

1. Send a standard HTTP request to any page on the domain.

1. Examine the HTTP response headers using a proxy.

1. Observe that the Server and X-Powered-By headers expose the web server and PHP version in use, respectively.

1. No authentication or special action is required to access this information.

# PoC  

Request (example):
```http
GET /index.php?page=analytics/analytics.php HTTP/2
Host: <IP>
```
But this also works on other pages.

Response (HTTP headers):
```http
HTTP/2 200 OK
Server: nginx
X-Powered-By: PHP/8.2.28
```
# Risk

Allows an attacker to precisely target vulnerabilities affecting nginx and PHP (8.2.28).

Significantly reduces the reconnaissance phase of a targeted attack.

Can be used to refine attacks based on public exploits, 0days, or targeted brute-force. 


# Remediation  

Remove or mask sensitive HTTP headers:

In nginx:
`server_tokens off;`

In PHP:
    `expose_php = Off`

Adopt a policy of minimizing exposed information in all HTTP responses.
# Author
CESI
