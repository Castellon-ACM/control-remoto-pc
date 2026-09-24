"""Tests del modulo de auto-instalacion."""

import os
import types

import autoinstalar


def test_ruta_es_profunda_y_con_nombre_propio(tmp_path):
    ruta = autoinstalar.ruta_instalacion(str(tmp_path))
    # Varios niveles dentro de ProgramData, con el nombre de la app.
    assert "ControlRemotoPC" in ruta
    partes = ruta.replace(str(tmp_path), "").strip(os.sep).split(os.sep)
    assert len(partes) >= 3          # runtime/bin/agente...
    # No se disfraza de componente de Windows/Microsoft.
    assert "Microsoft" not in ruta and "\\Windows\\" not in ruta


def test_copiar_a_destino(tmp_path):
    origen = tmp_path / "descargado.exe"
    origen.write_bytes(b"contenido-del-exe")
    dir_destino = tmp_path / "destino"
    destino = autoinstalar._copiar_a_destino(str(origen), str(dir_destino))
    assert os.path.exists(destino)
    assert open(destino, "rb").read() == b"contenido-del-exe"


def test_esta_instalado(monkeypatch, tmp_path):
    dentro = os.path.join(autoinstalar.ruta_instalacion(str(tmp_path)), "agente.exe")
    fuera = str(tmp_path / "Downloads" / "agente.exe")

    monkeypatch.setattr(autoinstalar, "_origen_ejecutable", lambda: dentro)
    assert autoinstalar.esta_instalado(str(tmp_path)) is True

    monkeypatch.setattr(autoinstalar, "_origen_ejecutable", lambda: fuera)
    assert autoinstalar.esta_instalado(str(tmp_path)) is False


def test_registrar_arranque_usa_la_ruta(tmp_path):
    registrado = {}

    class _FakeWinreg:
        HKEY_CURRENT_USER = "HKCU"
        KEY_SET_VALUE = 2
        REG_SZ = 1

        def OpenKey(self, raiz, sub, r, acceso):
            return ("clave", raiz, sub)

        def SetValueEx(self, clave, nombre, r, tipo, valor):
            registrado["nombre"] = nombre
            registrado["valor"] = valor

        def CloseKey(self, clave):
            pass

    ruta_exe = str(tmp_path / "agente.exe")
    valor = autoinstalar._registrar_arranque(ruta_exe, winreg_mod=_FakeWinreg())
    assert registrado["nombre"] == autoinstalar.NOMBRE
    assert ruta_exe in registrado["valor"]
    assert valor.startswith('"') and valor.endswith('"')


def test_instalacion_completa_con_winreg_falso(tmp_path):
    origen = tmp_path / "descargado.exe"
    origen.write_bytes(b"exe")

    escrito = {}

    class _FakeWinreg:
        HKEY_CURRENT_USER = "HKCU"
        KEY_SET_VALUE = 2
        REG_SZ = 1
        def OpenKey(self, *a): return "k"
        def SetValueEx(self, clave, nombre, r, tipo, valor): escrito["valor"] = valor
        def CloseKey(self, k): pass

    destino = autoinstalar._realizar_instalacion(
        str(origen), base=str(tmp_path), winreg_mod=_FakeWinreg()
    )
    assert os.path.exists(destino)
    assert destino in escrito["valor"]


def test_no_hace_nada_fuera_de_windows():
    # En Linux (entorno de test) no debe intentar instalar nada.
    r = autoinstalar.instalar_si_hace_falta()
    assert r["instalado"] is False
    assert r["motivo"] in ("no-windows", "no-congelado")
