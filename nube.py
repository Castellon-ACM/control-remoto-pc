"""
nube.py - Modo NUBE: conexion entre ciudades SIN rele propio y SIN instalar nada.

Idea: en vez de montar un rele con IP publica, los dos equipos se conectan
(conexion SALIENTE, atraviesa cualquier router) a un broker MQTT PUBLICO y
gratuito (por defecto broker.emqx.io). El broker hace de "centralita": el
agente escucha en un canal y la consola en otro.

Todo con la libreria estandar de Python (socket, ssl, hashlib, hmac, zlib,
ctypes): no hace falta pip install, ni VPN, ni abrir puertos.

Seguridad (el broker es publico, cualquiera puede conectarse a el):
  - El nombre del canal se DERIVA de la sala + la clave (PBKDF2). Sin la
    clave no se sabe ni en que canal escuchar.
  - Cada mensaje va CIFRADO (SHAKE-256 como flujo de clave) y FIRMADO
    (HMAC-SHA256). El broker solo ve bytes aleatorios.
  - La firma incluye la direccion (consola->agente o agente->consola) y cada
    mensaje lleva hora y un numero aleatorio: se rechazan mensajes viejos
    (> 5 min) y repetidos (anti-replay).
  - La clave NUNCA viaja por la red.
  - La conexion con el broker va ademas por TLS (puerto 8883).
"""

import os
import io
import ssl
import sys
import hmac
import json
import time
import zlib
import base64
import socket
import struct
import hashlib
import threading

BROKER_POR_DEFECTO = "broker.emqx.io"
PUERTO_POR_DEFECTO = 8883          # MQTT sobre TLS
CLAVE_POR_DEFECTO = "cambia-esta-clave-2026"
LONGITUD_MINIMA_CLAVE = 8
VENTANA_SEGUNDOS = 300             # antiguedad maxima aceptada de un mensaje
MAX_BYTES_FRAME = 350_000          # por encima se reduce el tamano del visor

HACIA_AGENTE = b"a"
HACIA_CONSOLA = b"c"


# ===========================================================================
# 1) Cifrado y firma extremo a extremo
# ===========================================================================
def validar_clave(clave):
    """Devuelve un texto de error si la clave no es aceptable, o None si vale."""
    if not clave or clave == CLAVE_POR_DEFECTO:
        return ("Cambia la clave por defecto: en modo nube el broker es publico y "
                "la clave es lo unico que protege el equipo.")
    if len(clave) < LONGITUD_MINIMA_CLAVE:
        return f"La clave debe tener al menos {LONGITUD_MINIMA_CLAVE} caracteres."
    return None


def _xor(a, b):
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big")


