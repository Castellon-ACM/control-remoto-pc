"""
Test del monitor multi-equipo: levanta el rele y VARIOS agentes (cada uno en su
sala), conecta el GestorMulti con todos y comprueba que las acciones van al
equipo correcto y que cada uno manda su propia pantalla.
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
import consola_multi


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
def flota(rele):
    """Dos agentes en salas 'pc1' y 'pc2' + un GestorMulti conectado a ambos."""
    agentes = []
    for sala in ("pc1", "pc2"):
        ag = agente_relay.AgenteRelay("127.0.0.1", rele, sala, "k", 1, lambda *a: None)
        threading.Thread(target=ag.run, daemon=True).start()
        agentes.append(ag)
    time.sleep(0.3)

    respuestas = {"PC-1": queue.Queue(), "PC-2": queue.Queue()}
    frames = {"PC-1": queue.Queue(), "PC-2": queue.Queue()}

    gestor = consola_multi.GestorMulti(
        "127.0.0.1", rele, "k",
        [{"nombre": "PC-1", "sala": "pc1"}, {"nombre": "PC-2", "sala": "pc2"}],
    )
    gestor.on_respuesta = lambda n, m: respuestas[n].put(m)
    gestor.on_frame = lambda n, m: frames[n].put(m)
    gestor.conectar()
    time.sleep(0.3)

    yield gestor, respuestas, frames
    gestor.cerrar()
    for ag in agentes:
        ag.parar()


def test_ping_a_cada_equipo(flota):
    gestor, respuestas, _ = flota
    gestor.enviar("PC-1", "ping")
    gestor.enviar("PC-2", "ping")
    assert respuestas["PC-1"].get(timeout=5)["ok"] is True
    assert respuestas["PC-2"].get(timeout=5)["ok"] is True


def test_accion_dirigida_solo_a_uno(flota, monkeypatch):
    gestor, respuestas, _ = flota
    monkeypatch.setattr(agente, "_es_windows", lambda: False)
    # Congelar SOLO PC-1
    gestor.enviar("PC-1", "congelar_raton", {"segundos": 10})
    r1 = respuestas["PC-1"].get(timeout=5)
    assert "Simulado" in r1["mensaje"]
    # PC-2 no debe recibir nada de esa orden
    with pytest.raises(queue.Empty):
        respuestas["PC-2"].get(timeout=1)


def test_fondo_a_uno_y_apagar_a_otro(flota, monkeypatch):
    gestor, respuestas, _ = flota
    monkeypatch.setattr(agente, "_es_windows", lambda: False)

    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (0, 0, 0)).save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    gestor.fondo("PC-1", b64)
    gestor.enviar("PC-2", "apagar")

    assert "Simulado" in respuestas["PC-1"].get(timeout=5)["mensaje"]
    assert "Simulado" in respuestas["PC-2"].get(timeout=5)["mensaje"]


def test_broadcast_a_todos(flota):
    gestor, respuestas, _ = flota
    gestor.enviar("Todos", "ping")
    assert respuestas["PC-1"].get(timeout=5)["ok"] is True
    assert respuestas["PC-2"].get(timeout=5)["ok"] is True


def test_streaming_solo_del_equipo_pedido(flota, monkeypatch):
    gestor, _, frames = flota
    frame_falso = {"tipo": "frame",
                   "jpeg": base64.b64encode(b"x").decode("ascii"), "w": 10, "h": 10}
    monkeypatch.setattr(remoto, "capturar_frame", lambda ancho, calidad: frame_falso)

    gestor.ver("PC-1", activar=True, fps=20, ancho=100)
    assert frames["PC-1"].get(timeout=5)["tipo"] == "frame"
    # PC-2 no comparte pantalla, su cola sigue vacia
    with pytest.raises(queue.Empty):
        frames["PC-2"].get(timeout=1)
    gestor.ver("PC-1", activar=False)
