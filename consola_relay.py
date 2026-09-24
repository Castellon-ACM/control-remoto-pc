"""
consola_relay.py - Consola (monitor) en modo RELE, con visor de pantalla.

Se conecta HACIA el rele, se empareja con el Agente de la misma sala y permite:
  - Enviar las ordenes (apagar, suspender, reiniciar, cancelar, congelar raton).
  - Ver la pantalla del equipo remoto EN VIVO en una miniatura.

La parte de red esta en ClienteConsolaRelay (sin interfaz, facil de testear);
la ventana la dibuja VentanaConsolaRelay.

Uso:  python consola_relay.py
El visor requiere Pillow (pip install pillow).
"""

import io
import socket
import threading

import remoto


# ---------------------------------------------------------------------------
# Cliente de red (sin interfaz): se puede usar y testear por si solo
# ---------------------------------------------------------------------------
class ClienteConsolaRelay:
    def __init__(self, host, puerto, sala, clave):
        self.host = host
        self.puerto = int(puerto)
        self.sala = sala
        self.clave = clave
        self._sock = None
        self._enviar_lock = threading.Lock()
        self._parar = threading.Event()
        self.vivo = False          # True mientras el socket con el rele este abierto
        # Callbacks (los pone la ventana): reciben un dict de mensaje.
        self.on_frame = None       # fotograma de pantalla
        self.on_respuesta = None   # respuesta a una orden
        self.on_estado = None      # cambios de estado ("conectado"/"desconectado")

    def conectar(self):
        self._sock = socket.create_connection((self.host, self.puerto), timeout=10)
        self._sock.settimeout(None)
        remoto.enviar_mensaje(self._sock, {"sala": self.sala, "rol": "consola"})
        self._parar.clear()
        self.vivo = True
        threading.Thread(target=self._bucle_recibir, daemon=True).start()
        if self.on_estado:
            self.on_estado("conectado")

    def _bucle_recibir(self):
        while not self._parar.is_set():
            try:
                msg = remoto.recibir_mensaje(self._sock)
            except OSError:
                msg = None
            if msg is None:
                self.vivo = False
                if self.on_estado:
                    self.on_estado("desconectado")
                break
            if msg.get("error"):
                if self.on_respuesta:
                    self.on_respuesta({"ok": False, "mensaje": msg["error"]})
                continue
            if msg.get("tipo") == "frame":
                if self.on_frame:
                    self.on_frame(msg)
            else:
                if self.on_respuesta:
                    self.on_respuesta(msg)

    def enviar_orden(self, accion, extra=None):
        obj = {"clave": self.clave, "accion": accion}
        if extra:
            obj.update(extra)
        with self._enviar_lock:
            remoto.enviar_mensaje(self._sock, obj)

    def ver_pantalla(self, activar=True, fps=5, ancho=480):
        with self._enviar_lock:
            remoto.enviar_mensaje(self._sock, {
                "tipo": "ver", "clave": self.clave,
                "activar": bool(activar), "fps": int(fps), "ancho": int(ancho),
            })

    def enviar_fondo(self, imagen_b64):
        """Envia una imagen (base64) para ponerla de fondo en el equipo remoto."""
        with self._enviar_lock:
            remoto.enviar_mensaje(self._sock, {
                "tipo": "fondo", "clave": self.clave, "imagen": imagen_b64,
            })

    def cerrar(self):
        self._parar.set()
        self.vivo = False
        try:
            self._sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Ventana (interfaz grafica)
