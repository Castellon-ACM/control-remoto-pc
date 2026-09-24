"""
agente_nube.py - Agente en modo NUBE (entre ciudades, sin rele ni VPN).

Se conecta (conexion saliente) a un broker MQTT publico y gratuito y atiende:
  - Las mismas ordenes que en LAN (apagar, suspender, reiniciar, cancelar,
    congelar raton, ping), reutilizando agente.ejecutar_orden.
  - El visor de pantalla en vivo (miniaturas PNG/JPEG).

No necesita instalar nada: solo Python (o el .exe que genera GitHub Actions).
Debe correr en la SESION DEL USUARIO (no como servicio), porque el visor y
congelar el raton actuan sobre el escritorio.

Config en config.ini: la clave en [agente]; broker, puerto y sala en [nube].
La ventana permite cambiar sala y clave sin tocar el archivo.

Uso:
    python agente_nube.py            # con ventana de estado
    python agente_nube.py --oculto   # sin ventana (arranque automatico)
    python agente_nube.py --configurar SALA CLAVE   # guarda sala y clave
"""

import os
import sys
import time
import socket
import threading
import configparser

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

import agente
import nube


def cargar_config_nube():
    """Lee (y crea si falta) la seccion [nube] de config.ini."""
    ruta = agente.CONFIG_FILE
    cfg = configparser.ConfigParser()
    if os.path.exists(ruta):
        cfg.read(ruta, encoding="utf-8")
    if "nube" not in cfg:
        cfg["nube"] = {}
    seccion = cfg["nube"]
    defaults = {
        "broker": nube.BROKER_POR_DEFECTO,
        "puerto": str(nube.PUERTO_POR_DEFECTO),
        "sala": "casa-" + socket.gethostname().lower(),
    }
    cambios = False
    for k, v in defaults.items():
        if k not in seccion:
            seccion[k] = v
            cambios = True
    if cambios:
        with open(ruta, "w", encoding="utf-8") as f:
            cfg.write(f)
    return dict(seccion)


def guardar_sala_y_clave(sala, clave):
    ruta = agente.CONFIG_FILE
    cfg = configparser.ConfigParser()
    if os.path.exists(ruta):
        cfg.read(ruta, encoding="utf-8")
    for s in ("agente", "nube"):
        if s not in cfg:
            cfg[s] = {}
    cfg["agente"]["clave"] = clave
    cfg["nube"]["sala"] = sala
    with open(ruta, "w", encoding="utf-8") as f:
        cfg.write(f)


class AgenteNube:
    RENOVAR_VISOR_SEG = 20   # si la consola no renueva "ver" en este tiempo, se corta

    def __init__(self, broker, puerto, sala, clave, margen=15, log=print,
                 tls=True, capturar=None):
        self.broker = broker
        self.puerto = int(puerto)
        self.sala = sala
        self.clave = clave
        self.margen = int(margen)
        self.log = log
        self.tls = tls
        self._capturar = capturar or nube.capturar_frame
        self.canal = nube.Canal(sala, clave)
        self._mqtt = None
        self._parar = threading.Event()
        self._caido = threading.Event()
        self._visor = {"hasta": 0.0, "fps": 3, "ancho": 480, "formatos": ["png"]}
        self._visor_activo = False
        self._lock_visor = threading.Lock()

    # -- bucle principal (se reconecta solo) --------------------------------
    def run(self):
        error = nube.validar_clave(self.clave)
        if error:
            self.log("NO arranca: " + error)
            return
        espera = 3
        while not self._parar.is_set():
            try:
                self._conectar()
                espera = 3
                self.log(f"Conectado a {self.broker}. Sala '{self.sala}'. "
                         f"Esperando a la consola...")
                while not self._parar.is_set() and not self._caido.is_set():
                    self._caido.wait(1)
                if not self._parar.is_set():
                    self.log("Conexion perdida con el broker.")
            except Exception as e:
                self.log(f"Sin conexion con {self.broker} ({e}). Reintento en {espera} s...")
            if self._mqtt:
                self._mqtt.cerrar()
            if self._parar.wait(espera):
                break
            espera = min(espera * 2, 60)

    def _conectar(self):
        self._caido.clear()
        self._mqtt = nube.ClienteMQTT(self.broker, self.puerto, tls=self.tls,
                                      on_mensaje=self._on_mensaje,
                                      on_caida=self._caido.set)
        self._mqtt.conectar()
        self._mqtt.suscribir(self.canal.topic_agente)
        self._responder({"tipo": "hola", "hostname": socket.gethostname()})

    def parar(self):
        self._parar.set()
        self._visor["hasta"] = 0
        if self._mqtt:
            self._mqtt.cerrar()

    # -- mensajes -----------------------------------------------------------
    def _responder(self, obj):
        self._mqtt.publicar(self.canal.topic_consola,
                            self.canal.cerrar_sobre(nube.HACIA_CONSOLA, obj))

    def _on_mensaje(self, topic, payload):
        if topic != self.canal.topic_agente:
            return
        msg = self.canal.abrir_sobre(nube.HACIA_AGENTE, payload)
        if msg is None:
            return  # sin firma valida (otra clave, basura o repetido): se ignora
        if msg.get("tipo") == "ver":
            self._config_visor(msg)
            return
        # Las ordenes se ejecutan en otro hilo para no bloquear la lectura.
        threading.Thread(target=self._orden, args=(msg,), daemon=True).start()

    def _orden(self, msg):
        msg["clave"] = self.clave   # ya autenticado por la firma del sobre
        ok, texto, extra = agente.ejecutar_orden(msg, self.clave, self.margen)
        respuesta = {"tipo": "respuesta", "ok": ok, "mensaje": texto,
                     "id": msg.get("id"), "accion": msg.get("accion")}
        if extra:
            respuesta.update(extra)
        try:
            self._responder(respuesta)
        except OSError:
            pass
        if msg.get("accion") != "ping":
            self.log(f"Orden '{msg.get('accion')}' -> {texto}")

    # -- visor --------------------------------------------------------------
    def _config_visor(self, msg):
        with self._lock_visor:
            if not msg.get("activar"):
                if self._visor["hasta"]:
                    self.log("Pantalla dejada de compartir.")
                self._visor["hasta"] = 0
                return
            self._visor["hasta"] = time.time() + self.RENOVAR_VISOR_SEG
            self._visor["fps"] = min(10, max(1, int(msg.get("fps", 3))))
            self._visor["ancho"] = min(1280, max(160, int(msg.get("ancho", 480))))
            self._visor["formatos"] = list(msg.get("formatos") or ["png"])
            if not self._visor_activo:
                self._visor_activo = True
                self.log("Compartiendo pantalla con la consola.")
                threading.Thread(target=self._bucle_visor, daemon=True).start()

    def _bucle_visor(self):
        ancho = self._visor["ancho"]
        try:
            while time.time() < self._visor["hasta"] and not self._parar.is_set():
                inicio = time.time()
                ancho = min(ancho, self._visor["ancho"])
                try:
                    frame = self._capturar(ancho, self._visor["formatos"])
                except Exception as e:
                    self._responder({"tipo": "respuesta", "ok": False,
                                     "mensaje": f"No se puede capturar la pantalla: {e}"})
                    break
                sobre = self.canal.cerrar_sobre(nube.HACIA_CONSOLA, frame)
                if len(sobre) > nube.MAX_BYTES_FRAME and ancho > 200:
                    ancho = int(ancho * 0.8)   # demasiado grande: la siguiente, mas pequena
                    continue
                try:
                    self._mqtt.publicar(self.canal.topic_consola, sobre)
                except (OSError, AttributeError):
                    break
                resto = 1.0 / self._visor["fps"] - (time.time() - inicio)
                if resto > 0:
                    time.sleep(resto)
        finally:
            with self._lock_visor:
                self._visor_activo = False
                if self._visor["hasta"] and time.time() >= self._visor["hasta"]:
                    self.log("Visor detenido (la consola dejo de pedirlo).")


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------
def _crear_agente(log):
    ag = agente.cargar_config()
    nb = cargar_config_nube()
    return AgenteNube(broker=nb["broker"], puerto=nb["puerto"], sala=nb["sala"],
                      clave=ag["clave"], margen=int(ag.get("margen_segundos", 15)), log=log)


