"""
agente_relay.py - Agente en modo RELE (para funcionar entre ciudades).

Se conecta HACIA el rele (conexion saliente, atraviesa el router sin
configurar nada), se registra en una "sala" y atiende:
  - Las mismas ordenes que en LAN (apagar, suspender, reiniciar, cancelar,
    congelar raton), reutilizando agente.ejecutar_orden.
  - El streaming de pantalla en vivo (fotogramas JPEG en miniatura).

Debe correr en la SESION DEL USUARIO (no como servicio de la Sesion 0), porque
tanto compartir pantalla como congelar el raton actuan sobre el escritorio.

Config en config.ini (se crea/rellena solo): la clave va en [agente] y el rele
en [relay] (host, puerto, sala).

Uso:  python agente_relay.py
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
import remoto


def cargar_config_relay():
    """Lee (y crea si falta) la seccion [relay] de config.ini."""
    ruta = agente.CONFIG_FILE
    cfg = configparser.ConfigParser()
    if os.path.exists(ruta):
        cfg.read(ruta, encoding="utf-8")
    if "relay" not in cfg:
        cfg["relay"] = {}
    seccion = cfg["relay"]
    defaults = {
        "host": "CAMBIA-esto-por-la-ip-o-dominio-de-tu-rele",
        "puerto": str(remoto.PUERTO_RELE_POR_DEFECTO),
        "sala": "casa-2026",
    }
    cambios = False
    for k, v in defaults.items():
        if k not in seccion:
            seccion[k] = v
            cambios = True
    if cambios:
        with open(ruta, "w", encoding="utf-8") as f:
            cfg.write(f)
    return seccion


class AgenteRelay:
    def __init__(self, host, puerto, sala, clave, margen=15, log=print):
        self.host = host
        self.puerto = int(puerto)
        self.sala = sala
        self.clave = clave
        self.margen = int(margen)
        self.log = log
        self._sock = None
        self._enviar_lock = threading.Lock()
        self._streaming = False
        self._stream_cfg = {"fps": 5, "ancho": 480, "calidad": 40}
        self._parar = threading.Event()

    # -- envio con cerrojo (fotogramas y respuestas comparten socket) --------
    def _enviar(self, obj):
        with self._enviar_lock:
            remoto.enviar_mensaje(self._sock, obj)

    # -- bucle principal: se reconecta si se cae la sesion -------------------
    def run(self):
        while not self._parar.is_set():
            try:
                self._sesion()
            except Exception as e:
                self.log(f"Rele: sin conexion ({e}). Reintentando en 3 s...")
            self._streaming = False
            if self._parar.is_set():
                break
            time.sleep(3)

    def _sesion(self):
        self._sock = socket.create_connection((self.host, self.puerto), timeout=10)
        self._sock.settimeout(None)
        self._enviar({"sala": self.sala, "rol": "agente"})
        self.log(f"Conectado al rele ({self.host}:{self.puerto}), sala '{self.sala}'. "
                 f"Esperando a la consola...")
        while not self._parar.is_set():
            msg = remoto.recibir_mensaje(self._sock)
            if msg is None:
                break  # la consola cerro: se volvera a registrar
            self._procesar(msg)
        try:
            self._sock.close()
        except OSError:
            pass

    def _procesar(self, msg):
        # Toda peticion debe traer la clave correcta (seguridad extremo a extremo).
        if msg.get("clave") != self.clave:
            self._enviar({"tipo": "respuesta", "ok": False, "mensaje": "Clave incorrecta."})
            return

        if msg.get("tipo") == "ver":
            self._config_streaming(msg)
            return

        if msg.get("tipo") == "fondo":
            texto = agente.accion_fondo_pantalla(msg.get("imagen", ""))
            self._enviar({"tipo": "respuesta", "ok": True, "mensaje": texto})
            self.log(f"Fondo de pantalla -> {texto}")
            return

        # Por defecto es una orden (mismo formato que en LAN).
        ok, texto, extra = agente.ejecutar_orden(msg, self.clave, self.margen)
        respuesta = {"tipo": "respuesta", "ok": ok, "mensaje": texto}
        if extra:
            respuesta.update(extra)
        self._enviar(respuesta)
        self.log(f"Orden '{msg.get('accion')}' -> {texto}")

    def _config_streaming(self, msg):
        if msg.get("activar"):
            self._stream_cfg["fps"] = max(1, int(msg.get("fps", 5)))
            self._stream_cfg["ancho"] = int(msg.get("ancho", 480))
            if not self._streaming:
                self._streaming = True
                threading.Thread(target=self._bucle_stream, daemon=True).start()
                self.log("Compartiendo pantalla.")
        else:
            self._streaming = False
            self.log("Pantalla dejada de compartir.")

    def _bucle_stream(self):
        while self._streaming and not self._parar.is_set():
            try:
                frame = remoto.capturar_frame(
                    self._stream_cfg["ancho"], self._stream_cfg["calidad"]
                )
                self._enviar(frame)
            except Exception as e:
                self._enviar({
                    "tipo": "respuesta", "ok": False,
                    "mensaje": f"No se puede capturar la pantalla: {e}",
                })
                self._streaming = False
                break
            time.sleep(1.0 / self._stream_cfg["fps"])

    def parar(self):
        self._parar.set()
        try:
            self._sock.close()
        except OSError:
            pass


def main():
    ag = agente.cargar_config()          # [agente]: clave, margen...
    rl = cargar_config_relay()           # [relay]: host, puerto, sala
    cliente = AgenteRelay(
        host=rl["host"], puerto=rl["puerto"], sala=rl["sala"],
        clave=ag["clave"], margen=int(ag["margen_segundos"]),
    )
    print("Agente (modo rele) en marcha. Ctrl+C para salir.")
    try:
        cliente.run()
    except KeyboardInterrupt:
        cliente.parar()


if __name__ == "__main__":
    main()
