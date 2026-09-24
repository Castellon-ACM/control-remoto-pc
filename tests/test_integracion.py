"""
Tests de integracion: levantan el servidor real del Agente y le hablan con la
funcion real de la Consola (enviar_orden) por un socket de localhost.
Asi se comprueba el protocolo completo de punta a punta.
"""

import json
import socket
import time

import agente
import consola
import pytest

CLAVE = "clave-de-prueba"


def _puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar_escucha(puerto, timeout=5.0):
    fin = time.time() + timeout
    while time.time() < fin:
        try:
            with socket.create_connection(("127.0.0.1", puerto), timeout=0.3):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("El servidor del agente no llego a escuchar")


@pytest.fixture
def servidor():
    puerto = _puerto_libre()
    srv = agente.ServidorAgente(
        puerto=puerto, clave=CLAVE, margen=1, log_callback=lambda m: None
    )
    srv.start()
    _esperar_escucha(puerto)
    yield puerto
    srv.parar()
    time.sleep(0.1)


# --- Protocolo basico --------------------------------------------------------
def test_ping_responde_activo(servidor):
    ok, msg = consola.enviar_orden("127.0.0.1", servidor, CLAVE, "ping")
    assert ok is True
    assert "activo" in msg.lower()


def test_clave_incorrecta_es_rechazada(servidor):
    ok, msg = consola.enviar_orden("127.0.0.1", servidor, "clave-mala", "ping")
    assert ok is False
    assert "Clave incorrecta" in msg


def test_accion_desconocida(servidor):
    ok, msg = consola.enviar_orden("127.0.0.1", servidor, CLAVE, "bailar")
    assert ok is False
    assert "desconocida" in msg.lower()


def test_json_invalido(servidor):
    # Enviamos algo que NO es JSON y comprobamos la respuesta de error.
    with socket.create_connection(("127.0.0.1", servidor), timeout=3) as s:
        s.sendall(b"esto no es json\n")
        datos = s.recv(4096).decode("utf-8").strip()
    resp = json.loads(datos)
    assert resp["ok"] is False
    assert "no valido" in resp["mensaje"].lower()


def test_conexion_rechazada_si_no_hay_agente():
    # Puerto libre sin nadie escuchando -> la consola lo reporta con claridad.
    ok, msg = consola.enviar_orden("127.0.0.1", _puerto_libre(), CLAVE, "ping")
    assert ok is False
    assert "rechazada" in msg.lower()


# --- Acciones a traves del protocolo (Windows simulado) ----------------------
def test_apagar_por_protocolo(servidor, monkeypatch):
    llamadas = []
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    monkeypatch.setattr(
        agente.subprocess, "Popen", lambda args, *a, **k: llamadas.append(list(args))
    )
    ok, msg = consola.enviar_orden("127.0.0.1", servidor, CLAVE, "apagar")
    assert ok is True
    assert llamadas and llamadas[-1][:2] == ["shutdown", "/s"]


# --- El extra: congelar el raton por el protocolo ----------------------------
def test_congelar_raton_viaja_el_parametro_segundos(servidor, monkeypatch):
    # Fuera de Windows: respuesta rapida y sin efectos, pero prueba que el campo
    # "segundos" llega bien desde la Consola hasta el Agente.
    monkeypatch.setattr(agente, "_es_windows", lambda: False)
    ok, msg = consola.enviar_orden(
        "127.0.0.1", servidor, CLAVE, "congelar_raton", extra={"segundos": 30}
    )
    assert ok is True
    assert "Simulado" in msg


def test_congelar_raton_por_protocolo_en_windows(servidor, monkeypatch):
    import types

    class _User32:
        def GetCursorPos(self, puntero):
            return True

        def SetCursorPos(self, x, y):
            return True

    windll = types.SimpleNamespace(user32=_User32())
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    monkeypatch.setattr(agente.ctypes, "windll", windll, raising=False)

    ok, msg = consola.enviar_orden(
        "127.0.0.1", servidor, CLAVE, "congelar_raton", extra={"segundos": 1}
    )
    assert ok is True
    assert "1s" in msg

    # Esperar a que se libere para no dejar el hilo corriendo.
    fin = time.time() + 5
    while agente._raton_congelado.is_set() and time.time() < fin:
        time.sleep(0.02)
    assert not agente._raton_congelado.is_set()
