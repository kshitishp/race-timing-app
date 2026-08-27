import io

import qrcode


def generate_qr_png_bytes(payload: str) -> bytes:
    """Encode `payload` (the Profile's qr_code_uuid, per §8) as a PNG QR
    code and return the raw bytes."""
    img = qrcode.make(payload)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
