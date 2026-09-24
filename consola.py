"""
CONSOLA REMOTA - Programa para el PC desde el que controlas (p. ej. el del trabajo)
===================================================================================

Interfaz de escritorio que:
  - Lista los equipos que tengas dados de alta (nombre, IP y puerto).
  - Comprueba periodicamente si cada equipo esta ENCENDIDO (online) u OFFLINE.
  - Permite enviar ordenes: apagar, suspender o reiniciar (con confirmacion).

Se conecta al Agente enviando la CLAVE compartida. Si la clave no coincide,
el Agente rechaza la orden.

Los equipos se guardan en "equipos.json" junto al programa.

Proyecto educativo.

Autor: (tu nombre)
"""

import socket
import json
import os
import threading

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

EQUIPOS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "equipos.json"
)

TIMEOUT_CONEXION = 3.0  # segundos
INTERVALO_SONDEO = 5000  # milisegundos entre comprobaciones de estado


# ---------------------------------------------------------------------------
# Comunicacion con el agente
# ---------------------------------------------------------------------------
def enviar_orden(ip, puerto, clave, accion, extra=None):
    """Envia una orden al agente y devuelve (ok, mensaje).

    'extra' permite anadir campos adicionales al mensaje (por ejemplo
    {"segundos": 20} para la orden de congelar el raton).
    """
    mensaje = {"clave": clave, "accion": accion}
    if extra:
        mensaje.update(extra)
    try:
        with socket.create_connection((ip, int(puerto)), timeout=TIMEOUT_CONEXION) as s:
            s.sendall((json.dumps(mensaje) + "\n").encode("utf-8"))
            s.settimeout(TIMEOUT_CONEXION)
            datos = s.recv(4096).decode("utf-8").strip()
            if not datos:
                return False, "Sin respuesta del agente."
            resp = json.loads(datos)
            return bool(resp.get("ok")), resp.get("mensaje", "")
    except socket.timeout:
        return False, "Tiempo de espera agotado."
    except ConnectionRefusedError:
        return False, "Conexion rechazada (¿agente apagado?)."
    except OSError as e:
        return False, f"No accesible: {e}"
    except json.JSONDecodeError:
        return False, "Respuesta no valida del agente."


