"""
AGENTE REMOTO - Programa para el PC que quieres controlar (p. ej. el de casa)
============================================================================

Se ejecuta de forma VISIBLE: abre una ventana que muestra que el agente
esta activo, en que puerto escucha y un registro de las ordenes recibidas.

Escucha ordenes por red y solo las ejecuta si llegan con la CLAVE correcta.
Acciones soportadas: comprobar estado (ping), apagar, suspender y reiniciar.

Proyecto educativo. No tiene ninguna funcion oculta ni de control del raton.

Autor: (tu nombre)
"""

import socket
import threading
import json
import subprocess
import platform
import os
import sys
import time
import ctypes
import configparser
from datetime import datetime

import tkinter as tk
from tkinter import scrolledtext

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------
# La clave y el puerto se guardan en "config.ini" junto al programa.
# Si no existe, se crea con valores por defecto la primera vez.
# Si es un .exe (PyInstaller), junto al .exe; si no, junto a este archivo.
_BASE = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
         else os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(_BASE, "config.ini")

DEFAULTS = {
    "puerto": "50505",
    # CAMBIA esta clave por una tuya. Debe ser la misma en el Agente y en la Consola.
    "clave": "cambia-esta-clave-2026",
    # Segundos de margen antes de apagar/reiniciar (da tiempo a cancelar con "shutdown /a").
    "margen_segundos": "15",
}


def cargar_config():
    cfg = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    if "agente" not in cfg:
        cfg["agente"] = {}
    seccion = cfg["agente"]
    cambios = False
    for clave, valor in DEFAULTS.items():
        if clave not in seccion:
            seccion[clave] = valor
            cambios = True
    if cambios:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            cfg.write(f)
    return seccion


# ---------------------------------------------------------------------------
# Acciones del sistema (solo Windows)
# ---------------------------------------------------------------------------
def _es_windows():
    return platform.system().lower().startswith("win")


def accion_apagar(margen):
    if _es_windows():
        subprocess.Popen(["shutdown", "/s", "/t", str(margen)])
        return f"Apagando en {margen}s (cancelable con 'shutdown /a')."
    return "Simulado: apagar (no es Windows)."


def accion_reiniciar(margen):
    if _es_windows():
        subprocess.Popen(["shutdown", "/r", "/t", str(margen)])
        return f"Reiniciando en {margen}s (cancelable con 'shutdown /a')."
    return "Simulado: reiniciar (no es Windows)."


def accion_suspender(margen=None):
    if _es_windows():
        # Suspende el equipo. El primer parametro 0 = suspender (no hibernar).
        subprocess.Popen(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
        )
        return "Suspendiendo el equipo."
    return "Simulado: suspender (no es Windows)."


def accion_cancelar():
    if _es_windows():
        # Cancela un apagado/reinicio programado.
        subprocess.Popen(["shutdown", "/a"])
        return "Apagado/reinicio cancelado."
    return "Simulado: cancelar (no es Windows)."


# Evita lanzar dos congelaciones a la vez.
_raton_congelado = threading.Event()

# Tope de seguridad: nunca se congela mas de este tiempo, pase lo que pase.
CONGELAR_TOPE_SEGUNDOS = 300


class _PUNTO(ctypes.Structure):
    """Estructura POINT de Windows para leer la posicion del cursor."""
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def accion_congelar_raton(segundos):
    """Congela (fija) el cursor del raton durante 'segundos'.

    Clava el cursor EN LA POSICION EN LA QUE ESTE en ese momento, asi que el
    raton no se puede mover. El TECLADO SIGUE FUNCIONANDO (no se bloquea al
    usuario) y el raton se libera SOLO al terminar el tiempo. Solo tiene efecto
    en Windows y cuando el agente corre en la sesion del usuario (la ventana),
    no como servicio de la Sesion 0.
    """
    if not _es_windows():
        return "Simulado: congelar raton (no es Windows)."
    try:
        segundos = int(segundos)
    except (TypeError, ValueError):
        return "Parametro 'segundos' no valido."
    if segundos <= 0:
        return "Los segundos deben ser un numero mayor que 0."
    if segundos > CONGELAR_TOPE_SEGUNDOS:
        segundos = CONGELAR_TOPE_SEGUNDOS
    if _raton_congelado.is_set():
        return "El raton ya esta congelado en este momento."

    def _bucle():
        _raton_congelado.set()
        try:
            user32 = ctypes.windll.user32
            # Posicion actual del cursor: ahi es donde se queda clavado.
            punto = _PUNTO()
            user32.GetCursorPos(ctypes.byref(punto))
            x, y = punto.x, punto.y
            fin = time.monotonic() + segundos
            while time.monotonic() < fin:
                user32.SetCursorPos(x, y)
                time.sleep(0.01)
        finally:
            _raton_congelado.clear()

    threading.Thread(target=_bucle, daemon=True).start()
    return f"Raton congelado {segundos}s en su posicion (el teclado sigue activo)."