# ---------------------------------------------------------------------------
def _lanzar_ventana(cliente_cls=None, titulo="Consola Remota (rele) + Visor",
                    cabecera="  CONSOLA REMOTA (rele)", etiqueta_host="Rele (host):",
                    host="mi-rele.ejemplo.com", puerto=None, sala="casa-2026",
                    color="#0d47a1"):
    """Dibuja la consola. La usan el modo rele y el modo nube (consola_nube.py):
    solo cambia la clase de cliente de red y los valores por defecto."""
    import base64
    import tkinter as tk
    from tkinter import messagebox
    try:
        from PIL import Image, ImageTk   # opcional: sin Pillow se muestran PNG con Tk
    except ImportError:
        Image = ImageTk = None

    cliente_cls = cliente_cls or ClienteConsolaRelay
    if puerto is None:
        puerto = remoto.PUERTO_RELE_POR_DEFECTO

    ANCHO_MINIATURA = 480  # px de la vista en miniatura

    class VentanaConsolaRelay:
        def __init__(self, root):
            self.root = root
            self.cliente = None
            self._imgtk = None  # referencia viva para que Tk no la borre

            root.title(titulo)
            root.geometry("560x640")

            cab = tk.Frame(root, bg=color)
            cab.pack(fill="x")
            tk.Label(cab, text=cabecera, bg=color, fg="white",
                     font=("Segoe UI", 14, "bold"), anchor="w").pack(fill="x", padx=8, pady=10)

            # Datos de conexion
            form = tk.Frame(root)
            form.pack(fill="x", padx=12, pady=8)
            self.e_host = self._campo(form, etiqueta_host, 0, host)
            self.e_puerto = self._campo(form, "Puerto:", 1, str(puerto))
            self.e_sala = self._campo(form, "Sala:", 2, sala)
            self.e_clave = self._campo(form, "Clave:", 3, "cambia-esta-clave-2026", oculto=True)
            self.b_conectar = tk.Button(form, text="Conectar", command=self.conectar)
            self.b_conectar.grid(row=4, column=1, sticky="w", pady=6)
            self.lbl_estado = tk.Label(form, text="Desconectado", fg="#b71c1c")
            self.lbl_estado.grid(row=4, column=1, sticky="e")

            # Botones de accion
            acc = tk.Frame(root)
            acc.pack(fill="x", padx=12, pady=(0, 6))
            tk.Button(acc, text="Apagar", width=10, bg="#c62828", fg="white",
                      command=lambda: self._orden("apagar")).pack(side="left")
            tk.Button(acc, text="Suspender", width=10,
                      command=lambda: self._orden("suspender")).pack(side="left", padx=4)
            tk.Button(acc, text="Reiniciar", width=10,
                      command=lambda: self._orden("reiniciar")).pack(side="left")
            tk.Button(acc, text="Cancelar", width=10,
                      command=lambda: self._orden("cancelar")).pack(side="left", padx=4)

            # Congelar raton
            rat = tk.Frame(root)
            rat.pack(fill="x", padx=12, pady=(0, 6))
            tk.Label(rat, text="Segundos:").pack(side="left")
            self.e_seg = tk.Entry(rat, width=6)
            self.e_seg.insert(0, "20")
            self.e_seg.pack(side="left", padx=6)
            tk.Button(rat, text="Congelar raton", bg="#4527a0", fg="white",
                      command=self._congelar).pack(side="left")
            tk.Button(rat, text="Poner fondo de pantalla...", bg="#00695c", fg="white",
                      command=self._fondo).pack(side="left", padx=8)

            # Visor
            vis = tk.Frame(root)
            vis.pack(fill="x", padx=12, pady=(4, 4))
            self.var_ver = tk.IntVar(value=0)
            tk.Checkbutton(vis, text="Ver pantalla en vivo", variable=self.var_ver,
                           command=self._toggle_ver).pack(side="left")
            self.lbl_pantalla = tk.Label(root, text="(sin imagen)", bg="#111111",
                                         fg="#888888", width=ANCHO_MINIATURA)
            self.lbl_pantalla.pack(padx=12, pady=(0, 12))

            root.protocol("WM_DELETE_WINDOW", self._cerrar)

        def _campo(self, padre, etiqueta, fila, valor, oculto=False):
            tk.Label(padre, text=etiqueta).grid(row=fila, column=0, sticky="e", pady=2)
            e = tk.Entry(padre, width=30, show="*" if oculto else "")
            e.insert(0, valor)
            e.grid(row=fila, column=1, sticky="w", padx=6, pady=2)
            return e

        # -- conexion -----------------------------------------------------
        def conectar(self):
            if self.cliente:
                self.cliente.cerrar()
            self.cliente = cliente_cls(
                self.e_host.get().strip(), self.e_puerto.get().strip(),
                self.e_sala.get().strip(), self.e_clave.get(),
            )
            self.cliente.on_frame = self._frame_recibido
            self.cliente.on_respuesta = self._respuesta_recibida
            self.cliente.on_estado = self._estado_cambiado
            try:
                self.cliente.conectar()
            except (OSError, ValueError) as e:
                messagebox.showerror("Error", f"No se pudo conectar: {e}")

        def _estado_cambiado(self, estado):
            def _ui():
                if estado == "conectado":
                    self.lbl_estado.configure(text="Conectado", fg="#1b5e20")
                elif estado.startswith("en_linea"):
                    nombre = estado.partition(":")[2]
                    self.lbl_estado.configure(
                        text=f"Equipo en linea: {nombre}" if nombre else "Equipo en linea",
                        fg="#1b5e20")
                elif estado == "esperando":
                    self.lbl_estado.configure(text="Conectado, esperando al equipo...",
                                              fg="#e65100")
                else:
                    self.lbl_estado.configure(text="Desconectado", fg="#b71c1c")
            self.root.after(0, _ui)

        # -- ordenes ------------------------------------------------------
        def _orden(self, accion, extra=None):
            if not self.cliente:
                messagebox.showinfo("Sin conexion", "Primero conecta al rele.")
                return
            if accion in ("apagar", "reiniciar", "suspender", "congelar_raton"):
                if not messagebox.askyesno("Confirmar", f"¿Enviar '{accion}'?"):
                    return
            try:
                self.cliente.enviar_orden(accion, extra)
            except OSError as e:
                messagebox.showerror("Error", str(e))

        def _congelar(self):
            texto = self.e_seg.get().strip()
            if not texto.isdigit() or int(texto) <= 0:
                messagebox.showwarning("Dato no valido", "Pon un numero de segundos > 0.")
                return
            self._orden("congelar_raton", extra={"segundos": int(texto)})

        def _fondo(self):
            if not self.cliente:
                messagebox.showinfo("Sin conexion", "Primero conecta.")
                return
            from tkinter import filedialog
            ruta = filedialog.askopenfilename(
                title="Elige una imagen para el fondo del equipo remoto",
                filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.bmp *.gif"),
                           ("Todos los archivos", "*.*")],
            )
            if not ruta:
                return
            def _enviar():
                try:
                    imagen_b64 = remoto.leer_imagen_base64(ruta)
                    self.cliente.enviar_fondo(imagen_b64)
                except (OSError, ValueError) as e:
                    self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            # En otro hilo: una imagen grande tarda en enviarse y no debe congelar la ventana.
            threading.Thread(target=_enviar, daemon=True).start()

        def _respuesta_recibida(self, msg):
            def _ui():
                if msg.get("ok"):
                    messagebox.showinfo("Resultado", msg.get("mensaje", ""))
                else:
                    messagebox.showerror("Error", msg.get("mensaje", ""))
            self.root.after(0, _ui)

        # -- visor --------------------------------------------------------
        def _toggle_ver(self):
            if not self.cliente:
                messagebox.showinfo("Sin conexion", "Primero conecta al rele.")
                self.var_ver.set(0)
                return
            kwargs = {}
            if getattr(self.cliente, "ACEPTA_FORMATOS", False):
                kwargs["formatos"] = ["jpeg", "png"] if ImageTk is not None else ["png"]
            self.cliente.ver_pantalla(
                activar=bool(self.var_ver.get()), fps=6, ancho=ANCHO_MINIATURA, **kwargs
            )

        def _frame_recibido(self, msg):
            fmt = msg.get("fmt", "jpeg")
            datos = base64.b64decode(msg.get("img") or msg.get("jpeg"))

            def _ui():
                if ImageTk is not None:
                    self._imgtk = ImageTk.PhotoImage(Image.open(io.BytesIO(datos)))
                elif fmt == "png":
                    self._imgtk = tk.PhotoImage(data=base64.b64encode(datos))
                else:
                    self.lbl_pantalla.configure(text="Instala Pillow para ver JPEG")
                    return
                self.lbl_pantalla.configure(image=self._imgtk, text="")
            self.root.after(0, _ui)

        def _cerrar(self):
            if self.cliente:
                self.cliente.cerrar()
            self.root.destroy()

    root = tk.Tk()
    VentanaConsolaRelay(root)
    root.mainloop()


def main():
    _lanzar_ventana()


if __name__ == "__main__":
    main()