# ---------------------------------------------------------------------------
# Almacenamiento de equipos
# ---------------------------------------------------------------------------
def cargar_equipos():
    if os.path.exists(EQUIPOS_FILE):
        try:
            with open(EQUIPOS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def guardar_equipos(equipos):
    with open(EQUIPOS_FILE, "w", encoding="utf-8") as f:
        json.dump(equipos, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Dialogo para anadir/editar un equipo
# ---------------------------------------------------------------------------
class DialogoEquipo(simpledialog.Dialog):
    def __init__(self, parent, titulo, equipo=None):
        self.equipo = equipo or {"nombre": "", "ip": "", "puerto": "50505"}
        super().__init__(parent, titulo)

    def body(self, master):
        tk.Label(master, text="Nombre:").grid(row=0, column=0, sticky="e", pady=4)
        tk.Label(master, text="IP o host:").grid(row=1, column=0, sticky="e", pady=4)
        tk.Label(master, text="Puerto:").grid(row=2, column=0, sticky="e", pady=4)

        self.e_nombre = tk.Entry(master, width=28)
        self.e_ip = tk.Entry(master, width=28)
        self.e_puerto = tk.Entry(master, width=28)

        self.e_nombre.grid(row=0, column=1, padx=6, pady=4)
        self.e_ip.grid(row=1, column=1, padx=6, pady=4)
        self.e_puerto.grid(row=2, column=1, padx=6, pady=4)

        self.e_nombre.insert(0, self.equipo["nombre"])
        self.e_ip.insert(0, self.equipo["ip"])
        self.e_puerto.insert(0, self.equipo["puerto"])
        return self.e_nombre

    def validate(self):
        if not self.e_nombre.get().strip():
            messagebox.showwarning("Falta dato", "Pon un nombre.")
            return False
        if not self.e_ip.get().strip():
            messagebox.showwarning("Falta dato", "Pon una IP o host.")
            return False
        if not self.e_puerto.get().strip().isdigit():
            messagebox.showwarning("Dato no valido", "El puerto debe ser un numero.")
            return False
        return True

    def apply(self):
        self.result = {
            "nombre": self.e_nombre.get().strip(),
            "ip": self.e_ip.get().strip(),
            "puerto": self.e_puerto.get().strip(),
        }


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------
class VentanaConsola:
    def __init__(self, root):
        self.root = root
        self.equipos = cargar_equipos()
        self.clave = "cambia-esta-clave-2026"  # se puede cambiar desde la interfaz

        root.title("Consola Remota")
        root.geometry("680x460")
        root.minsize(600, 400)

        # Cabecera
        cabecera = tk.Frame(root, bg="#0d47a1")
        cabecera.pack(fill="x")
        tk.Label(
            cabecera,
            text="  CONSOLA REMOTA",
            bg="#0d47a1",
            fg="white",
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=10)

        # Barra de clave
        barra_clave = tk.Frame(root)
        barra_clave.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(barra_clave, text="Clave compartida:").pack(side="left")
        self.e_clave = tk.Entry(barra_clave, show="*", width=30)
        self.e_clave.pack(side="left", padx=6)
        self.e_clave.insert(0, self.clave)
        tk.Button(
            barra_clave, text="Mostrar/Ocultar", command=self._toggle_clave
        ).pack(side="left")

        # Tabla de equipos
        cols = ("nombre", "ip", "puerto", "estado")
        self.tabla = ttk.Treeview(root, columns=cols, show="headings", height=10)
        self.tabla.heading("nombre", text="Nombre")
        self.tabla.heading("ip", text="IP / Host")
        self.tabla.heading("puerto", text="Puerto")
        self.tabla.heading("estado", text="Estado")
        self.tabla.column("nombre", width=180)
        self.tabla.column("ip", width=200)
        self.tabla.column("puerto", width=80, anchor="center")
        self.tabla.column("estado", width=140, anchor="center")
        self.tabla.pack(fill="both", expand=True, padx=12, pady=8)

        self.tabla.tag_configure("online", foreground="#1b5e20")
        self.tabla.tag_configure("offline", foreground="#b71c1c")

        # Botones de gestion
        botones = tk.Frame(root)
        botones.pack(fill="x", padx=12, pady=(0, 6))
        tk.Button(botones, text="Anadir", width=10, command=self.anadir).pack(side="left")
        tk.Button(botones, text="Editar", width=10, command=self.editar).pack(side="left", padx=4)
        tk.Button(botones, text="Eliminar", width=10, command=self.eliminar).pack(side="left")
        tk.Button(botones, text="Comprobar ahora", command=self.sondear).pack(side="right")

        # Botones de accion
        acciones = tk.Frame(root)
        acciones.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(
            acciones, text="Apagar", width=14, bg="#c62828", fg="white",
            command=lambda: self.enviar("apagar"),
        ).pack(side="left")
        tk.Button(
            acciones, text="Suspender", width=14,
            command=lambda: self.enviar("suspender"),
        ).pack(side="left", padx=4)
        tk.Button(
            acciones, text="Reiniciar", width=14,
            command=lambda: self.enviar("reiniciar"),
        ).pack(side="left")
        tk.Button(
            acciones, text="Cancelar apagado", width=16,
            command=lambda: self.enviar("cancelar", confirmar=False),
        ).pack(side="left", padx=4)

        # Congelar el raton durante los segundos indicados
        raton = tk.Frame(root)
        raton.pack(fill="x", padx=12, pady=(0, 12))
        tk.Label(raton, text="Segundos:").pack(side="left")
        self.e_segundos = tk.Entry(raton, width=6)
        self.e_segundos.pack(side="left", padx=6)
        self.e_segundos.insert(0, "20")
        tk.Button(
            raton, text="Congelar raton", width=16, bg="#4527a0", fg="white",
            command=self.congelar_raton,
        ).pack(side="left")
        tk.Label(
            raton,
            text="(fija el raton en el equipo seleccionado; el teclado sigue activo)",
            fg="#555555",
        ).pack(side="left", padx=8)

        self.refrescar_tabla()
        self._programar_sondeo()

    # -- utilidades de interfaz -------------------------------------------
    def _toggle_clave(self):
        self.e_clave.configure(show="" if self.e_clave.cget("show") else "*")

    def _clave_actual(self):
        return self.e_clave.get()

    def refrescar_tabla(self):
        seleccion = self.tabla.selection()
        self.tabla.delete(*self.tabla.get_children())
        for i, eq in enumerate(self.equipos):
            self.tabla.insert(
                "", "end", iid=str(i),
                values=(eq["nombre"], eq["ip"], eq["puerto"], eq.get("estado", "?")),
                tags=(eq.get("_tag", ""),),
            )
        if seleccion:
            try:
                self.tabla.selection_set(seleccion)
            except Exception:
                pass

    def _equipo_seleccionado(self):
        sel = self.tabla.selection()
        if not sel:
            messagebox.showinfo("Sin seleccion", "Selecciona un equipo de la lista.")
            return None
        return int(sel[0])

    # -- gestion de equipos -----------------------------------------------
    def anadir(self):
        d = DialogoEquipo(self.root, "Anadir equipo")
        if d.result:
            self.equipos.append(d.result)
            guardar_equipos(self.equipos)
            self.refrescar_tabla()

    def editar(self):
        idx = self._equipo_seleccionado()
        if idx is None:
            return
        d = DialogoEquipo(self.root, "Editar equipo", self.equipos[idx])
        if d.result:
            self.equipos[idx].update(d.result)
            guardar_equipos(self.equipos)
            self.refrescar_tabla()

    def eliminar(self):
        idx = self._equipo_seleccionado()
        if idx is None:
            return
        if messagebox.askyesno("Eliminar", f"¿Eliminar '{self.equipos[idx]['nombre']}'?"):
            self.equipos.pop(idx)
            guardar_equipos(self.equipos)
            self.refrescar_tabla()

    # -- acciones y estado -------------------------------------------------
    def enviar(self, accion, confirmar=True, extra=None):
        idx = self._equipo_seleccionado()
        if idx is None:
            return
        eq = self.equipos[idx]

        nombres = {
            "apagar": "APAGAR",
            "reiniciar": "REINICIAR",
            "suspender": "SUSPENDER",
            "cancelar": "cancelar el apagado de",
            "congelar_raton": "CONGELAR EL RATON de",
        }
        if confirmar:
            if not messagebox.askyesno(
                "Confirmar",
                f"¿Seguro que quieres {nombres.get(accion, accion)} '{eq['nombre']}'?",
            ):
                return

        def _tarea():
            ok, msg = enviar_orden(
                eq["ip"], eq["puerto"], self._clave_actual(), accion, extra
            )
            self.root.after(
                0,
                lambda: messagebox.showinfo("Resultado", msg)
                if ok
                else messagebox.showerror("Error", msg),
            )

        threading.Thread(target=_tarea, daemon=True).start()

    def congelar_raton(self):
        """Envia la orden de congelar el raton con los segundos indicados."""
        texto = self.e_segundos.get().strip()
        if not texto.isdigit() or int(texto) <= 0:
            messagebox.showwarning(
                "Dato no valido", "Pon los segundos como un numero mayor que 0."
            )
            return
        self.enviar(
            "congelar_raton", confirmar=True, extra={"segundos": int(texto)}
        )

    def sondear(self):
        """Comprueba el estado de todos los equipos en segundo plano."""
        def _tarea():
            for i, eq in enumerate(list(self.equipos)):
                ok, _ = enviar_orden(
                    eq["ip"], eq["puerto"], self._clave_actual(), "ping"
                )
                if i < len(self.equipos):
                    self.equipos[i]["estado"] = "ENCENDIDO" if ok else "offline"
                    self.equipos[i]["_tag"] = "online" if ok else "offline"
            self.root.after(0, self.refrescar_tabla)

        threading.Thread(target=_tarea, daemon=True).start()

    def _programar_sondeo(self):
        self.sondear()
        self.root.after(INTERVALO_SONDEO, self._programar_sondeo)


def main():
    root = tk.Tk()
    VentanaConsola(root)
    root.mainloop()


if __name__ == "__main__":
    main()
