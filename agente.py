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
import configparser
from datetime import datetime

import tkinter as tk
from tkinter import scrolledtext

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------
# La clave y el puerto se guardan en "config.ini" junto al programa.
# Si no existe, se crea con valores por defecto la primera vez.
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

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

            if accion == "ping":
                self._responder(
                    conn,
                    True,
                    "Agente activo.",
                    extra={"hostname": socket.gethostname()},
                )
            elif accion == "apagar":
                msg = accion_apagar(self.margen)
                self._responder(conn, True, msg)
                self.log(msg)
            elif accion == "reiniciar":
                msg = accion_reiniciar(self.margen)
                self._responder(conn, True, msg)
                self.log(msg)
            elif accion == "suspender":
                msg = accion_suspender()
                self._responder(conn, True, msg)
                self.log(msg)
            elif accion == "cancelar":
                msg = accion_cancelar()
                self._responder(conn, True, msg)
                self.log(msg)
            else:
                self._responder(conn, False, f"Accion desconocida: {accion}")
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
