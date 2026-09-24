"""
consola_flota.py - Monitor de flota con descubrimiento automatico.

Dos vistas:
  - PANEL: lista de equipos descubiertos. Pincha uno para entrar.
  - EQUIPO: su pantalla en grande + botones que actuan SOLO sobre ese PC,
            y una flecha (<- Volver) para regresar al panel.
"""

import io
import base64

import nube
import flota

# Debe coincidir con la de agente_auto.py
CLAVE = "ACM-flota-2026-tunel-9f3k2Z"
BROKER = nube.BROKER_POR_DEFECTO
PUERTO = 8883

ANCHO_GRANDE = 900   # ancho de la pantalla en la vista de un equipo


def main():
    import tkinter as tk
    from tkinter import messagebox, filedialog
    try:
        from PIL import Image, ImageTk
        HAY_PIL = True
    except Exception:
        HAY_PIL = False

    root = tk.Tk()
    root.title("Monitor de flota")
    root.geometry("1000x720")

    estado = {}       # sala -> "conectado"/"desconectado"
    hostname = {}     # sala -> nombre
    filas = {}        # sala -> frame en el panel
    lbl_estado = {}   # sala -> label estado en el panel
    actual = {"sala": None}   # equipo abierto en la vista grande
    img_ref = {"img": None}   # referencia viva de la imagen

    gestor = flota.GestorFlota(BROKER, PUERTO, CLAVE, tls=True)

    # ===================== VISTA 1: PANEL (lista) =====================
    vista_panel = tk.Frame(root)

    cab = tk.Frame(vista_panel, bg="#0d47a1")
    cab.pack(fill="x")
    tk.Label(cab, text="  MONITOR DE FLOTA", bg="#0d47a1", fg="white",
             font=("Segoe UI", 14, "bold")).pack(side="left", padx=10, pady=8)
    info = tk.Label(vista_panel, text="Esperando a que los equipos se conecten...", fg="#555")
    info.pack(pady=6)

    cont = tk.Frame(vista_panel)
    cont.pack(fill="both", expand=True, padx=10, pady=6)
    lienzo = tk.Canvas(cont, highlightthickness=0)
    scroll = tk.Scrollbar(cont, orient="vertical", command=lienzo.yview)
    lista = tk.Frame(lienzo)
    lista.bind("<Configure>", lambda e: lienzo.configure(scrollregion=lienzo.bbox("all")))
    lienzo.create_window((0, 0), window=lista, anchor="nw", width=960)
    lienzo.configure(yscrollcommand=scroll.set)
    lienzo.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    def crear_fila(sala, nombre):
        fila = tk.Frame(lista, bd=2, relief="groove", cursor="hand2")
        fila.pack(fill="x", padx=4, pady=4)
        tk.Label(fila, text="🖥", font=("Segoe UI", 16)).pack(side="left", padx=8)
        tk.Label(fila, text=nombre, font=("Segoe UI", 12, "bold")).pack(side="left")
        lbl_estado[sala] = tk.Label(fila, text="ENCENDIDO", fg="#1b5e20",
                                    font=("Segoe UI", 10, "bold"))
        lbl_estado[sala].pack(side="right", padx=10)
        tk.Label(fila, text="Abrir  ▶", fg="#0d47a1").pack(side="right")
        # click en cualquier parte de la fila abre el equipo
        for w in [fila] + list(fila.winfo_children()):
            w.bind("<Button-1>", lambda e, s=sala: abrir_equipo(s))
        filas[sala] = fila
        info.configure(text=f"{len(filas)} equipo(s) descubierto(s). Pincha uno para verlo.")

    # ===================== VISTA 2: UN EQUIPO =====================
    vista_equipo = tk.Frame(root)

    barra = tk.Frame(vista_equipo, bg="#0d47a1")
    barra.pack(fill="x")
    tk.Button(barra, text="◀  Volver", command=lambda: volver_al_panel(),
              bg="#0d47a1", fg="white", bd=0, font=("Segoe UI", 11, "bold"),
              activebackground="#1565c0", cursor="hand2").pack(side="left", padx=6, pady=6)
    titulo_eq = tk.Label(barra, text="", bg="#0d47a1", fg="white",
                         font=("Segoe UI", 13, "bold"))
    titulo_eq.pack(side="left", padx=6)
    estado_eq = tk.Label(barra, text="", bg="#0d47a1", fg="#a5d6a7")
    estado_eq.pack(side="left", padx=6)

    acc = tk.Frame(vista_equipo, bd=1, relief="ridge")
    acc.pack(fill="x", padx=6, pady=4)
    tk.Button(acc, text="Apagar", bg="#c62828", fg="white",
              command=lambda: orden("apagar")).pack(side="left", padx=2)
    tk.Button(acc, text="Suspender", command=lambda: orden("suspender")).pack(side="left", padx=2)
    tk.Button(acc, text="Reiniciar", command=lambda: orden("reiniciar")).pack(side="left", padx=2)
    tk.Button(acc, text="Cancelar", command=lambda: orden("cancelar")).pack(side="left", padx=2)
    tk.Label(acc, text="Seg:").pack(side="left", padx=(10, 0))
    e_seg = tk.Entry(acc, width=4)
    e_seg.insert(0, "20")
    e_seg.pack(side="left", padx=2)
    tk.Button(acc, text="Congelar raton", bg="#4527a0", fg="white",
              command=lambda: congelar()).pack(side="left", padx=2)
    tk.Button(acc, text="Poner fondo...", bg="#00695c", fg="white",
              command=lambda: fondo()).pack(side="left", padx=4)
    ver_var = tk.IntVar(value=0)
    tk.Checkbutton(acc, text="Ver pantalla en vivo", variable=ver_var,
                   command=lambda: toggle_ver()).pack(side="left", padx=8)

    pantalla = tk.Label(vista_equipo, text="(pantalla)\nMarca 'Ver pantalla en vivo'",
                        bg="#111", fg="#888", font=("Segoe UI", 12))
    pantalla.pack(fill="both", expand=True, padx=6, pady=6)

    # ===================== Navegacion =====================
    def mostrar(vista):
        vista_panel.pack_forget()
        vista_equipo.pack_forget()
        vista.pack(fill="both", expand=True)

    def abrir_equipo(sala):
        actual["sala"] = sala
        titulo_eq.configure(text=hostname.get(sala, sala))
        estado_eq.configure(text="ENCENDIDO" if estado.get(sala) == "conectado" else "desconectado")
        pantalla.configure(image="", text="(pantalla)\nMarca 'Ver pantalla en vivo'")
        img_ref["img"] = None
        ver_var.set(0)
        mostrar(vista_equipo)

    def volver_al_panel():
        # al salir, dejamos de pedir su pantalla
        if actual["sala"]:
            gestor.ver(actual["sala"], activar=False)
        actual["sala"] = None
        mostrar(vista_panel)

    # ===================== Acciones (solo el equipo abierto) =====================
    def sala_actual():
        return actual["sala"]

    def orden(accion):
        s = sala_actual()
        if not s:
            return
        if accion in ("apagar", "reiniciar", "suspender"):
            if not messagebox.askyesno("Confirmar", f"¿'{accion}' a {hostname.get(s, s)}?"):
                return
        gestor.enviar(s, accion)

    def congelar():
        s = sala_actual()
        t = e_seg.get().strip()
        if s and t.isdigit() and int(t) > 0:
            gestor.enviar(s, "congelar_raton", {"segundos": int(t)})

    def fondo():
        s = sala_actual()
        if not s:
            return
        ruta = filedialog.askopenfilename(
            title="Imagen de fondo",
            filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Todos", "*.*")])
        if ruta:
            with open(ruta, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            gestor.fondo(s, b64)

    def toggle_ver():
        s = sala_actual()
        if s:
            gestor.ver(s, activar=bool(ver_var.get()), fps=4, ancho=ANCHO_GRANDE)

    # ===================== Callbacks del gestor =====================
    def on_nuevo(sala, nombre):
        hostname[sala] = nombre
        estado[sala] = "conectado"
        root.after(0, lambda: crear_fila(sala, nombre))

    def on_estado(sala, est):
        def _ui():
            estado[sala] = est
            on = est == "conectado"
            if sala in lbl_estado:
                lbl_estado[sala].configure(text="ENCENDIDO" if on else "DESCONECTADO",
                                           fg="#1b5e20" if on else "#b71c1c")
            if actual["sala"] == sala:
                estado_eq.configure(text="ENCENDIDO" if on else "desconectado")
        root.after(0, _ui)

    def on_frame(sala, msg):
        # Solo pintamos la pantalla del equipo que estas viendo.
        if not HAY_PIL or actual["sala"] != sala:
            return
        datos = base64.b64decode(msg.get("img") or msg.get("jpeg") or "")

        def _ui():
            try:
                original = Image.open(io.BytesIO(datos))
                w, h = original.size
                max_w = max(400, pantalla.winfo_width() - 20)
                if w > max_w:
                    original = original.resize((max_w, max(1, int(h * max_w / w))))
                img_ref["img"] = ImageTk.PhotoImage(original)
                pantalla.configure(image=img_ref["img"], text="")
            except Exception:
                pass
        root.after(0, _ui)

    def on_respuesta(sala, msg):
        nombre = hostname.get(sala, sala)
        root.after(0, lambda: messagebox.showinfo("Respuesta", f"[{nombre}] {msg.get('mensaje','')}"))

    gestor.on_nuevo = on_nuevo
    gestor.on_estado = on_estado
    gestor.on_frame = on_frame
    gestor.on_respuesta = on_respuesta
    gestor.conectar()

    mostrar(vista_panel)
    root.protocol("WM_DELETE_WINDOW", lambda: (gestor.cerrar(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
