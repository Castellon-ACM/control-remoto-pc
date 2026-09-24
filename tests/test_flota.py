"""
Test del descubrimiento automatico (flota) sobre el broker MQTT de juguete:
un agente se anuncia con su baliza y el GestorFlota lo descubre solo y lo controla.
"""

import time
import base64
import queue

import pytest

import agente
import nube
import agente_nube
import flota
from test_nube import BrokerFalso, CLAVE


@pytest.fixture
def broker():
    b = BrokerFalso()
    yield b
    b.cerrar()


def _frame_falso(ancho, formatos):
    png = nube.bgra_a_png(4, 2, bytes(range(32)))
    return {"tipo": "frame", "fmt": "png", "img": base64.b64encode(png).decode(), "w": 4, "h": 2}


def _esperar(cond, limite=6.0):
    fin = time.time() + limite
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_sala_unica_por_pc():
    s = flota.sala_de_este_pc()
    assert s.startswith("eq-")
    assert s == flota.sala_de_este_pc()   # estable


@pytest.fixture
def flota_montada(broker):
    sala = "eq-prueba-abc123"
    ag = agente_nube.AgenteNube("127.0.0.1", broker.puerto, sala, CLAVE,
                                tls=False, log=lambda *a: None, capturar=_frame_falso)
    import threading
    threading.Thread(target=ag.run, daemon=True).start()
    baliza = flota.Baliza("127.0.0.1", broker.puerto, CLAVE, sala,
                          hostname="PC-PRUEBA", tls=False, intervalo=0.2)
    threading.Thread(target=baliza.run, daemon=True).start()

    respuestas = queue.Queue()
    frames = queue.Queue()
    nuevos = queue.Queue()
    g = flota.GestorFlota("127.0.0.1", broker.puerto, CLAVE, tls=False, timeout=3.0)
    g.on_respuesta = lambda s, m: respuestas.put((s, m))
    g.on_frame = lambda s, m: frames.put((s, m))
    g.on_nuevo = lambda s, h: nuevos.put((s, h))
    g.conectar()
    yield g, sala, respuestas, frames, nuevos
    g.cerrar()
    ag.parar()
    baliza.parar()


def test_descubre_el_equipo_solo(flota_montada):
    g, sala, _, _, nuevos = flota_montada
    assert _esperar(lambda: sala in g.salas()), "el monitor deberia descubrir el equipo"
    s, host = nuevos.get(timeout=5)
    assert s == sala and host == "PC-PRUEBA"


def test_controla_el_equipo_descubierto(flota_montada):
    g, sala, respuestas, _, _ = flota_montada
    assert _esperar(lambda: sala in g.salas())
    g.enviar(sala, "ping")
    # Puede llegar el "hola" inicial; buscamos la respuesta con "activo".
    fin = time.time() + 5
    visto = False
    while time.time() < fin and not visto:
        try:
            s, m = respuestas.get(timeout=1)
            if "activo" in str(m.get("mensaje", "")).lower():
                visto = True
        except queue.Empty:
            break
    assert visto, "el equipo descubierto deberia responder al ping"


def test_streaming_del_equipo(flota_montada):
    g, sala, _, frames, _ = flota_montada
    assert _esperar(lambda: sala in g.salas())
    g.ver(sala, activar=True, fps=20, ancho=100)
    s, m = frames.get(timeout=5)
    assert s == sala and m.get("tipo") == "frame"
    g.ver(sala, activar=False)
