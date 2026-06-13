import hashlib
import time


def generate_sid():
    return hashlib.md5(str(int(time.time())).encode()).hexdigest()
