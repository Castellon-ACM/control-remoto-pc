"""
Tests del modo NUBE (nube.py, agente_nube.py, consola_nube.py).

Para no depender de Internet se levanta un broker MQTT minimo en localhost
(solo lo necesario: CONNECT, SUBSCRIBE, PUBLISH QoS 0, PINGREQ). El codigo del
proyecto es exactamente el mismo que habla con broker.emqx.io, pero sin TLS.
"""

import base64
import queue
import socket
import struct
import threading
import time
import zlib

import pytest

import agente
import nube
import agente_nube
import consola_nube

CLAVE = "clave-de-prueba-123"


# ---------------------------------------------------------------------------
# Broker MQTT de juguete
# ---------------------------------------------------------------------------
class BrokerFalso:
    def __init__(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(16)
        self.puerto = self.srv.getsockname()[1]
        self.subs = {}          # topic -> [conn]
        self.publicados = []    # (topic, payload) para inspeccionar lo que "ve" el broker
        self.lock = threading.Lock()
        self.conns = []
        threading.Thread(target=self._aceptar, daemon=True).start()

    def _aceptar(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.conns.append(c)
            threading.Thread(target=self._cliente, args=(c,), daemon=True).start()

    @staticmethod
    def _leer(c, n):
        b = bytearray()
        while len(b) < n:
            p = c.recv(n - len(b))
            if not p:
                raise ConnectionError
            b.extend(p)
        return bytes(b)

    def _cliente(self, c):
        try:
            while True:
                cab = self._leer(c, 1)[0]
                mult, lon = 1, 0
                while True:
                    b = self._leer(c, 1)[0]
                    lon += (b & 0x7F) * mult
                    if not b & 0x80:
                        break
                    mult *= 128
                datos = self._leer(c, lon) if lon else b""
                t = cab & 0xF0
                if t == 0x10:
                    c.sendall(b"\x20\x02\x00\x00")
                elif t == 0x80:
                    pid = datos[:2]
                    (lt,) = struct.unpack(">H", datos[2:4])
                    topic = datos[4:4 + lt].decode()
                    with self.lock:
                        self.subs.setdefault(topic, []).append(c)
                    c.sendall(b"\x90\x03" + pid + b"\x00")
                elif t == 0x30:
                    (lt,) = struct.unpack(">H", datos[:2])
                    topic = datos[2:2 + lt].decode()
                    with self.lock:
                        self.publicados.append((topic, datos[2 + lt:]))
                        destinos = list(self.subs.get(topic, []))
                    paquete = bytes([0x30]) + nube._longitud_restante(len(datos)) + datos
                    for d in destinos:
                        try:
                            d.sendall(paquete)
                        except OSError:
                            pass
                elif t == 0xC0:
                    c.sendall(b"\xd0\x00")
                elif t == 0xE0:
                    break
        except (ConnectionError, OSError):
            pass
        with self.lock:
            for lista in self.subs.values():
                if c in lista:
                    lista.remove(c)
        try:
            c.close()
        except OSError:
            pass

    def cerrar(self):
        self.srv.close()
        for c in self.conns:
            try:
                c.close()
            except OSError:
                pass


@pytest.fixture
def broker():
    b = BrokerFalso()
    yield b
    b.cerrar()


def _frame_falso(ancho, formatos):
    png = nube.bgra_a_png(4, 2, bytes(range(32)))
    return {"tipo": "frame", "fmt": "png", "img": base64.b64encode(png).decode(),
            "w": 4, "h": 2}


@pytest.fixture
def sistema(broker, monkeypatch):
    llamadas = []
    monkeypatch.setattr(agente, "accion_apagar", lambda m: llamadas.append(("apagar", m)) or "apagando")
    monkeypatch.setattr(agente, "accion_congelar_raton",
                        lambda s: llamadas.append(("congelar", s)) or f"congelado {s}s")
    ag = agente_nube.AgenteNube("127.0.0.1", broker.puerto, "sala-test", CLAVE,
                                margen=1, log=lambda *a: None, tls=False,
                                capturar=_frame_falso)
    threading.Thread(target=ag.run, daemon=True).start()
    # Espera a que el agente se suscriba
    for _ in range(100):
        if ag.canal.topic_agente in broker.subs:
            break
        time.sleep(0.05)
    con = consola_nube.ClienteConsolaNube("127.0.0.1", broker.puerto, "sala-test", CLAVE, tls=False)
    colas = {"frame": queue.Queue(), "resp": queue.Queue(), "estado": queue.Queue()}
    con.on_frame = colas["frame"].put
    con.on_respuesta = colas["resp"].put
    con.on_estado = colas["estado"].put
    con.conectar()
    yield ag, con, colas, llamadas
    con.cerrar()
    ag.parar()


def _esperar_estado(q, prefijo, t=5):
    fin = time.time() + t
    while time.time() < fin:
        try:
            e = q.get(timeout=fin - time.time())
        except queue.Empty:
            break
        if e.startswith(prefijo):
            return e
    raise AssertionError(f"no llego el estado {prefijo}")


# ---------------------------------------------------------------------------
# Cifrado
# ---------------------------------------------------------------------------
def test_sobre_ida_y_vuelta():
    c = nube.Canal("s", CLAVE, iteraciones=1000)
    datos = c.cerrar_sobre(nube.HACIA_AGENTE, {"accion": "apagar"})
    assert b"apagar" not in datos and CLAVE.encode() not in datos
    assert nube.Canal("s", CLAVE, iteraciones=1000).abrir_sobre(
        nube.HACIA_AGENTE, datos) == {"accion": "apagar"}


def test_clave_o_sala_distinta_no_abre_ni_comparte_topic():
    a = nube.Canal("s", CLAVE, iteraciones=1000)
    b = nube.Canal("s", CLAVE + "x", iteraciones=1000)
    c = nube.Canal("otra", CLAVE, iteraciones=1000)
    datos = a.cerrar_sobre(nube.HACIA_AGENTE, {"accion": "apagar"})
    assert b.abrir_sobre(nube.HACIA_AGENTE, datos) is None
    assert a.topic_agente != b.topic_agente != c.topic_agente


def test_manipulado_repetido_viejo_o_direccion_cambiada_se_rechaza(monkeypatch):
    a = nube.Canal("s", CLAVE, iteraciones=1000)
    datos = a.cerrar_sobre(nube.HACIA_AGENTE, {"accion": "apagar"})
    tocado = bytearray(datos)
    tocado[20] ^= 1
    assert a.abrir_sobre(nube.HACIA_AGENTE, bytes(tocado)) is None
    assert a.abrir_sobre(nube.HACIA_CONSOLA, datos) is None      # reflejado
    assert a.abrir_sobre(nube.HACIA_AGENTE, datos) is not None
    assert a.abrir_sobre(nube.HACIA_AGENTE, datos) is None       # replay
    viejo = a.cerrar_sobre(nube.HACIA_AGENTE, {"x": 1})
    monkeypatch.setattr(nube.time, "time", lambda: time.monotonic() + 1e10)
    assert a.abrir_sobre(nube.HACIA_AGENTE, viejo) is None


def test_clave_por_defecto_o_corta_no_vale():
    assert nube.validar_clave(nube.CLAVE_POR_DEFECTO)
    assert nube.validar_clave("corta")
    assert nube.validar_clave(CLAVE) is None
    with pytest.raises(ValueError):
        consola_nube.ClienteConsolaNube("h", 1, "s", nube.CLAVE_POR_DEFECTO)


def test_agente_con_clave_por_defecto_no_arranca():
    logs = []
    a = agente_nube.AgenteNube("127.0.0.1", 1, "s", nube.CLAVE_POR_DEFECTO, log=logs.append)
    a.run()   # debe volver enseguida sin conectarse
    assert "NO arranca" in logs[0]


# ---------------------------------------------------------------------------
# PNG sin Pillow
# ---------------------------------------------------------------------------
def test_png_332_es_valido():
    w, h = 3, 2
    bgra = bytes([0, 0, 255, 0, 0, 255, 0, 0, 255, 0, 0, 0] + [255] * 12)
    png = nube.bgra_a_png(w, h, bgra)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    idat = png[png.index(b"IDAT") + 4:png.index(b"IEND") - 8]
    filas = zlib.decompress(idat)
    assert filas == b"\x00" + bytes([0xE0, 0x1C, 0x03]) + b"\x00" + bytes([0xFF] * 3)
    try:
        from PIL import Image
    except ImportError:
        return
    import io
    img = Image.open(io.BytesIO(png)).convert("RGB")
    assert img.getpixel((0, 0)) == (255, 0, 0) and img.getpixel((2, 1)) == (255, 255, 255)


# ---------------------------------------------------------------------------
# Extremo a extremo por el broker
# ---------------------------------------------------------------------------
def test_presencia_y_orden(sistema, broker):
    ag, con, colas, llamadas = sistema
    assert _esperar_estado(colas["estado"], "en_linea:") == "en_linea:" + socket.gethostname()
    con.enviar_orden("apagar")
    r = colas["resp"].get(timeout=5)
    assert r["ok"] and r["mensaje"] == "apagando" and llamadas == [("apagar", 1)]
    # El broker publico solo ve bytes ilegibles: ni la clave ni la orden.
    for topic, payload in broker.publicados:
        assert topic.startswith("crp/") and b"apagar" not in payload
        assert CLAVE.encode() not in payload


def test_congelar_con_segundos(sistema):
    ag, con, colas, llamadas = sistema
    con.enviar_orden("congelar_raton", {"segundos": 7})
    r = colas["resp"].get(timeout=5)
    assert r["ok"] and ("congelar", 7) in llamadas


def test_visor_envia_frames_y_se_para(sistema):
    ag, con, colas, _ = sistema
    con.ver_pantalla(True, fps=4, ancho=320)
    f = colas["frame"].get(timeout=5)
    assert f["fmt"] == "png" and base64.b64decode(f["img"]).startswith(b"\x89PNG")
    con.ver_pantalla(False)
    time.sleep(0.8)
    while not colas["frame"].empty():
        colas["frame"].get()
    time.sleep(0.8)
    assert colas["frame"].empty()


def test_intruso_con_otra_clave_no_controla(sistema, broker, monkeypatch):
    ag, con, colas, llamadas = sistema
    # Un intruso publica en el MISMO topic del agente pero sin conocer la clave.
    intruso = nube.ClienteMQTT("127.0.0.1", broker.puerto, tls=False)
    intruso.conectar()
    falso = nube.Canal("sala-test", "otra-clave-cualquiera")
    intruso.publicar(ag.canal.topic_agente,
                     falso.cerrar_sobre(nube.HACIA_AGENTE, {"accion": "apagar"}))
    # Y reenvia tal cual un mensaje legitimo capturado (replay).
    con.enviar_orden("congelar_raton", {"segundos": 3})
    colas["resp"].get(timeout=5)
    legitimo = [p for t, p in broker.publicados if t == ag.canal.topic_agente][-1]
    intruso.publicar(ag.canal.topic_agente, legitimo)
    time.sleep(0.5)
    intruso.cerrar()
    assert ("apagar", 1) not in llamadas
    assert llamadas.count(("congelar", 3)) == 1


def test_agente_se_reconecta_si_cae_el_broker(broker):
    ag = agente_nube.AgenteNube("127.0.0.1", broker.puerto, "s2", CLAVE, log=lambda *a: None,
                                tls=False, capturar=_frame_falso)
    threading.Thread(target=ag.run, daemon=True).start()
    for _ in range(100):
        if broker.subs.get(ag.canal.topic_agente):
            break
        time.sleep(0.05)
    with broker.lock:
        conns = list(broker.subs[ag.canal.topic_agente])
    for c in conns:
        c.shutdown(socket.SHUT_RDWR)
    fin = time.time() + 8
    while time.time() < fin:
        if broker.subs.get(ag.canal.topic_agente):
            break
        time.sleep(0.1)
    ag.parar()
    assert broker.subs.get(ag.canal.topic_agente) is not None
