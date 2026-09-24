"""Tests de las acciones del sistema, con subprocess simulado."""

import agente
import pytest


class _PopenFalso:
    """Registra la ultima llamada a subprocess.Popen sin ejecutar nada."""

    llamadas = []

    def __init__(self, args, *a, **k):
        type(self).llamadas.append(list(args))


@pytest.fixture
def en_windows(monkeypatch):
    """Finge que estamos en Windows y captura las llamadas a Popen."""
    _PopenFalso.llamadas = []
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    monkeypatch.setattr(agente.subprocess, "Popen", _PopenFalso)
    return _PopenFalso


@pytest.fixture
def fuera_de_windows(monkeypatch):
    monkeypatch.setattr(agente, "_es_windows", lambda: False)
    # Si algo intentara ejecutar Popen, el test fallaria.
    monkeypatch.setattr(
        agente.subprocess, "Popen",
        lambda *a, **k: pytest.fail("No se debe ejecutar Popen fuera de Windows"),
    )


def test_apagar_llama_a_shutdown_s(en_windows):
    msg = agente.accion_apagar(15)
    assert en_windows.llamadas[-1] == ["shutdown", "/s", "/t", "15"]
    assert "15" in msg


def test_reiniciar_llama_a_shutdown_r(en_windows):
    agente.accion_reiniciar(20)
    assert en_windows.llamadas[-1] == ["shutdown", "/r", "/t", "20"]


def test_suspender_usa_rundll32(en_windows):
    agente.accion_suspender()
    args = en_windows.llamadas[-1]
    assert args[0] == "rundll32.exe"
    assert "SetSuspendState" in args[1]


def test_cancelar_llama_a_shutdown_a(en_windows):
    msg = agente.accion_cancelar()
    assert en_windows.llamadas[-1] == ["shutdown", "/a"]
    assert "cancel" in msg.lower()


@pytest.mark.parametrize(
    "funcion", [
        lambda: agente.accion_apagar(10),
        lambda: agente.accion_reiniciar(10),
        agente.accion_suspender,
        agente.accion_cancelar,
    ],
)
def test_fuera_de_windows_no_ejecuta_nada(fuera_de_windows, funcion):
    msg = funcion()
    assert "Simulado" in msg
