"""
consola_nube.py - Consola en modo NUBE (entre ciudades, sin rele ni VPN).

Se conecta al mismo broker MQTT publico que el agente y, con la misma sala y
clave, permite enviar ordenes y ver la pantalla en vivo. Todo cifrado y
firmado extremo a extremo (ver nube.py). No necesita instalar nada.

La parte de red esta en ClienteConsolaNube (sin interfaz, facil de testear);
la ventana es la misma que la del modo rele (consola_relay._lanzar_ventana).

Uso:  python consola_nube.py
"""

import os
import sys
import time
import threading

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

import nube


class ClienteConsolaNube:
    """Mismo interfaz que ClienteConsolaRelay: conectar, enviar_orden,
    ver_pantalla, cerrar y callbacks on_frame / on_respuesta / on_estado."""

    ACEPTA_FORMATOS = True
    RENOVAR_VISOR_SEG = 8

    def __init__(self, host, puerto, sala, clave, tls=True):
        error = nube.validar_clave(clave)
        if error:
            raise ValueError(error)
        if not sala:
            raise ValueError("Pon el nombre de la sala (el mismo que en el agente).")
        self.host = host or nube.BROKER_POR_DEFECTO
        self.puerto = int(puerto or nube.PUERTO_POR_DEFECTO)
        self.sala = sala
        self.tls = tls
        self.canal = nube.Canal(sala, clave)
        self._mqtt = None
        self._visor = None       # parametros del visor mientras este activo
        self._parar = threading.Event()
        self.on_frame = None
        self.on_respuesta = None
        self.on_estado = None

    def _estado(self, e):
        if self.on_estado:
            self.on_estado(e)

    def conectar(self):
        self._mqtt = nube.ClienteMQTT(self.host, self.puerto, tls=self.tls,
                                      on_mensaje=self._on_mensaje,
                                      on_caida=lambda: self._estado("desconectado"))
        self._mqtt.conectar()
        self._mqtt.suscribir(self.canal.topic_consola)
        self._parar.clear()
        self._estado("esperando")
        threading.Thread(target=self._bucle_presencia, daemon=True).start()

    def _bucle_presencia(self):
        """Pregunta periodicamente si el equipo esta en linea y renueva el visor."""
        ultimo_ping = 0.0
        while not self._parar.is_set() and self._mqtt and self._mqtt.conectado:
            ahora = time.time()
            try:
                if ahora - ultimo_ping > 30:
                    ultimo_ping = ahora
                    self._enviar({"accion": "ping", "id": "auto"})
                if self._visor:
                    self._enviar(dict(self._visor))
            except OSError:
                break
            self._parar.wait(self.RENOVAR_VISOR_SEG)

    def _enviar(self, obj):
        self._mqtt.publicar(self.canal.topic_agente,
                            self.canal.cerrar_sobre(nube.HACIA_AGENTE, obj))

    def _on_mensaje(self, topic, payload):
        if topic != self.canal.topic_consola:
            return
        msg = self.canal.abrir_sobre(nube.HACIA_CONSOLA, payload)
        if msg is None:
            return
        tipo = msg.get("tipo")
        if tipo == "frame":
            if self.on_frame:
                self.on_frame(msg)
        elif tipo == "hola" or (tipo == "respuesta" and msg.get("id") == "auto"):
            self._estado("en_linea:" + str(msg.get("hostname", "")))
            if tipo == "hola" and self._visor:
                self._enviar(dict(self._visor))   # el agente se reinicio: reanudar visor
        elif self.on_respuesta:
            self.on_respuesta(msg)

    def enviar_orden(self, accion, extra=None):
        obj = {"accion": accion, "id": os.urandom(4).hex()}
        if extra:
            obj.update(extra)
        self._enviar(obj)

    def enviar_fondo(self, imagen_b64):
        """Envia una imagen (base64) para ponerla de fondo en el equipo remoto.

        El broker publico limita el tamano de cada mensaje, asi que la imagen
        se parte en trozos cifrados que el agente vuelve a juntar."""
        if len(imagen_b64) * 3 // 4 > nube.MAX_BYTES_ARCHIVO:
            raise ValueError("La imagen es demasiado grande (maximo 15 MB).")
        ident = os.urandom(4).hex()
        trozos = [imagen_b64[i:i + nube.TAM_TROZO]
                  for i in range(0, len(imagen_b64), nube.TAM_TROZO)] or [""]
        for i, datos in enumerate(trozos):
            self._enviar({"tipo": "fondo_parte", "id": ident, "i": i,
                          "n": len(trozos), "datos": datos})
            time.sleep(0.05)   # no saturar el broker
        return ident

    def ver_pantalla(self, activar=True, fps=3, ancho=480, formatos=("png",)):
        if activar:
            self._visor = {"tipo": "ver", "activar": True, "fps": min(int(fps), 4),
                           "ancho": int(ancho), "formatos": list(formatos)}
            self._enviar(dict(self._visor))
        else:
            self._visor = None
            self._enviar({"tipo": "ver", "activar": False})

    def cerrar(self):
        self._parar.set()
        if self._mqtt:
            try:
                if self._visor:
                    self._enviar({"tipo": "ver", "activar": False})
            except OSError:
                pass
            self._mqtt.cerrar()


def main():
    import consola_relay
    consola_relay._lanzar_ventana(
        cliente_cls=ClienteConsolaNube,
        titulo="Consola Remota (modo nube) + Visor",
        cabecera="  CONSOLA REMOTA - modo nube",
        etiqueta_host="Broker:",
        host=nube.BROKER_POR_DEFECTO,
        puerto=nube.PUERTO_POR_DEFECTO,
        sala="",
        color="#1b5e20",
    )


if __name__ == "__main__":
    main()
