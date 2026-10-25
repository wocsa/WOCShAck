import qrcode
import base64
import pyotp
from io import BytesIO


def generate_qr(email):
    key = pyotp.random_base32()

    uri = pyotp.totp.TOTP(key).provisioning_uri(name=email, issuer_name="V.R.C")
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    return uri, img_str, key


def verify_code(code, key):
    totp = pyotp.TOTP(key)
    return totp.verify(code)