def _tipo_imagen(datos):
    """Reconoce el formato por sus primeros bytes. Devuelve la extension o None."""
    if datos.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if datos.startswith(b"BM"):
        return "bmp"
    return None


def accion_fondo_pantalla(imagen_b64):
    """Pone la imagen recibida (en base64) como fondo de escritorio.

    Guarda la imagen como BMP en ProgramData y la aplica con la API de Windows
    (SystemParametersInfo). Solo tiene efecto en Windows y en la sesion del
    usuario. Con Pillow la convierte a BMP; sin Pillow usa el JPG/PNG/BMP tal cual.
    """
    if not _es_windows():
        return "Simulado: cambiar fondo de pantalla (no es Windows)."
    import base64
    import io
    try:
        datos = base64.b64decode(imagen_b64, validate=True)
    except Exception:
        return "Imagen no valida."

    carpeta = os.path.join(
        os.environ.get("ProgramData", r"C:\ProgramData"), "ControlRemotoPC"
    )
    os.makedirs(carpeta, exist_ok=True)
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is not None:
        ruta = os.path.join(carpeta, "fondo.bmp")
        try:
            Image.open(io.BytesIO(datos)).convert("RGB").save(ruta, "BMP")
        except Exception as e:
            return f"No se pudo procesar la imagen: {e}"
    else:
        # Sin Pillow: Windows 8+ acepta JPG, PNG y BMP directamente como fondo.
        extension = _tipo_imagen(datos)
        if extension is None:
            return "Imagen no valida (usa JPG, PNG o BMP)."
        ruta = os.path.join(carpeta, "fondo." + extension)
        with open(ruta, "wb") as f:
            f.write(datos)

    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDWININICHANGE = 0x02
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, ctypes.c_wchar_p(ruta),
        SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
    )
    return "Fondo de pantalla cambiado." if ok else "Windows rechazo el cambio de fondo."


# ---------------------------------------------------------------------------
# Despacho de ordenes (lo usan tanto el servidor LAN como el modo rele)
# ---------------------------------------------------------------------------
def ejecutar_orden(mensaje, clave, margen):
    """Procesa un mensaje ya deserializado y devuelve (ok, texto, extra).

    'extra' es un dict con datos adicionales para la respuesta (o None).
    Comprueba la clave de forma independiente al transporte, asi que sirve
    igual por LAN que a traves del rele.
    """
    if mensaje.get("clave") != clave:
        return False, "Clave incorrecta.", None

    accion = mensaje.get("accion", "")
    if accion == "ping":
        return True, "Agente activo.", {"hostname": socket.gethostname()}
    if accion == "apagar":
        return True, accion_apagar(margen), None
    if accion == "reiniciar":
        return True, accion_reiniciar(margen), None
    if accion == "suspender":
        return True, accion_suspender(), None
    if accion == "cancelar":
        return True, accion_cancelar(), None
    if accion == "congelar_raton":
        return True, accion_congelar_raton(mensaje.get("segundos", 10)), None
    return False, f"Accion desconocida: {accion}", None


