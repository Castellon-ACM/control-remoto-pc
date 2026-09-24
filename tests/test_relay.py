"""Tests del servidor rele (emparejamiento y reenvio de bytes)."""

import socket
import threading
import time

import pytest

import relay
import remoto


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
    corriendo = threading.Event()
    corriendo.set()

    def _aceptar():
        while corriendo.is_set():
            try:
                conn, addr = srv.accept()
            except OSError:
                break
            threading.Thread(target=relay._manejar, args=(conn, addr), daemon=True).start()

    hilo = threading.Thread(target=_aceptar, daemon=True)
    hilo.start()
    yield puerto
    corriendo.clear()
    srv.close()
    relay._salas.clear()


def _conectar(puerto, sala, rol):
    s = socket.create_connection(("127.0.0.1", puerto), timeout=5)
    remoto.enviar_mensaje(s, {"sala": sala, "rol": rol})
    return s


def test_reenvia_en_ambos_sentidos(rele):
    agente = _conectar(rele, "sala1", "agente")
    consola = _conectar(rele, "sala1", "consola")
    time.sleep(0.2)  # deja que se emparejen

    # consola -> agente
    remoto.enviar_mensaje(consola, {"orden": "hola"})
    assert remoto.recibir_mensaje(agente) == {"orden": "hola"}

    # agente -> consola
    remoto.enviar_mensaje(agente, {"resp": "ok"})
    assert remoto.recibir_mensaje(consola) == {"resp": "ok"}

    agente.close()
    consola.close()


def test_empareja_aunque_llegue_antes_la_consola(rele):
    consola = _conectar(rele, "sala2", "consola")
    time.sleep(0.1)
    agente = _conectar(rele, "sala2", "agente")
    time.sleep(0.2)

    remoto.enviar_mensaje(consola, {"x": 1})
    assert remoto.recibir_mensaje(agente) == {"x": 1}

    agente.close()
    consola.close()


def test_rechaza_segundo_del_mismo_rol(rele):
    c1 = _conectar(rele, "sala3", "consola")
    c2 = _conectar(rele, "sala3", "consola")
    # El segundo recibe un error del rele.
    respuesta = remoto.recibir_mensaje(c2)
    assert respuesta is not None and "error" in respuesta
    c1.close()
    c2.close()