def _ventana():
    import tkinter as tk
    from tkinter import scrolledtext, messagebox
    from datetime import datetime

    root = tk.Tk()
    root.title("Agente remoto (modo nube)")
    root.geometry("520x380")
    cab = tk.Frame(root, bg="#1b5e20")
    cab.pack(fill="x")
    tk.Label(cab, text="  AGENTE REMOTO - modo nube", bg="#1b5e20", fg="white",
             font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", padx=8, pady=8)

    form = tk.Frame(root)
    form.pack(fill="x", padx=12, pady=6)
    ag, nb = agente.cargar_config(), cargar_config_nube()
    tk.Label(form, text="Sala:").grid(row=0, column=0, sticky="e")
    e_sala = tk.Entry(form, width=30)
    e_sala.insert(0, nb["sala"])
    e_sala.grid(row=0, column=1, sticky="w", padx=6, pady=2)
    tk.Label(form, text="Clave:").grid(row=1, column=0, sticky="e")
    e_clave = tk.Entry(form, width=30, show="*")
    e_clave.insert(0, ag["clave"])
    e_clave.grid(row=1, column=1, sticky="w", padx=6, pady=2)

    log_box = scrolledtext.ScrolledText(root, height=12, state="disabled", font=("Consolas", 9))
    log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def log(texto):
        linea = f"[{datetime.now().strftime('%H:%M:%S')}] {texto}\n"

        def _w():
            log_box.configure(state="normal")
            log_box.insert("end", linea)
            log_box.see("end")
            log_box.configure(state="disabled")
        root.after(0, _w)

    estado = {"agente": None}

    def arrancar():
        if estado["agente"]:
            estado["agente"].parar()
        a = _crear_agente(log)
        estado["agente"] = a
        threading.Thread(target=a.run, daemon=True).start()

    def guardar():
        sala, clave = e_sala.get().strip(), e_clave.get()
        error = nube.validar_clave(clave)
        if not sala or error:
            messagebox.showwarning("Datos no validos", error or "Pon una sala.")
            return
        guardar_sala_y_clave(sala, clave)
        log("Configuracion guardada. Reconectando...")
        arrancar()

    tk.Button(form, text="Guardar y conectar", command=guardar).grid(
        row=0, column=2, rowspan=2, padx=8)

    def cerrar():
        if estado["agente"]:
            estado["agente"].parar()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", cerrar)
    arrancar()
    root.mainloop()


def configurar(sala, clave):
    """Guarda sala y clave (lo usa el instalador). Devuelve 0 si todo va bien."""
    error = nube.validar_clave(clave) or ("" if sala.strip() else "Falta la sala.")
    if error:
        print(error)
        return 1
    agente.cargar_config()
    cargar_config_nube()
    guardar_sala_y_clave(sala.strip(), clave)
    print(f"Guardado en {agente.CONFIG_FILE}")
    return 0


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--configurar":
        sys.exit(configurar(sys.argv[2], sys.argv[3]))
    if "--oculto" in sys.argv:
        a = _crear_agente(print)
        try:
            a.run()
        except KeyboardInterrupt:
            a.parar()
    else:
        _ventana()


if __name__ == "__main__":
    main()