# ---------------------------------------------------------------------------
# Servidor de red
# ---------------------------------------------------------------------------
class ServidorAgente(threading.Thread):
    def __init__(self, puerto, clave, margen, log_callback):
        super().__init__(daemon=True)
        self.puerto = int(puerto)
        self.clave = clave
        self.margen = int(margen)
        self.log = log_callback
        self._parar = threading.Event()
        self._sock = None

    def run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("0.0.0.0", self.puerto))
            self._sock.listen(5)
            self._sock.settimeout(1.0)
            self.log(f"Escuchando en el puerto {self.puerto}. Agente ACTIVO.")
        except Exception as e:
            self.log(f"ERROR al iniciar el servidor: {e}")
            return

        while not self._parar.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._atender, args=(conn, addr), daemon=True
            ).start()

        if self._sock:
            self._sock.close()

    def parar(self):
        self._parar.set()

    def _atender(self, conn, addr):
        ip = addr[0]
        try:
            conn.settimeout(5.0)
            datos = conn.recv(4096).decode("utf-8").strip()
            if not datos:
                return
            try:
                mensaje = json.loads(datos)
            except json.JSONDecodeError:
                self._responder(conn, False, "Mensaje no valido.")
                return

            if mensaje.get("clave") != self.clave:
                self.log(f"[{ip}] Intento RECHAZADO (clave incorrecta).")
                self._responder(conn, False, "Clave incorrecta.")
                return

            accion = mensaje.get("accion", "")
            self.log(f"[{ip}] Orden recibida: {accion}")

            ok, texto, extra = ejecutar_orden(mensaje, self.clave, self.margen)
            self._responder(conn, ok, texto, extra=extra)
            if accion != "ping":
                self.log(texto)
        except Exception as e:
            self.log(f"[{ip}] Error atendiendo la conexion: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _responder(self, conn, ok, mensaje, extra=None):
        respuesta = {"ok": ok, "mensaje": mensaje}
        if extra:
            respuesta.update(extra)
        try:
            conn.sendall((json.dumps(respuesta) + "\n").encode("utf-8"))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Interfaz grafica
# ---------------------------------------------------------------------------
class VentanaAgente:
    def __init__(self, root):
        self.root = root
        self.cfg = cargar_config()

        root.title("Agente Remoto - ACTIVO")
        root.geometry("560x420")
        root.minsize(480, 360)

        cabecera = tk.Frame(root, bg="#1b5e20")
        cabecera.pack(fill="x")
        tk.Label(
            cabecera,
            text="  AGENTE REMOTO ACTIVO",
            bg="#1b5e20",
            fg="white",
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=10)

        info = tk.Frame(root)
        info.pack(fill="x", padx=12, pady=8)

        hostname = socket.gethostname()
        try:
            ip_local = socket.gethostbyname(hostname)
        except Exception:
            ip_local = "desconocida"

        tk.Label(info, text=f"Equipo: {hostname}", anchor="w").pack(fill="x")
        tk.Label(info, text=f"IP local: {ip_local}", anchor="w").pack(fill="x")
        tk.Label(
            info, text=f"Puerto: {self.cfg['puerto']}", anchor="w"
        ).pack(fill="x")
        tk.Label(
            info,
            text="Este equipo puede recibir ordenes de apagado/suspension/reinicio "
            "desde la Consola.",
            anchor="w",
            wraplength=520,
            justify="left",
            fg="#555555",
        ).pack(fill="x", pady=(4, 0))

        tk.Label(
            root, text="Registro de actividad:", anchor="w"
        ).pack(fill="x", padx=12)
        self.log_area = scrolledtext.ScrolledText(
            root, height=12, state="disabled", font=("Consolas", 9)
        )
        self.log_area.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Arrancar servidor
        self.servidor = ServidorAgente(
            puerto=self.cfg["puerto"],
            clave=self.cfg["clave"],
            margen=self.cfg["margen_segundos"],
            log_callback=self.log,
        )
        self.servidor.start()

        root.protocol("WM_DELETE_WINDOW", self.cerrar)

    def log(self, texto):
        marca = datetime.now().strftime("%H:%M:%S")
        linea = f"[{marca}] {texto}\n"

        def _escribir():
            self.log_area.configure(state="normal")
            self.log_area.insert("end", linea)
            self.log_area.see("end")
            self.log_area.configure(state="disabled")

        # Asegura que se escribe en el hilo de la interfaz
        self.root.after(0, _escribir)

    def cerrar(self):
        self.servidor.parar()
        self.root.destroy()


def main():
    root = tk.Tk()
    VentanaAgente(root)
    root.mainloop()


if __name__ == "__main__":
    main()
