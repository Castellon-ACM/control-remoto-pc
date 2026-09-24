"""
flota.py - Descubrimiento automatico de equipos (modo nube).

Idea: repartes UN mismo ejecutable. Cada PC, al abrirlo:
  - calcula SU PROPIA sala unica (a partir del nombre del equipo y su MAC),
  - anuncia su presencia periodicamente en un canal comun cifrado (una "baliza").

El monitor escucha ese canal comun y va DESCUBRIENDO los equipos solos, sin que
nadie configure salas a mano. Toda la seguridad es la de nube.py (cifrado y firma
con la clave compartida): el broker publico solo ve bytes aleatorios.
"""

import re
import time
import uuid
import socket
import threading

import nube

SALA_DESCUBRIMIENTO = "__descubrimiento__"
INTERVALO_BALIZA = 5.0


def sala_de_este_pc():
    """Sala unica y estable para este equipo (nombre + parte de la MAC)."""
    host = re.sub(r"[^a-zA-Z0-9_-]", "-", socket.gethostname()).lower()[:24] or "pc"
    sufijo = format(uuid.getnode() & 0xFFFFFF, "06x")
    return f"eq-{host}-{sufijo}"


class Baliza:
    """Publica la presencia del agente en el canal comun cada 'intervalo' s."""

    def __init__(self, broker, puerto, clave, sala, hostname=None, tls=True,
                 intervalo=INTERVALO_BALIZA):
        self.broker = broker
        self.puerto = int(puerto)
        self.clave = clave
        self.sala = sala
        self.hostname = hostname or socket.gethostname()
        self.tls = tls
        self.intervalo = intervalo
        self.canal = nube.Canal(SALA_DESCUBRIMIENTO, clave)
        self._parar = threading.Event()
        self._mqtt = None

    def run(self):
        while not self._parar.is_set():
            try:
                self._mqtt = nube.ClienteMQTT(self.broker, self.puerto, tls=self.tls)
                self._mqtt.conectar()
                while not self._parar.is_set():
                    sobre = self.canal.cerrar_sobre(nube.HACIA_CONSOLA, {
                        "tipo": "presencia", "sala": self.sala, "hostname": self.hostname,
                    })
                    self._mqtt.publicar(self.canal.topic_consola, sobre)
                    if self._parar.wait(self.intervalo):
                        break
            except Exception:
                if self._parar.wait(3):
                    break
            finally:
                if self._mqtt:
                    try:
                        self._mqtt.cerrar()
                    except Exception:
                        pass

    def parar(self):
        self._parar.set()
        if self._mqtt:
            try:
                self._mqtt.cerrar()
            except Exception:
                pass


class GestorFlota:
    """Descubre equipos por el canal comun y mantiene una consola por cada uno."""

    def __init__(self, broker, puerto, clave, tls=True, timeout=15.0):
        self.broker = broker
        self.puerto = int(puerto)
        self.clave = clave
        self.tls = tls
        self.timeout = timeout
        self.canal = nube.Canal(SALA_DESCUBRIMIENTO, clave)
        self._mqtt = None
        self._clientes = {}     # sala -> ClienteConsolaNube
        self._hostname = {}     # sala -> nombre del equipo
        self._ultimo = {}       # sala -> ultima baliza (ts)
        self._estado_actual = {}  # sala -> "conectado"/"desconectado"
        self._parar = threading.Event()
        self._lock = threading.Lock()
        # Callbacks (los pone la ventana): reciben (sala, dato).
        self.on_frame = None
        self.on_respuesta = None
        self.on_estado = None
        self.on_nuevo = None    # (sala, hostname) cuando se descubre uno nuevo

    def conectar(self):
        self._mqtt = nube.ClienteMQTT(self.broker, self.puerto, tls=self.tls,
                                      on_mensaje=self._on_baliza)
        self._mqtt.conectar()
        self._mqtt.suscribir(self.canal.topic_consola)
        threading.Thread(target=self._vigilar, daemon=True).start()

    def _on_baliza(self, topic, payload):
        if topic != self.canal.topic_consola:
            return
        msg = self.canal.abrir_sobre(nube.HACIA_CONSOLA, payload)
        if not msg or msg.get("tipo") != "presencia":
            return
        sala = msg.get("sala")
        if not sala:
            return
        self._ultimo[sala] = time.time()
        if sala not in self._clientes:
            self._anadir(sala, msg.get("hostname", sala))
        self._marcar(sala, "conectado")

    def _anadir(self, sala, hostname):
        from consola_nube import ClienteConsolaNube
        cli = ClienteConsolaNube(self.broker, self.puerto, sala, self.clave, tls=self.tls)
        cli.on_frame = lambda m, s=sala: self._reenviar(self.on_frame, s, m)
        cli.on_respuesta = lambda m, s=sala: self._reenviar(self.on_respuesta, s, m)
        cli.on_estado = lambda e, s=sala: None
        try:
            cli.conectar()
        except Exception:
            pass
        with self._lock:
            self._clientes[sala] = cli
            self._hostname[sala] = hostname
        if self.on_nuevo:
            self.on_nuevo(sala, hostname)

    def _vigilar(self):
        while not self._parar.wait(2):
            ahora = time.time()
            for sala, ts in list(self._ultimo.items()):
                self._marcar(sala, "conectado" if ahora - ts <= self.timeout else "desconectado")

    def _marcar(self, sala, estado):
        if self._estado_actual.get(sala) != estado:
            self._estado_actual[sala] = estado
            self._reenviar(self.on_estado, sala, estado)

    @staticmethod
    def _reenviar(cb, sala, dato):
        if cb:
            cb(sala, dato)

    def hostname(self, sala):
        return self._hostname.get(sala, sala)

    def salas(self):
        return list(self._clientes.keys())

    def _destinos(self, sala):
        if sala in (None, "Todos", "TODOS"):
            return list(self._clientes.values())
        c = self._clientes.get(sala)
        return [c] if c else []

    def enviar(self, sala, accion, extra=None):
        for c in self._destinos(sala):
            try:
                c.enviar_orden(accion, extra)
            except Exception:
                pass

    def fondo(self, sala, imagen_b64):
        for c in self._destinos(sala):
            try:
                c.enviar_fondo(imagen_b64)
            except Exception:
                pass

    def ver(self, sala, activar=True, fps=3, ancho=360):
        for c in self._destinos(sala):
            try:
                c.ver_pantalla(activar=activar, fps=fps, ancho=ancho)
            except Exception:
                pass

    def cerrar(self):
        self._parar.set()
        for c in list(self._clientes.values()):
            try:
                c.cerrar()
            except Exception:
                pass
        if self._mqtt:
            try:
                self._mqtt.cerrar()
            except Exception:
                pass
