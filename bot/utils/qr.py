from io import BytesIO

import qrcode


def generate_qr_image(data: str) -> BytesIO:
    qr = qrcode.QRCode(
        version=None,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer