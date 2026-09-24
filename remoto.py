"""
remoto.py - utilidades compartidas para el modo remoto (a traves del rele).

Contiene:
  - Framing de mensajes: cada mensaje va precedido de su longitud (4 bytes),
    para poder enviar ordenes, respuestas y fotogramas por el mismo socket sin
    que se mezclen.
  - Captura de pantalla en JPEG (para el visor en vivo). Usa Pillow y solo
    funciona con un escritorio real (sesion de usuario).
"""

import io
import json
import base64
import struct

PUERTO_RELE_POR_DEFECTO = 50510


# ---------------------------------------------------------------------------
# Framing: enviar / recibir mensajes con prefijo de longitud
# ---------------------------------------------------------------------------
def enviar_mensaje(sock, obj):
    """Serializa 'obj' a JSON y lo envia con un prefijo de longitud (4 bytes)."""
    datos = json.dumps(obj).encode("utf-8")
    sock.sendall(struct.pack(">I", len(datos)) + datos)


def _recibir_exacto(sock, n):
    """Lee EXACTAMENTE n bytes del socket. Devuelve None si se cierra antes."""
    trozos = bytearray()
    while len(trozos) < n:
        parte = sock.recv(n - len(trozos))
        if not parte:
            return None
        trozos.extend(parte)
    return bytes(trozos)


def recibir_mensaje(sock):
    """Lee un mensaje completo. Devuelve el dict, o None si el socket se cierra."""
    cabecera = _recibir_exacto(sock, 4)
    if cabecera is None:
        return None
    (longitud,) = struct.unpack(">I", cabecera)
    cuerpo = _recibir_exacto(sock, longitud)
    if cuerpo is None:
        return None
    return json.loads(cuerpo.decode("utf-8"))


# ---------------------------------------------------------------------------
# Captura de pantalla (visor en vivo)
# ---------------------------------------------------------------------------
def capturar_frame(ancho=480, calidad=40):
    """Captura la pantalla y devuelve un mensaje 'frame' con el JPEG en base64.

    Reduce el ancho a 'ancho' px (miniatura) para que fluya. Requiere Pillow
    (pip install pillow) y un escritorio real.
    """
    from PIL import ImageGrab  # import perezoso: solo se necesita en el agente

    img = ImageGrab.grab()
    ancho0, alto0 = img.size
    if ancho and ancho0 > ancho:
        alto = max(1, int(alto0 * ancho / ancho0))
        img = img.resize((ancho, alto))
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=calidad)
    jpeg = buffer.getvalue()
    return {
        "tipo": "frame",
        "jpeg": base64.b64encode(jpeg).decode("ascii"),
        "w": img.size[0],
        "h": img.size[1],
    }


def decodificar_frame(mensaje):
    """Devuelve los bytes JPEG contenidos en un mensaje 'frame'."""
    return base64.b64decode(mensaje["jpeg"])
