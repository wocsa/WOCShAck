import socket
import threading
from datetime import datetime
from Utils.parser import parse
from Activity.Logger import write_activity, write_security
import json
from socket_policy import is_allowed_client_ip

HOST = "172.28.0.2"
PORT = 7051


def log_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def handle_client(conn, addr):
    client_ip = addr[0]
    write_activity(f"{log_time()} - Connection accepted from {addr}\n")
    try:
        with conn:
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                response = parse(data.decode())
                conn.sendall(json.dumps(response).encode())
    except Exception as e:
        write_activity(f"{log_time()} - Error with {client_ip}: {str(e)}\n")
    finally:
        write_activity(f"{log_time()} - Connection with {client_ip} closed.\n")


def serve_forever():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()

        write_activity(f"{log_time()} - Server listening on {HOST}:{PORT}\n")

        while True:
            try:
                conn, addr = s.accept()
                client_ip, client_port = addr

                if not is_allowed_client_ip(client_ip):
                    write_security(
                        f"{log_time()} - Rejected connection from {client_ip}:{client_port}\n"
                    )
                    conn.close()
                    continue

                t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                t.start()

            except Exception as e:
                write_activity(f"{log_time()} - Error: {str(e)}\n")


if __name__ == "__main__":
    serve_forever()
