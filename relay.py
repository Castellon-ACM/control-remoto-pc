"""
relay.py - Servidor RELE (rendezvous) para el control remoto.

Se despliega en una maquina con IP publica (un VPS, una cuenta cloud gratis,
o un equipo con un puerto abierto). Tanto el Agente como la Consola se conectan
HACIA AQUI (conexiones salientes), asi que atraviesan el router de casa sin
configurar nada. El rele solo hace de puente: empareja al agente y a la consola
que comparten la misma "sala" y reenvia los bytes de uno a otro.

No entiende el contenido (ordenes, respuestas o fotogramas): solo lo reenvia.
La clave se comprueba de extremo a extremo en el Agente, no aqui.

Uso:
    python relay.py              # escucha en el puerto 50510
    python relay.py 9000         # escucha en el puerto 9000
"""

import sys
import socket
import struct
import json
import threading

PUERTO = 50510

# sala -> {"agente": conn|None, "consola": conn|None}
_salas = {}
_lock = threading.Lock()


def _recibir_exacto(sock, n):
    trozos = bytearray()
    while len(trozos) < n:
        parte = sock.recv(n - len(trozos))
        if not parte:
            return None
        trozos.extend(parte)
    return bytes(trozos)


def _leer_registro(sock):
    """Lee el primer mensaje (registro): {"sala": "...", "rol": "..."}."""
    cabecera = _recibir_exacto(sock, 4)
    if cabecera is None:
        return None
    (longitud,) = struct.unpack(">I", cabecera)
    cuerpo = _recibir_exacto(sock, longitud)
    if cuerpo is None:
        return None
    return json.loads(cuerpo.decode("utf-8"))


def _enviar(sock, obj):
    datos = json.dumps(obj).encode("utf-8")
    sock.sendall(struct.pack(">I", len(datos)) + datos)


def _pump(origen, destino):
    """Reenvia bytes de 'origen' a 'destino' hasta que se cierre la conexion."""
    try:
        while True:
            datos = origen.recv(65536)
            if not datos:
                break
            destino.sendall(datos)
    except OSError:
        pass


def _sesion(agente, consola, sala):
    print(f"[sala {sala}] emparejados agente <-> consola")
    hilo = threading.Thread(target=_pump, args=(agente, consola), daemon=True)
    hilo.start()
    _pump(consola, agente)  # bloquea hasta que la consola cierre
    for s in (agente, consola):
        try:
            s.close()
        except OSError:
            pass
    print(f"[sala {sala}] sesion terminada")


def _manejar(conn, addr):
    reg = None
    try:
        reg = _leer_registro(conn)
    except Exception:
        pass
    if not reg or reg.get("rol") not in ("agente", "consola"):
        try:
            _enviar(conn, {"error": "registro no valido"})
            conn.close()
        except OSError:
            pass
        return

    sala = str(reg.get("sala", ""))
    rol = reg["rol"]
    pareja = None

    with _lock:
        s = _salas.setdefault(sala, {"agente": None, "consola": None})
        if s[rol] is not None:
            # Ya hay uno de ese rol en la sala: rechazamos al nuevo.
            try:
                _enviar(conn, {"error": f"ya hay un {rol} en la sala '{sala}'"})
                conn.close()
            except OSError:
                pass
            return
        s[rol] = conn
        otro = "consola" if rol == "agente" else "agente"
        if s[otro] is not None:
            pareja = (s["agente"], s["consola"])
            _salas.pop(sala, None)  # la pareja ya no espera a nadie

    print(f"[sala {sala}] conectado {rol} desde {addr[0]}")
    if pareja:
        _sesion(pareja[0], pareja[1], sala)
    # Si no hay pareja aun, este hilo termina; la conexion queda guardada y
    # viva, y sera el companero (cuando llegue) quien atienda ambos sockets.


def main():
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else PUERTO
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(("0.0.0.0", puerto))
    servidor.listen(16)
    print(f"Rele escuchando en el puerto {puerto}. Ctrl+C para salir.")
    try:
        while True:
            conn, addr = servidor.accept()
            threading.Thread(target=_manejar, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nRele detenido.")
    finally:
        servidor.close()


if __name__ == "__main__":
    main()
