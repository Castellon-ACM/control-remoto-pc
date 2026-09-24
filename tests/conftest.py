"""
Configuracion comun de los tests.

Agente y Consola importan tkinter solo para la interfaz grafica; la logica de
red no lo necesita. Para poder probar esa logica en cualquier entorno (incluida
integracion continua sin escritorio), si no hay tkinter real se inyecta un
stub minimo. Esto NO cambia el codigo del proyecto: solo permite importarlo.
"""

import os
import sys
import types
import socket

# Permite importar agente.py y consola.py (estan en la carpeta padre).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _instalar_stub_tkinter():
    tk = types.ModuleType("tkinter")
    scrolledtext = types.ModuleType("tkinter.scrolledtext")
    ttk = types.ModuleType("tkinter.ttk")
    messagebox = types.ModuleType("tkinter.messagebox")
    simpledialog = types.ModuleType("tkinter.simpledialog")

    class _Dialog:  # base de DialogoEquipo (se evalua al importar consola.py)
        def __init__(self, *a, **k):
            pass

    simpledialog.Dialog = _Dialog

    submods = {
        "tkinter": tk,
        "tkinter.scrolledtext": scrolledtext,
        "tkinter.ttk": ttk,
        "tkinter.messagebox": messagebox,
        "tkinter.simpledialog": simpledialog,
    }
    for nombre, mod in submods.items():
        sys.modules[nombre] = mod
    tk.scrolledtext = scrolledtext
    tk.ttk = ttk
    tk.messagebox = messagebox
    tk.simpledialog = simpledialog


try:
    import tkinter  # noqa: F401
except Exception:
    _instalar_stub_tkinter()


def puerto_libre():
    """Devuelve un puerto TCP libre en localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