class Canal:
    """Deriva las claves y los topics a partir de sala + clave, y cifra/descifra."""

    VERSION = b"\x01"

    def __init__(self, sala, clave, iteraciones=100_000):
        sal = ("control-remoto-pc/nube/" + sala).encode("utf-8")
        k = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, iteraciones, 64)
        self._k_cifrado, self._k_firma = k[:32], k[32:]
        ident = hmac.new(self._k_firma, b"topic", hashlib.sha256).hexdigest()[:24]
        self.topic_agente = f"crp/{ident}/a"    # lo escucha el agente
        self.topic_consola = f"crp/{ident}/c"   # lo escucha la consola
        self._vistos = {}
        self._lock = threading.Lock()

    def cerrar_sobre(self, direccion, obj):
        """obj (dict) -> bytes cifrados y firmados."""
        obj = dict(obj)
        obj["ts"] = time.time()
        claro = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        nonce = os.urandom(16)
        flujo = hashlib.shake_256(self._k_cifrado + direccion + nonce).digest(len(claro))
        cifrado = _xor(claro, flujo) if claro else b""
        firma = hmac.new(self._k_firma, self.VERSION + direccion + nonce + cifrado,
                         hashlib.sha256).digest()
        return self.VERSION + nonce + cifrado + firma

    def abrir_sobre(self, direccion, datos):
        """bytes -> dict, o None si la firma no cuadra, es viejo o repetido."""
        if len(datos) < 1 + 16 + 32 or datos[:1] != self.VERSION:
            return None
        nonce, cifrado, firma = datos[1:17], datos[17:-32], datos[-32:]
        esperada = hmac.new(self._k_firma, self.VERSION + direccion + nonce + cifrado,
                            hashlib.sha256).digest()
        if not hmac.compare_digest(firma, esperada):
            return None
        flujo = hashlib.shake_256(self._k_cifrado + direccion + nonce).digest(len(cifrado))
        try:
            obj = json.loads(_xor(cifrado, flujo).decode("utf-8"))
        except ValueError:
            return None
        ahora = time.time()
        if not isinstance(obj, dict) or abs(ahora - float(obj.get("ts", 0))) > VENTANA_SEGUNDOS:
            return None
        with self._lock:
            if nonce in self._vistos:
                return None  # repetido (replay)
            self._vistos[nonce] = ahora
            if len(self._vistos) > 5000:
                limite = ahora - VENTANA_SEGUNDOS
                self._vistos = {n: t for n, t in self._vistos.items() if t > limite}
        obj.pop("ts", None)
        return obj


# ===========================================================================
# 2) Cliente MQTT 3.1.1 minimo (solo libreria estandar)
# ===========================================================================
def _cadena(texto):
    b = texto.encode("utf-8")
    return struct.pack(">H", len(b)) + b


def _longitud_restante(n):
    salida = bytearray()
    while True:
        byte = n % 128
        n //= 128
        if n:
            byte |= 0x80
        salida.append(byte)
        if not n:
            return bytes(salida)


def _paquete(cabecera, cuerpo=b""):
    return bytes([cabecera]) + _longitud_restante(len(cuerpo)) + cuerpo


