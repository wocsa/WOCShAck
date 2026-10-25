import re


# Registration is restricted to the internal mail domain (issue #184).
ALLOWED_EMAIL_DOMAIN = 'tbox.traced'
EMAIL_VALID = 'valid'
EMAIL_INVALID_FORMAT = 'invalid_format'
EMAIL_INVALID_DOMAIN = 'invalid_domain'


def get_email_validation_result(email):
    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    if not email or not re.match(email_regex, email):
        return EMAIL_INVALID_FORMAT
    if email.rsplit('@', 1)[-1].lower() != ALLOWED_EMAIL_DOMAIN:
        return EMAIL_INVALID_DOMAIN
    return EMAIL_VALID


def check_email_validity(email):
    return get_email_validation_result(email) == EMAIL_VALID


def check_password_strength(password):
    if len(password) < 8 or not any(char.isupper() for char in password) or not any(
            char.islower() for char in password) or not any(char.isdigit() for char in password) or not any(
            char in '.!@#$%^&*()_+{}|:"<>?`~' for char in password):
        return False
    return True
