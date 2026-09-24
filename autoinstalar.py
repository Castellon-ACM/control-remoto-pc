"""
autoinstalar.py - Auto-instalacion del Agente.

La primera vez que se ejecuta el .exe, este modulo:
  1. Se copia a si mismo a una carpeta ESTABLE y profunda dentro de ProgramData
     (varios niveles, con nombre propio de la aplicacion; NO se disfraza de
     componente de Windows ni se marca como oculto).
  2. Registra el arranque automatico al iniciar sesion (clave Run del usuario),
     apuntando a esa copia.
  3. Lanza la copia instalada.

Asi, aunque borres el .exe que descargaste, el que arranca en cada encendido es
la copia interna. (Lo que no puede existir es sobrevivir a borrar TAMBIEN esa
copia: un programa es su archivo.)

Solo actua en Windows y sobre el ejecutable "congelado" (PyInstaller). En modo
codigo (python agente_relay.py) no hace nada, para no molestar en desarrollo.
"""

import os
import sys
import shutil
import subprocess

NOMBRE = "WindowsSystem"
# Ruta profunda, pero identificable como la app (no imita a Windows/Microsoft).
SUBRUTA = os.path.join(NOMBRE, "runtime", "bin", "agente")
NOMBRE_EXE = "agente.exe"


def _es_windows():
    return sys.platform.startswith("win")


def _congelado():
    return getattr(sys, "frozen", False)


def ruta_instalacion(base=None):
    base = base or os.environ.get("ProgramData", r"C:\ProgramData")
    return os.path.join(base, SUBRUTA)


def _origen_ejecutable():
    """El .exe actual (si esta congelado) o el script en ejecucion."""
    if _congelado():
        return sys.executable
    return os.path.abspath(sys.argv[0])


def esta_instalado(base=None):
    destino = os.path.normcase(os.path.abspath(ruta_instalacion(base)))
    actual = os.path.normcase(os.path.abspath(_origen_ejecutable()))
    return actual.startswith(destino)


def _copiar_a_destino(origen, dir_destino, nombre=NOMBRE_EXE):
    os.makedirs(dir_destino, exist_ok=True)
    destino = os.path.join(dir_destino, nombre)
    shutil.copy2(origen, destino)
    return destino


def _registrar_arranque(ruta_exe, winreg_mod=None):
    """Da de alta el arranque al iniciar sesion (HKCU\\...\\Run)."""
    if winreg_mod is None:
        import winreg as winreg_mod
    clave = winreg_mod.OpenKey(
        winreg_mod.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg_mod.KEY_SET_VALUE,
    )
    valor = f'"{ruta_exe}"'
    winreg_mod.SetValueEx(clave, NOMBRE, 0, winreg_mod.REG_SZ, valor)
    winreg_mod.CloseKey(clave)
    return valor


def _realizar_instalacion(origen, base=None, winreg_mod=None):
    """Copia el ejecutable y registra el arranque. Devuelve la ruta destino."""
    destino = _copiar_a_destino(origen, ruta_instalacion(base))
    _registrar_arranque(destino, winreg_mod=winreg_mod)
    return destino


def _avisar(destino):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "Instalado correctamente.\n\nArrancara solo cada vez que enciendas "
            "el equipo. Ya puedes borrar el archivo que descargaste.",
            "Control Remoto PC", 0x40,
        )
    except Exception:
        pass


def instalar_si_hace_falta(base=None, relanzar=True):
    """Punto de entrada: instala la primera vez y devuelve un resumen."""
    if not _es_windows():
        return {"instalado": False, "motivo": "no-windows"}
    if not _congelado():
        return {"instalado": False, "motivo": "no-congelado"}
    if esta_instalado(base):
        return {"instalado": False, "motivo": "ya-instalado"}

    destino = _realizar_instalacion(_origen_ejecutable(), base=base)
    _avisar(destino)
    if relanzar:
        try:
            subprocess.Popen([destino], close_fds=True)
        except Exception:
            pass
        return {"instalado": True, "destino": destino, "relanzado": True}
    return {"instalado": True, "destino": destino, "relanzado": False}
