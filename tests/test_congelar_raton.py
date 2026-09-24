"""Tests de la funcion extra: congelar el raton."""

import time
import types

import agente
import pytest


@pytest.fixture(autouse=True)
def _reset_estado():
    """Garantiza que ningun test empieza o acaba con el raton 'congelado'."""
    agente._raton_congelado.clear()
    yield
    agente._raton_congelado.clear()


# --- Utilidad: un user32 falso que registra las llamadas a SetCursorPos ------
class _User32Falso:
    def __init__(self):
        self.movimientos = 0

    def GetCursorPos(self, puntero):
        return True  # deja el punto en (0, 0); no nos importa el valor

    def SetCursorPos(self, x, y):
        self.movimientos += 1
        return True


def _instalar_windll_falso(monkeypatch):
    """Pone un windll.user32 falso en el ctypes real (deja byref/Structure)."""
    user32 = _User32Falso()
    windll = types.SimpleNamespace(user32=user32)
    monkeypatch.setattr(agente.ctypes, "windll", windll, raising=False)
    return user32


# --- Camino fuera de Windows (no hace nada) ----------------------------------
def test_simulado_fuera_de_windows(monkeypatch):
    monkeypatch.setattr(agente, "_es_windows", lambda: False)
    msg = agente.accion_congelar_raton(20)
    assert "Simulado" in msg


# --- Validaciones ------------------------------------------------------------
def test_segundos_no_numericos(monkeypatch):
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    _instalar_windll_falso(monkeypatch)
    assert "no valido" in agente.accion_congelar_raton("hola").lower()


def test_segundos_cero_o_negativos(monkeypatch):
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    _instalar_windll_falso(monkeypatch)
    assert "mayor que 0" in agente.accion_congelar_raton(0)
    assert "mayor que 0" in agente.accion_congelar_raton(-5)


def test_aplica_tope_de_seguridad(monkeypatch):
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    _instalar_windll_falso(monkeypatch)
    # Reloj simulado que avanza a saltos: el bucle termina enseguida en vez de
    # esperar los 300s reales del tope.
    contador = {"t": 0}

    def _monotonic():
        contador["t"] += 1000
        return contador["t"]

    monkeypatch.setattr(agente.time, "monotonic", _monotonic)
    msg = agente.accion_congelar_raton(99999)
    assert str(agente.CONGELAR_TOPE_SEGUNDOS) in msg
    _esperar_descongelado()


# --- Comportamiento real (con ctypes simulado) -------------------------------
def _esperar_descongelado(timeout=5.0):
    inicio = time.time()
    while agente._raton_congelado.is_set() and time.time() - inicio < timeout:
        time.sleep(0.02)


def test_congela_y_libera(monkeypatch):
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    user32 = _instalar_windll_falso(monkeypatch)

    msg = agente.accion_congelar_raton(1)          # 1 segundo
    assert "1s" in msg
    # Nada mas lanzarlo, debe estar marcado como congelado.
    assert agente._raton_congelado.is_set()

    _esperar_descongelado()
    assert not agente._raton_congelado.is_set()    # se libera solo
    assert user32.movimientos > 0      # ha fijado el cursor


def test_no_permite_dos_congelaciones_a_la_vez(monkeypatch):
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    _instalar_windll_falso(monkeypatch)
    agente._raton_congelado.set()                  # simulamos que ya esta activo
    try:
        msg = agente.accion_congelar_raton(5)
        assert "ya esta congelado" in msg
    finally:
        agente._raton_congelado.clear()
