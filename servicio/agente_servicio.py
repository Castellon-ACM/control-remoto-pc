"""
AGENTE REMOTO - Version SERVICIO de Windows (sin ventana)
=========================================================
Ejecuta el agente en SEGUNDO PLANO como un servicio de Windows real:
    - Arranca solo al encender el PC (antes de iniciar sesion).
    - No muestra ninguna ventana.
    - Se reinicia con el sistema.

Reutiliza EXACTAMENTE la misma logica de red (ServidorAgente) y el mismo
config.ini que agente.py, por lo que la Consola funciona sin cambios.

Requisitos:  pip install pywin32
Debe estar en la MISMA carpeta que agente.py.

Uso (como Administrador):
    python agente_servicio.py --startup auto install   # registrar (arranque automatico)
    python agente_servicio.py start                     # iniciar
    python agente_servicio.py stop                      # detener
    python agente_servicio.py remove                    # desinstalar
"""

import os
import sys

# Aseguramos que se puede importar agente.py aunque el servicio arranque
# desde otra carpeta de trabajo (el SCM no usa la carpeta del script).
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

import logging
from logging.handlers import RotatingFileHandler

import win32serviceutil
import win32service
import win32event
import servicemanager

# Logica ya existente del agente. Importar NO abre ninguna ventana:
# la interfaz de agente.py solo se lanza si se ejecuta directamente.
from agente import ServidorAgente, cargar_config


def _carpeta_logs():
    base = os.environ.get("ProgramData", r"C:\ProgramData")
    ruta = os.path.join(base, "ControlRemotoPC", "logs")
    os.makedirs(ruta, exist_ok=True)
    return ruta


class AgenteServicio(win32serviceutil.ServiceFramework):
    # Nombre interno (para sc.exe) y nombre visible en services.msc
    _svc_name_ = "ControlRemotoPC"
    _svc_display_name_ = "Control Remoto PC - Agente"
    _svc_description_ = (
        "Agente en segundo plano que permite apagar, suspender o reiniciar "
        "este equipo en remoto. Arranca automaticamente con el sistema."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.servidor = None
        self._configurar_log()

    def _configurar_log(self):
        self.logger = logging.getLogger("agente_servicio")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = RotatingFileHandler(
                os.path.join(_carpeta_logs(), "agente.log"),
                maxBytes=1_000_000, backupCount=3, encoding="utf-8",
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S")
            )
            self.logger.addHandler(handler)

    def log(self, texto):
        # Mismo "contrato" que el log_callback de la ventana, pero a fichero.
        self.logger.info(texto)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.log("Deteniendo el servicio...")
        if self.servidor:
            self.servidor.parar()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        try:
            cfg = cargar_config()
            self.servidor = ServidorAgente(
                puerto=cfg["puerto"],
                clave=cfg["clave"],
                margen=cfg["margen_segundos"],
                log_callback=self.log,
            )
            self.servidor.start()
            self.log("Servicio iniciado. Agente escuchando.")
            # Bloquea hasta que el SCM pida detener el servicio.
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        except Exception as e:
            self.log(f"ERROR en el servicio: {e}")
        self.log("Servicio detenido.")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Lo ha lanzado el Administrador de control de servicios de Windows.
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AgenteServicio)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Linea de comandos: install / start / stop / remove / update ...
        win32serviceutil.HandleCommandLine(AgenteServicio)
