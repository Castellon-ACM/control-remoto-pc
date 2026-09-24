"""
consola_multi.py - Monitor de VARIOS equipos con lista persistente.

Caracteristicas:
  - Recuerda los equipos que has anadido (equipos_multi.json). Los que estan
    apagados NO desaparecen: se muestran como "desconectado".
  - Detecta en vivo quien esta encendido (latido/ping) y reconecta solo, asi
    que cuando un equipo se enciende pasa a "conectado" sin quitar a los demas.
  - Los conectados se muestran arriba; los desconectados debajo.
  - Puedes RENOMBRAR cada equipo desde el monitor (p. ej. "PC Casa",
    "PC empresa", "Ordenador Papa"). El nombre se guarda.
  - Seleccionas uno (o "Todos") y le mandas apagar / suspender / reiniciar /
    cancelar / congelar raton / poner fondo, y ves su pantalla en miniatura.

La identidad estable de cada equipo es su "sala" del rele; el "nombre" es solo
una etiqueta que puedes cambiar sin perder el equipo.
"""

import os
import json
import time
import threading

import remoto
from consola_relay import ClienteConsolaRelay

CONFIG_MULTI = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "equipos_multi.json"
)


# ---------------------------------------------------------------------------
# Persistencia de la lista de equipos
# ---------------------------------------------------------------------------
def cargar_equipos_multi(ruta=CONFIG_MULTI):
    if not os.path.exists(ruta):
        plantilla = {
            "host": "CAMBIA-esto-por-tu-rele",
            "puerto": remoto.PUERTO_RELE_POR_DEFECTO,
            "clave": "cambia-esta-clave-2026",
            "equipos": [
                {"nombre": "PC Casa", "sala": "pc1"},
                {"nombre": "PC Empresa", "sala": "pc2"},
                {"nombre": "Ordenador Papa", "sala": "pc3"},
                {"nombre": "PC-4", "sala": "pc4"},
            ],
        }
        guardar_equipos_multi(plantilla, ruta)
        return plantilla
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_equipos_multi(cfg, ruta=CONFIG_MULTI):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def renombrar_equipo(cfg, sala, nuevo_nombre, ruta=CONFIG_MULTI):
    """Cambia el nombre (etiqueta) del equipo con esa sala y lo guarda."""
    for eq in cfg["equipos"]:
        if eq["sala"] == sala:
            eq["nombre"] = nuevo_nombre
            break
    guardar_equipos_multi(cfg, ruta)
    return cfg


