"""
Tests del monitor multi-equipo: estado en vivo (conectado/desconectado),
persistencia y renombrado, reconexion automatica y acciones dirigidas.
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


def _lanzar_agente(rele, sala):
    ag = agente_relay.AgenteRelay("127.0.0.1", rele, sala, "k", 1, lambda *a: None)
    threading.Thread(target=ag.run, daemon=True).start()
    return ag


def _gestor(rele, salas):
    equipos = [{"nombre": s.upper(), "sala": s} for s in salas]
    return consola_multi.GestorMulti("127.0.0.1", rele, "k", equipos,
                                     intervalo=0.3, timeout=1.2)


def _esperar(cond, limite=6.0):
    fin = time.time() + limite
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.1)
    return False


# --- Persistencia y renombrado (sin red) ------------------------------------
def test_guardar_cargar_y_renombrar(tmp_path):
    ruta = tmp_path / "equipos_multi.json"
    cfg = {
        "host": "h", "puerto": 1, "clave": "k",
        "equipos": [{"nombre": "PC-1", "sala": "pc1"},
                    {"nombre": "PC-2", "sala": "pc2"}],
    }
    consola_multi.guardar_equipos_multi(cfg, str(ruta))
    consola_multi.renombrar_equipo(cfg, "pc1", "Ordenador Papa", str(ruta))

    recargado = consola_multi.cargar_equipos_multi(str(ruta))
    nombres = {e["sala"]: e["nombre"] for e in recargado["equipos"]}
    assert nombres["pc1"] == "Ordenador Papa"
    assert nombres["pc2"] == "PC-2"


def test_plantilla_se_crea_sola(tmp_path):
    ruta = tmp_path / "nuevo.json"
    cfg = consola_multi.cargar_equipos_multi(str(ruta))
    assert ruta.exists()
    assert len(cfg["equipos"]) >= 1


# --- Estado en vivo ----------------------------------------------------------
def test_detecta_encendidos_y_apagados(rele):
    _lanzar_agente(rele, "pc1")
    _lanzar_agente(rele, "pc2")
    g = _gestor(rele, ["pc1", "pc2", "pc3"])
    g.conectar()
    try:
        assert _esperar(lambda: g.conectados()["pc1"] and g.conectados()["pc2"])
        # pc3 no tiene agente: desconectado, pero sigue en la lista.
        assert g.conectados()["pc3"] is False
        assert "pc3" in g.salas()
    finally:
        g.cerrar()


def test_reconexion_cuando_se_enciende(rele):
    g = _gestor(rele, ["pc1"])
    g.conectar()
    try:
        assert _esperar(lambda: g.conectados()["pc1"] is False)
        _lanzar_agente(rele, "pc1")
        assert _esperar(lambda: g.conectados()["pc1"] is True)
    finally:
        g.cerrar()


# --- Acciones dirigidas ------------------------------------------------------
@pytest.fixture
def flota(rele):
    _lanzar_agente(rele, "pc1")
    _lanzar_agente(rele, "pc2")
    respuestas = {"pc1": queue.Queue(), "pc2": queue.Queue()}
    frames = {"pc1": queue.Queue(), "pc2": queue.Queue()}
    g = _gestor(rele, ["pc1", "pc2"])
    g.on_respuesta = lambda s, m: respuestas[s].put(m)
    g.on_frame = lambda s, m: frames[s].put(m)
    g.conectar()
    assert _esperar(lambda: g.conectados()["pc1"] and g.conectados()["pc2"])
    yield g, respuestas, frames
    g.cerrar()


def test_orden_solo_al_equipo_elegido(flota, monkeypatch):
    g, respuestas, _ = flota
    monkeypatch.setattr(agente, "_es_windows", lambda: False)
    g.enviar("pc1", "congelar_raton", {"segundos": 10})
    assert "Simulado" in respuestas["pc1"].get(timeout=5)["mensaje"]
    with pytest.raises(queue.Empty):
        respuestas["pc2"].get(timeout=1)


def test_fondo_a_uno_apagar_a_otro(flota, monkeypatch):
    g, respuestas, _ = flota
    monkeypatch.setattr(agente, "_es_windows", lambda: False)
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (0, 0, 0)).save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    g.fondo("pc1", b64)
    g.enviar("pc2", "apagar")
    assert "Simulado" in respuestas["pc1"].get(timeout=5)["mensaje"]
    assert "Simulado" in respuestas["pc2"].get(timeout=5)["mensaje"]


def test_streaming_solo_del_elegido(flota, monkeypatch):
    g, _, frames = flota
    frame_falso = {"tipo": "frame",
                   "jpeg": base64.b64encode(b"x").decode("ascii"), "w": 10, "h": 10}
    monkeypatch.setattr(remoto, "capturar_frame", lambda ancho, calidad: frame_falso)
    g.ver("pc1", activar=True, fps=20, ancho=100)
    assert frames["pc1"].get(timeout=5)["tipo"] == "frame"
    with pytest.raises(queue.Empty):
        frames["pc2"].get(timeout=1)
    g.ver("pc1", activar=False)
