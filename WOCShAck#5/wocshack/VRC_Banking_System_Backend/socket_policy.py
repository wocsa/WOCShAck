ALLOWED_CLIENT_IP = "172.28.0.3"


def is_allowed_client_ip(client_ip):
    return client_ip == ALLOWED_CLIENT_IP
