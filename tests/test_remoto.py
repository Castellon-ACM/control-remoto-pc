"""Tests del modulo compartido remoto.py (framing y frames)."""

import base64
import socket

import remoto


def test_framing_ida_y_vuelta():
    a, b = socket.socketpair()
    try:
        remoto.enviar_mensaje(a, {"hola": "mundo", "n": 7})
        recibido = remoto.recibir_mensaje(b)
        assert recibido == {"hola": "mundo", "n": 7}
    finally:
        a.close()
        b.close()


def test_varios_mensajes_seguidos():
    a, b = socket.socketpair()
    try:
        remoto.enviar_mensaje(a, {"i": 1})
        remoto.enviar_mensaje(a, {"i": 2})
        remoto.enviar_mensaje(a, {"i": 3})
        assert remoto.recibir_mensaje(b)["i"] == 1
        assert remoto.recibir_mensaje(b)["i"] == 2
        assert remoto.recibir_mensaje(b)["i"] == 3
    finally:
        a.close()
        b.close()


def test_recibir_devuelve_none_al_cerrar():
    a, b = socket.socketpair()
    a.close()
    assert remoto.recibir_mensaje(b) is None
    b.close()


def test_decodificar_frame():
    contenido = b"esto seria un jpeg"
    msg = {"tipo": "frame", "jpeg": base64.b64encode(contenido).decode("ascii")}
    assert remoto.decodificar_frame(msg) == contenido