class ClienteMQTT:
    """Cliente MQTT sencillo: conectar, suscribirse y publicar con QoS 0."""

    KEEPALIVE = 30

    def __init__(self, host, puerto, tls=True, on_mensaje=None, on_caida=None):
        self.host = host
        self.puerto = int(puerto)
        self.tls = tls
        self.on_mensaje = on_mensaje    # f(topic, payload_bytes)
        self.on_caida = on_caida        # f() cuando se pierde la conexion
        self._sock = None
        self._lock_envio = threading.Lock()
        self._vivo = threading.Event()
        self._ultimo_rx = 0.0
        self._id_paquete = 0

    # -- conexion -----------------------------------------------------------
    def conectar(self, timeout=15):
        s = socket.create_connection((self.host, self.puerto), timeout=timeout)
        if self.tls:
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
        self._sock = s
        id_cliente = "crp-" + os.urandom(6).hex()
        cuerpo = (_cadena("MQTT") + bytes([4, 0x02]) + struct.pack(">H", self.KEEPALIVE)
                  + _cadena(id_cliente))
        self._enviar(_paquete(0x10, cuerpo))
        tipo, datos = self._leer_paquete()
        if tipo != 0x20 or len(datos) < 2 or datos[1] != 0:
            s.close()
            raise ConnectionError(f"El broker rechazo la conexion (codigo {datos[1:2].hex()})")
        s.settimeout(None)
        self._ultimo_rx = time.time()
        self._vivo.set()
        threading.Thread(target=self._bucle_lectura, daemon=True).start()
        threading.Thread(target=self._bucle_ping, daemon=True).start()

    def suscribir(self, topic):
        self._id_paquete = (self._id_paquete % 65535) + 1
        cuerpo = struct.pack(">H", self._id_paquete) + _cadena(topic) + b"\x00"
        self._enviar(_paquete(0x82, cuerpo))

    def publicar(self, topic, payload):
        self._enviar(_paquete(0x30, _cadena(topic) + payload))

    def cerrar(self):
        estaba_vivo = self._vivo.is_set()
        self._vivo.clear()
        try:
            if estaba_vivo:
                self._enviar(b"\xe0\x00")
        except OSError:
            pass
        try:
            self._sock.close()
        except (OSError, AttributeError):
            pass

    @property
    def conectado(self):
        return self._vivo.is_set()

    # -- internos -----------------------------------------------------------
    def _enviar(self, datos):
        with self._lock_envio:
            self._sock.sendall(datos)

    def _leer_exacto(self, n):
        trozos = bytearray()
        while len(trozos) < n:
            parte = self._sock.recv(n - len(trozos))
            if not parte:
                raise ConnectionError("conexion cerrada por el broker")
            trozos.extend(parte)
        return bytes(trozos)

    def _leer_paquete(self):
        cabecera = self._leer_exacto(1)[0]
        multiplicador, longitud = 1, 0
        while True:
            b = self._leer_exacto(1)[0]
            longitud += (b & 0x7F) * multiplicador
            if not b & 0x80:
                break
            multiplicador *= 128
        return cabecera, self._leer_exacto(longitud) if longitud else b""

    def _bucle_lectura(self):
        try:
            while self._vivo.is_set():
                cabecera, datos = self._leer_paquete()
                self._ultimo_rx = time.time()
                if cabecera & 0xF0 == 0x30:          # PUBLISH
                    qos = (cabecera >> 1) & 0x03
                    (lt,) = struct.unpack(">H", datos[:2])
                    topic = datos[2:2 + lt].decode("utf-8", "replace")
                    inicio = 2 + lt + (2 if qos else 0)
                    if self.on_mensaje:
                        try:
                            self.on_mensaje(topic, datos[inicio:])
                        except Exception:
                            pass  # un mensaje raro no debe tumbar la conexion
                # SUBACK (0x90), PINGRESP (0xD0)... no requieren accion
        except (OSError, ConnectionError, IndexError, struct.error):
            pass
        if self._vivo.is_set():
            self._vivo.clear()
            try:
                self._sock.close()
            except OSError:
                pass
            if self.on_caida:
                self.on_caida()

    def _bucle_ping(self):
        ultimo_ping = time.time()
        while self._vivo.is_set():
            time.sleep(1)
            if not self._vivo.is_set():
                break
            inactivo = time.time() - self._ultimo_rx
            if inactivo > self.KEEPALIVE * 2:
                try:
                    self._sock.close()   # conexion muerta: el lector lo detecta
                except OSError:
                    pass
                break
            if time.time() - ultimo_ping >= self.KEEPALIVE / 2:
                ultimo_ping = time.time()
                try:
                    self._enviar(b"\xc0\x00")  # PINGREQ
                except OSError:
                    pass


# ===========================================================================
# 3) Captura de pantalla SIN Pillow (Windows, ctypes) -> PNG
# ===========================================================================
def _png_paleta_332(ancho, alto, indices):
    """Codifica un PNG de 8 bits con paleta fija 3-3-2 (256 colores)."""
    def trozo(tipo, datos):
        return (struct.pack(">I", len(datos)) + tipo + datos
                + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))

    paleta = bytearray()
    for i in range(256):
        paleta += bytes(((i >> 5) * 255 // 7, ((i >> 2) & 7) * 255 // 7, (i & 3) * 255 // 3))
    filas = b"".join(b"\x00" + indices[y * ancho:(y + 1) * ancho] for y in range(alto))
    return (b"\x89PNG\r\n\x1a\n"
            + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 3, 0, 0, 0))
            + trozo(b"PLTE", bytes(paleta))
            + trozo(b"IDAT", zlib.compress(filas, 6))
            + trozo(b"IEND", b""))


_T_R = bytes(v & 0xE0 for v in range(256))
_T_G = bytes((v >> 3) & 0x1C for v in range(256))
_T_B = bytes(v >> 6 for v in range(256))


