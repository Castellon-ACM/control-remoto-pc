"""
Test de extremo a extremo del modo remoto:
    relay.py  <->  agente_relay.AgenteRelay  <->  consola_relay.ClienteConsolaRelay
Todo en localhost. Prueba ordenes y streaming de pantalla (captura simulada).
"""

import base64
import socket
import threading
import time
import queue

import pytest

import agente
import relay
import remoto
import agente_relay
import consola_relay


def _puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def rele():
    relay._salas.clear()
    puerto = _puerto_libre()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", puerto))
    srv.listen(16)
    vivo = threading.Event()
    vivo.set()

    def _aceptar():
        while vivo.is_set():
            try:
                conn, addr = srv.accept()
            except OSError:
                break
            threading.Thread(target=relay._manejar, args=(conn, addr), daemon=True).start()

    threading.Thread(target=_aceptar, daemon=True).start()
    yield puerto
    vivo.clear()
    srv.close()
    relay._salas.clear()


@pytest.fixture
def sistema(rele):
    """Levanta el agente en modo rele y un cliente de consola conectado."""
    ag = agente_relay.AgenteRelay(
        host="127.0.0.1", puerto=rele, sala="demo", clave="k",
        margen=1, log=lambda *a: None,
    )
    threading.Thread(target=ag.run, daemon=True).start()
    time.sleep(0.3)  # deja que el agente se registre

    respuestas = queue.Queue()
    frames = queue.Queue()
    cli = consola_relay.ClienteConsolaRelay("127.0.0.1", rele, "demo", "k")
    cli.on_respuesta = respuestas.put
    cli.on_frame = frames.put
    cli.conectar()
    time.sleep(0.3)  # deja que se emparejen

    yield cli, respuestas, frames, ag

    cli.cerrar()
    ag.parar()


def test_ping_por_rele(sistema):
    cli, respuestas, _frames, _ag = sistema
    cli.enviar_orden("ping")
    r = respuestas.get(timeout=5)
    assert r["ok"] is True
    assert "activo" in r["mensaje"].lower()


def test_clave_incorrecta_por_rele(rele):
    ag = agente_relay.AgenteRelay("127.0.0.1", rele, "demo", "k", 1, lambda *a: None)
    threading.Thread(target=ag.run, daemon=True).start()
    time.sleep(0.3)
    respuestas = queue.Queue()
    cli = consola_relay.ClienteConsolaRelay("127.0.0.1", rele, "demo", "CLAVE-MALA")
    cli.on_respuesta = respuestas.put
    cli.conectar()
    time.sleep(0.2)
    cli.enviar_orden("ping")
    r = respuestas.get(timeout=5)
    assert r["ok"] is False
    assert "Clave incorrecta" in r["mensaje"]
    cli.cerrar()
    ag.parar()


def test_apagar_por_rele(sistema, monkeypatch):
    cli, respuestas, _frames, _ag = sistema
    llamadas = []
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    monkeypatch.setattr(
        agente.subprocess, "Popen", lambda args, *a, **k: llamadas.append(list(args))
    )
    cli.enviar_orden("apagar")
    r = respuestas.get(timeout=5)
    assert r["ok"] is True
    assert llamadas and llamadas[-1][:2] == ["shutdown", "/s"]


def test_congelar_por_rele_simulado(sistema, monkeypatch):
    cli, respuestas, _frames, _ag = sistema
    monkeypatch.setattr(agente, "_es_windows", lambda: False)
    cli.enviar_orden("congelar_raton", extra={"segundos": 25})
    r = respuestas.get(timeout=5)
    assert r["ok"] is True
    assert "Simulado" in r["mensaje"]


def test_streaming_de_pantalla(sistema, monkeypatch):
    cli, _respuestas, frames, _ag = sistema

    # Captura simulada: no necesita pantalla real ni Pillow.
    frame_falso = {
        "tipo": "frame",
        "jpeg": base64.b64encode(b"jpeg-de-mentira").decode("ascii"),
        "w": 320, "h": 180,
    }
    monkeypatch.setattr(remoto, "capturar_frame", lambda ancho, calidad: frame_falso)

    cli.ver_pantalla(activar=True, fps=20, ancho=320)
    recibido = frames.get(timeout=5)          # llega al menos un fotograma
    assert recibido["tipo"] == "frame"
    assert remoto.decodificar_frame(recibido) == b"jpeg-de-mentira"
    cli.ver_pantalla(activar=False)


def _png_b64():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (6, 6), (0, 100, 200)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_fondo_por_rele_simulado(sistema, monkeypatch):
    cli, respuestas, _frames, _ag = sistema
    monkeypatch.setattr(agente, "_es_windows", lambda: False)
    cli.enviar_fondo(_png_b64())
    r = respuestas.get(timeout=5)
    assert r["ok"] is True
    assert "Simulado" in r["mensaje"]


def test_fondo_por_rele_windows(sistema, monkeypatch, tmp_path):
    import types
    cli, respuestas, _frames, _ag = sistema

    class _User32:
        def SystemParametersInfoW(self, accion, uparam, ruta, flags):
            return 1

    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    monkeypatch.setattr(agente.ctypes, "windll",
                        types.SimpleNamespace(user32=_User32()), raising=False)
    monkeypatch.setenv("ProgramData", str(tmp_path))

    cli.enviar_fondo(_png_b64())
    r = respuestas.get(timeout=5)
    assert r["ok"] is True
    assert "cambiado" in r["mensaje"].lower()