# ---------------------------------------------------------------------------
# Gestor de la flota (sin interfaz): conecta, detecta estado y reconecta
# ---------------------------------------------------------------------------
class GestorMulti:
    def __init__(self, host, puerto, clave, equipos, intervalo=2.0, timeout=6.0):
        """equipos: lista de {"sala": ..., "nombre": ..., "clave"?: ...}."""
        self.host = host
        self.puerto = int(puerto)
        self.clave = clave
        self.equipos = equipos
        self.intervalo = intervalo   # cada cuanto se manda el latido
        self.timeout = timeout       # sin pong este tiempo -> desconectado
        self._clientes = {}          # sala -> ClienteConsolaRelay | None
        self._conectado = {}         # sala -> bool (¿el equipo esta encendido?)
        self._ultimo_pong = {}       # sala -> timestamp
        self._parar = threading.Event()
        # Callbacks (los pone la ventana): reciben (sala, dato).
        self.on_frame = None
        self.on_respuesta = None
        self.on_estado = None

    def salas(self):
        return [eq["sala"] for eq in self.equipos]

    def conectar(self):
        for sala in self.salas():
            self._conectado[sala] = False
        threading.Thread(target=self._monitor, daemon=True).start()

    def _monitor(self):
        while not self._parar.is_set():
            for eq in list(self.equipos):
                sala = eq["sala"]
                cli = self._clientes.get(sala)
                if cli is None or not cli.vivo:
                    self._reconectar(eq)
                    cli = self._clientes.get(sala)
                if cli is not None and cli.vivo:
                    try:
                        cli.enviar_orden("ping")     # latido
                    except OSError:
                        pass
                if time.time() - self._ultimo_pong.get(sala, 0) > self.timeout:
                    self._marcar(sala, False)
            self._parar.wait(self.intervalo)

    def _reconectar(self, eq):
        sala = eq["sala"]
        viejo = self._clientes.get(sala)
        if viejo:
            try:
                viejo.cerrar()
            except OSError:
                pass
        cli = ClienteConsolaRelay(self.host, self.puerto, sala, eq.get("clave", self.clave))
        cli.on_frame = lambda msg, s=sala: self._reenviar(self.on_frame, s, msg)
        cli.on_respuesta = lambda msg, s=sala: self._al_recibir(s, msg)
        cli.on_estado = lambda estado, s=sala: self._al_estado(s, estado)
        try:
            cli.conectar()
            self._clientes[sala] = cli
        except OSError:
            self._clientes[sala] = None
            self._marcar(sala, False)

    def _al_recibir(self, sala, msg):
        # El pong del latido marca "conectado" y NO se muestra al usuario.
        if msg.get("ok") and "activo" in str(msg.get("mensaje", "")).lower():
            self._ultimo_pong[sala] = time.time()
            self._marcar(sala, True)
            return
        self._reenviar(self.on_respuesta, sala, msg)

    def _al_estado(self, sala, estado):
        if estado != "conectado":
            self._marcar(sala, False)

    def _marcar(self, sala, conectado):
        if self._conectado.get(sala) != conectado:
            self._conectado[sala] = conectado
            self._reenviar(self.on_estado, sala, "conectado" if conectado else "desconectado")

    @staticmethod
    def _reenviar(cb, sala, dato):
        if cb:
            cb(sala, dato)

    def conectados(self):
        return {s: self._conectado.get(s, False) for s in self.salas()}

    def _destinos(self, sala):
        if sala in (None, "Todos", "TODOS"):
            return [c for c in self._clientes.values() if c and c.vivo]
        c = self._clientes.get(sala)
        return [c] if (c and c.vivo) else []

    def enviar(self, sala, accion, extra=None):
        for c in self._destinos(sala):
            try:
                c.enviar_orden(accion, extra)
            except OSError:
                pass

    def fondo(self, sala, imagen_b64):
        for c in self._destinos(sala):
            try:
                c.enviar_fondo(imagen_b64)
            except OSError:
                pass

    def ver(self, sala, activar=True, fps=5, ancho=360):
        for c in self._destinos(sala):
            try:
                c.ver_pantalla(activar=activar, fps=fps, ancho=ancho)
            except OSError:
                pass

    def cerrar(self):
        self._parar.set()
        for c in list(self._clientes.values()):
            if c:
                try:
                    c.cerrar()
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Ventana: rejilla con estado, orden (conectados arriba) y renombrado
# ---------------------------------------------------------------------------
def _lanzar_ventana():
    import io
    import tkinter as tk
    from tkinter import messagebox, filedialog, simpledialog
    from PIL import Image, ImageTk

    ANCHO_MINIATURA = 320

    class VentanaMulti:
        def __init__(self, root, cfg):
            self.root = root
            self.cfg = cfg
            self._imgtk = {}
            self.celdas = {}     # sala -> frame de la celda
            self.lbl_img = {}    # sala -> label de imagen
            self.lbl_nom = {}    # sala -> label del nombre
            self.lbl_est = {}    # sala -> label de estado
            self.estado = {}     # sala -> "conectado"/"desconectado"
            self.seleccion = tk.StringVar(value="Todos")

            root.title("Monitor multi-equipo")

            barra = tk.Frame(root, bg="#0d47a1")
            barra.pack(fill="x")
            tk.Label(barra, text="  MONITOR MULTI-EQUIPO", bg="#0d47a1", fg="white",
                     font=("Segoe UI", 14, "bold")).pack(side="left", padx=8, pady=8)
            tk.Button(barra, text="Ver todas",
                      command=lambda: self.gestor.ver("Todos", True, 5, ANCHO_MINIATURA)).pack(side="right", padx=8)

            self.rejilla = tk.Frame(root)
            self.rejilla.pack(padx=8, pady=8)
            for eq in cfg["equipos"]:
                self._crear_celda(eq)

            acc = tk.Frame(root)
            acc.pack(fill="x", padx=8, pady=(0, 6))
            tk.Radiobutton(acc, text="Todos", variable=self.seleccion, value="Todos").pack(side="left")
            tk.Button(acc, text="Apagar", bg="#c62828", fg="white",
                      command=lambda: self._orden("apagar")).pack(side="left", padx=2)
            tk.Button(acc, text="Suspender", command=lambda: self._orden("suspender")).pack(side="left", padx=2)
            tk.Button(acc, text="Reiniciar", command=lambda: self._orden("reiniciar")).pack(side="left", padx=2)
            tk.Button(acc, text="Cancelar", command=lambda: self._orden("cancelar")).pack(side="left", padx=2)

            acc2 = tk.Frame(root)
            acc2.pack(fill="x", padx=8, pady=(0, 8))
            tk.Label(acc2, text="Segundos:").pack(side="left")
            self.e_seg = tk.Entry(acc2, width=5)
            self.e_seg.insert(0, "20")
            self.e_seg.pack(side="left", padx=4)
            tk.Button(acc2, text="Congelar raton", bg="#4527a0", fg="white",
                      command=self._congelar).pack(side="left", padx=2)
            tk.Button(acc2, text="Poner fondo...", bg="#00695c", fg="white",
                      command=self._fondo).pack(side="left", padx=6)

            self.gestor = GestorMulti(cfg["host"], cfg["puerto"], cfg.get("clave", ""), cfg["equipos"])
            self.gestor.on_frame = self._frame
            self.gestor.on_respuesta = self._respuesta
            self.gestor.on_estado = self._estado
            self.gestor.conectar()
            self._reordenar()

            root.protocol("WM_DELETE_WINDOW", self._cerrar)

        def _nombre(self, sala):
            for eq in self.cfg["equipos"]:
                if eq["sala"] == sala:
                    return eq["nombre"]
            return sala

        def _crear_celda(self, eq):
            sala = eq["sala"]
            celda = tk.Frame(self.rejilla, bd=2, relief="groove")
            cab = tk.Frame(celda)
            cab.pack(fill="x")
            tk.Radiobutton(cab, variable=self.seleccion, value=sala).pack(side="left")
            self.lbl_nom[sala] = tk.Label(cab, text=eq["nombre"], font=("Segoe UI", 10, "bold"))
            self.lbl_nom[sala].pack(side="left")
            tk.Button(cab, text="Renombrar", command=lambda s=sala: self._renombrar(s)).pack(side="left", padx=4)
            self.lbl_est[sala] = tk.Label(cab, text="...", fg="#b71c1c")
            self.lbl_est[sala].pack(side="right")
            img = tk.Label(celda, text="(desconectado)", bg="#111111", fg="#888888",
                           width=ANCHO_MINIATURA, height=int(ANCHO_MINIATURA * 9 / 16))
            img.pack()
            self.celdas[sala] = celda
            self.lbl_img[sala] = img
            self.estado.setdefault(sala, "desconectado")

        def _reordenar(self):
            """Coloca primero los conectados, luego los desconectados; nadie se quita."""
            salas = self.gestor.salas()
            salas.sort(key=lambda s: (self.estado.get(s) != "conectado", self._nombre(s).lower()))
            for i, sala in enumerate(salas):
                self.celdas[sala].grid(row=i // 2, column=i % 2, padx=6, pady=6)

        def _renombrar(self, sala):
            actual = self._nombre(sala)
            nuevo = simpledialog.askstring("Renombrar equipo",
                                           "Nuevo nombre:", initialvalue=actual, parent=self.root)
            if nuevo and nuevo.strip():
                renombrar_equipo(self.cfg, sala, nuevo.strip())
                self.lbl_nom[sala].configure(text=nuevo.strip())
                self._reordenar()

        def _orden(self, accion):
            destino = self.seleccion.get()
            if accion in ("apagar", "reiniciar", "suspender"):
                if not messagebox.askyesno("Confirmar", f"¿'{accion}' a: {destino}?"):
                    return
            self.gestor.enviar(destino, accion)

        def _congelar(self):
            t = self.e_seg.get().strip()
            if not t.isdigit() or int(t) <= 0:
                messagebox.showwarning("Dato no valido", "Segundos > 0.")
                return
            self.gestor.enviar(self.seleccion.get(), "congelar_raton", {"segundos": int(t)})

        def _fondo(self):
            ruta = filedialog.askopenfilename(
                title="Imagen de fondo",
                filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Todos", "*.*")])
            if not ruta:
                return
            self.gestor.fondo(self.seleccion.get(), remoto.leer_imagen_base64(ruta))

        def _frame(self, sala, msg):
            jpeg = remoto.decodificar_frame(msg)

            def _ui():
                img = Image.open(io.BytesIO(jpeg))
                self._imgtk[sala] = ImageTk.PhotoImage(img)
                self.lbl_img[sala].configure(image=self._imgtk[sala], text="")
            self.root.after(0, _ui)

        def _respuesta(self, sala, msg):
            texto = f"[{self._nombre(sala)}] {msg.get('mensaje', '')}"
            self.root.after(0, lambda: messagebox.showinfo("Respuesta", texto))

        def _estado(self, sala, estado):
            def _ui():
                self.estado[sala] = estado
                conectado = estado == "conectado"
                self.lbl_est[sala].configure(text="ENCENDIDO" if conectado else "desconectado",
                                             fg="#1b5e20" if conectado else "#b71c1c")
                if not conectado:
                    self.lbl_img[sala].configure(image="", text="(desconectado)")
                    self._imgtk.pop(sala, None)
                self._reordenar()
            self.root.after(0, _ui)

        def _cerrar(self):
            self.gestor.cerrar()
            self.root.destroy()

    cfg = cargar_equipos_multi()
    root = tk.Tk()
    VentanaMulti(root, cfg)
    root.mainloop()


def main():
    _lanzar_ventana()


if __name__ == "__main__":
    main()