def bgra_a_png(ancho, alto, bgra):
    """Pixeles BGRA (4 bytes por pixel, de arriba abajo) -> bytes PNG."""
    r = int.from_bytes(bgra[2::4].translate(_T_R), "big")
    g = int.from_bytes(bgra[1::4].translate(_T_G), "big")
    b = int.from_bytes(bgra[0::4].translate(_T_B), "big")
    indices = (r | g | b).to_bytes(ancho * alto, "big")
    return _png_paleta_332(ancho, alto, indices)


def _capturar_bgra_windows(ancho_max):
    import ctypes
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    HANDLE = ctypes.c_void_p
    user32.GetDC.restype = HANDLE
    user32.GetDC.argtypes = [HANDLE]
    user32.ReleaseDC.argtypes = [HANDLE, HANDLE]
    gdi32.CreateCompatibleDC.restype = HANDLE
    gdi32.CreateCompatibleDC.argtypes = [HANDLE]
    gdi32.CreateCompatibleBitmap.restype = HANDLE
    gdi32.CreateCompatibleBitmap.argtypes = [HANDLE, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = HANDLE
    gdi32.SelectObject.argtypes = [HANDLE, HANDLE]
    gdi32.SetStretchBltMode.argtypes = [HANDLE, ctypes.c_int]
    gdi32.SetBrushOrgEx.argtypes = [HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi32.StretchBlt.argtypes = [HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wintypes.DWORD]
    gdi32.GetDIBits.argtypes = [HANDLE, HANDLE, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [HANDLE]
    gdi32.DeleteDC.argtypes = [HANDLE]

    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    w = max(1, min(int(ancho_max), sw))
    h = max(1, sh * w // sw)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    hdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    viejo = gdi32.SelectObject(mdc, bmp)
    try:
        gdi32.SetStretchBltMode(mdc, 4)          # HALFTONE: reduce con buena calidad
        gdi32.SetBrushOrgEx(mdc, 0, 0, None)
        gdi32.StretchBlt(mdc, 0, 0, w, h, hdc, 0, 0, sw, sh, 0x00CC0020)  # SRCCOPY
        bi = BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h               # negativo = de arriba abajo
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0):
            raise OSError("GetDIBits fallo (no hay escritorio accesible?)")
        return w, h, buf.raw
    finally:
        gdi32.SelectObject(mdc, viejo)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(None, hdc)


def capturar_frame(ancho=480, formatos=("png",), calidad=40):
    """Devuelve {"tipo":"frame","fmt":..,"img":base64,"w","h"}.

    Usa JPEG con Pillow si esta instalado y la consola lo acepta (mas ligero);
    si no, PNG hecho a mano con ctypes (Windows) sin ninguna dependencia.
    """
    try:
        from PIL import ImageGrab
    except ImportError:
        ImageGrab = None

    if ImageGrab is not None:
        img = ImageGrab.grab()
        w0, h0 = img.size
        if ancho and w0 > ancho:
            img = img.resize((ancho, max(1, int(h0 * ancho / w0))))
        buf = io.BytesIO()
        if "jpeg" in formatos:
            img.convert("RGB").save(buf, format="JPEG", quality=calidad)
            fmt = "jpeg"
        else:
            img.convert("RGB").quantize(256).save(buf, format="PNG", optimize=False)
            fmt = "png"
        datos, (w, h) = buf.getvalue(), img.size
    elif sys.platform == "win32":
        w, h, bgra = _capturar_bgra_windows(ancho)
        datos, fmt = bgra_a_png(w, h, bgra), "png"
    else:
        raise OSError("Sin Pillow solo se puede capturar la pantalla en Windows.")
    return {"tipo": "frame", "fmt": fmt, "img": base64.b64encode(datos).decode("ascii"),
            "w": w, "h": h}
