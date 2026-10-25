# WOCShAck#5 — Write-Ups

Curated write-ups for the WOCShAck#5 (V.R.C Platform) bug-bounty engagement. Each folder holds one finding, written from the **best accepted (resolved) hunter report** for that vulnerability, with the reporting team credited as the author. Findings cover the intended WOCShAck-5-dev vulnerability catalog plus additional accepted findings that fall outside it.

Each write-up follows the same structure: **Description → Exploitation → PoC → Risk → Remediation → Author**.

## Web / Injection
| Finding | Severity | Team |
|---------|----------|------|
| [Reflected XSS (shop search)](Reflected_XSS/Reflected_XSS.md) | Medium | Hackrapovic |
| [Stored XSS (biography)](Stored_XSS_Biography/Stored_XSS_Biography.md) | Medium-High | DaVinciCode |
| [Unrestricted File Upload → XSS](File_Upload_XSS/File_Upload_XSS.md) | High | CUSTODES SQUAD |
| [Path Traversal / LFI (`/api/loader/`)](Path_Traversal/Path_Traversal.md) | High | Hackrapovic |
| [SQL Injection (banking `su`)](SQLi_Banking/SQLi_Banking.md) | High | TéléHack |
| [CSV / Formula Injection](CSV_Injection/CSV_Injection.md) | Medium | TastyCrousteam |
| [CRLF / Email Header Injection](CRLF_Email_Injection/CRLF_Email_Injection.md) | High | CHILL HUNT |
| [Host Header Injection / Open Redirect](Host_Header_Injection/Host_Header_Injection.md) | High | CHILL HUNT |
| [Prompt Injection (chatbot)](Prompt_Injection/Prompt_Injection.md) | Medium | DaVinciCode |

## Access Control / Auth
| Finding | Severity | Team |
|---------|----------|------|
| [Unauthenticated Webmail API (users + emails)](Unauth_Webmail_API/Unauth_Webmail_API.md) | Critical | Hackrapovic |
| [Webmail Arbitrary Deletion (DELETE)](Webmail_Arbitrary_Deletion/Webmail_Arbitrary_Deletion.md) | High | Hackrapovic |
| [IDOR — Webmail `/api/emails`](IDOR_Webmail_Emails/IDOR_Webmail_Emails.md) | Critical | CPE LYON |
| [IDOR — Chatbot Flag](IDOR_Chatbot_Flag/IDOR_Chatbot_Flag.md) | Medium | CPE LYON |
| [TOTP Secret Leak → MFA Bypass](TOTP_Secret_Leak/TOTP_Secret_Leak.md) | High | CUSTODES SQUAD |
| [PIN-Skip Bypass](PIN_Skip_Bypass/PIN_Skip_Bypass.md) | High | CPE LYON |
| [2FA Bypass (incomplete enforcement)](2FA_Bypass/2FA_Bypass.md) | High | Hackrapovic |
| [Mass Assignment (profile)](Mass_Assignment/Mass_Assignment.md) | High | CPE LYON |
| [Coupon Abuse (free purchases)](Coupon_Abuse/Coupon_Abuse.md) | High | CPE LYON |
| [CSS Paywall Bypass](CSS_Paywall_Bypass/CSS_Paywall_Bypass.md) | High | CPE LYON |
| [No Rate Limit on Login](No_Rate_Limit_Login/No_Rate_Limit_Login.md) | Medium | 0xE51EE |

## CSRF
| Finding | Severity | Team |
|---------|----------|------|
| [CSRF — Cart (GET-triggerable)](CSRF_Cart/CSRF_Cart.md) | Medium | Hackrapovic |
| [CSRF — Bank Transfer](CSRF_Bank_Transfer/CSRF_Bank_Transfer.md) | High | TéléHack |
| [CSRF — Webmail Signup](CSRF_Webmail_Signup/CSRF_Webmail_Signup.md) | Medium-High | Hackrapovic |

## Crypto / Secrets / Tokens
| Finding | Severity | Team |
|---------|----------|------|
| [Predictable Activation Token (MD5)](Predictable_Activation_Token/Predictable_Activation_Token.md) | High | Hackrapovic |
| [Predictable Webmail Session Token (SHA256)](Predictable_Webmail_Token/Predictable_Webmail_Token.md) | Critical | TéléHack |
| [Unsalted SHA-256 Password Hashing](Unsalted_Password_Hash/Unsalted_Password_Hash.md) | High | CHILL HUNT |
| [Card Number in Plaintext Cookie](Card_In_Cookie/Card_In_Cookie.md) | Medium-High | CESI-ROUEN |

## Business Logic / Banking
| Finding | Severity | Team |
|---------|----------|------|
| [Race Condition / Double Spend](Race_Condition/Race_Condition.md) | High | Hackrapovic |
| [Price Tampering (client total)](Price_Tampering/Price_Tampering.md) | High | CHILL HUNT |
| [Negative Transfer](Negative_Transfer/Negative_Transfer.md) | High | Scoubi'Hack |
| [SSRF — Developer Webhook](SSRF_Webhook/SSRF_Webhook.md) | High | Hackrapovic |
| [Email Sender Spoofing → XSS](Email_Sender_Spoofing/Email_Sender_Spoofing.md) | High | TéléHack |

## Information Disclosure / Misconfiguration
| Finding | Severity | Team |
|---------|----------|------|
| [Username / Email Enumeration](Username_Enumeration/Username_Enumeration.md) | Medium | Hackrapovic |
| [Path Disclosure via robots.txt](Robots_Path_Disclosure/Robots_Path_Disclosure.md) | Medium | DaVinciCode |
| [Iframe Sandbox Bypass (chatbot)](Iframe_Sandbox_Bypass/Iframe_Sandbox_Bypass.md) | Medium-High | CHILL HUNT |
| [API Docs Exposure (`openapi.json`)](API_Docs_Exposure/API_Docs_Exposure.md) | Medium | Brain Scratch |
