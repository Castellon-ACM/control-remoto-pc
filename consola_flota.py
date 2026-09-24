"""
consola_flota.py - EL MONITOR que descubre los equipos solo.

Abre esta consola con la MISMA clave fija que agente_auto. Segun cada PC va
ejecutando el agente, aparece solo en la rejilla. Eliges uno (o "Todos") y le
mandas apagar / suspender / reiniciar / cancelar / congelar raton / poner fondo,
y ves su pantalla en miniatura.
"""

import io
import base64

import nube
import flota

# Debe coincidir con la de agente_auto.py
CLAVE = "ACM-flota-2026-tunel-9f3k2Z"
BROKER = nube.BROKER_POR_DEFECTO
PUERTO = 8883

ANCHO = 260          # ancho de cada miniatura (px)
COLUMNAS = 2         # equipos por fila


def main():
    import tkinter as tk
    from tkinter import messagebox, filedialog
    try:
        from PIL import Image, ImageTk
        HAY_PIL = True
    except Exception:
        HAY_PIL = False

    root = tk.Tk()
    root.title("Monitor de flota (descubrimiento automatico)")
    root.geometry("620x680")

    celdas, lbl_img, lbl_est, lbl_nom, imgs, estado = {}, {}, {}, {}, {}, {}
    seleccion = tk.StringVar(value="Todos")

    # --- Cabecera ---
    barra = tk.Frame(root, bg="#0d47a1")
    barra.pack(fill="x")
    tk.Label(barra, text="  MONITOR DE FLOTA", bg="#0d47a1", fg="white",
             font=("Segoe UI", 13, "bold")).pack(side="left", padx=8, pady=6)

    # --- Botonera SIEMPRE visible (arriba, no abajo) ---
    acc = tk.Frame(root, bd=1, relief="ridge")
    acc.pack(fill="x", padx=6, pady=4)
    tk.Radiobutton(acc, text="Todos", variable=seleccion, value="Todos").pack(side="left")
    tk.Button(acc, text="Apagar", bg="#c62828", fg="white",
              command=lambda: orden("apagar")).pack(side="left", padx=2)
    tk.Button(acc, text="Suspender", command=lambda: orden("suspender")).pack(side="left", padx=2)
    tk.Button(acc, text="Reiniciar", command=lambda: orden("reiniciar")).pack(side="left", padx=2)
    tk.Button(acc, text="Cancelar", command=lambda: orden("cancelar")).pack(side="left", padx=2)

    acc2 = tk.Frame(root, bd=1, relief="ridge")
    acc2.pack(fill="x", padx=6, pady=(0, 4))
    tk.Label(acc2, text="Seg:").pack(side="left")
    e_seg = tk.Entry(acc2, width=4)
    e_seg.insert(0, "20")
    e_seg.pack(side="left", padx=2)
    tk.Button(acc2, text="Congelar raton", bg="#4527a0", fg="white",
              command=lambda: congelar()).pack(side="left", padx=2)
    tk.Button(acc2, text="Poner fondo...", bg="#00695c", fg="white",
              command=lambda: fondo()).pack(side="left", padx=4)
    tk.Button(acc2, text="Ver todas", bg="#1565c0", fg="white",
              command=lambda: gestor.ver("Todos", True, 3, ANCHO)).pack(side="left", padx=4)

    info = tk.Label(root, text="Esperando a que los equipos se conecten...", fg="#555")
    info.pack(pady=2)

    # --- Zona de equipos CON SCROLL ---
    cont = tk.Frame(root)
    cont.pack(fill="both", expand=True, padx=6, pady=4)
    lienzo = tk.Canvas(cont, highlightthickness=0)
    scroll = tk.Scrollbar(cont, orient="vertical", command=lienzo.yview)
    rejilla = tk.Frame(lienzo)
    rejilla.bind("<Configure>", lambda e: lienzo.configure(scrollregion=lienzo.bbox("all")))
    lienzo.create_window((0, 0), window=rejilla, anchor="nw")
    lienzo.configure(yscrollcommand=scroll.set)
    lienzo.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    # rueda del raton
    lienzo.bind_all("<MouseWheel>", lambda e: lienzo.yview_scroll(int(-e.delta / 120), "units"))

    gestor = flota.GestorFlota(BROKER, PUERTO, CLAVE, tls=True)

    def crear_celda(sala, hostname):
        celda = tk.Frame(rejilla, bd=2, relief="groove")
        cab = tk.Frame(celda)
        cab.pack(fill="x")
        tk.Radiobutton(cab, variable=seleccion, value=sala).pack(side="left")
        lbl_nom[sala] = tk.Label(cab, text=hostname, font=("Segoe UI", 10, "bold"))
        lbl_nom[sala].pack(side="left")
        lbl_est[sala] = tk.Label(cab, text="...", fg="#b71c1c")
        lbl_est[sala].pack(side="right")
        img = tk.Label(celda, text="(sin imagen)\nPulsa 'Ver todas'", bg="#111", fg="#888",
                       width=int(ANCHO / 7), height=int(ANCHO * 9 / 16 / 15))
        img.pack()
        celdas[sala], lbl_img[sala] = celda, img
        estado[sala] = "conectado"
        recolocar()
        info.configure(text=f"{len(celdas)} equipo(s) descubierto(s).")

    def recolocar():
        orden_salas = sorted(celdas, key=lambda s: (estado.get(s) != "conectado", lbl_nom[s]["text"].lower()))
        for i, s in enumerate(orden_salas):
            celdas[s].grid(row=i // COLUMNAS, column=i % COLUMNAS, padx=6, pady=6, sticky="n")

    def destino():
        return seleccion.get()

    def orden(accion):
        if accion in ("apagar", "reiniciar", "suspender"):
            if not messagebox.askyesno("Confirmar", f"¿'{accion}' a: {destino()}?"):
                return
        gestor.enviar(destino(), accion)

    def congelar():
        t = e_seg.get().strip()
        if t.isdigit() and int(t) > 0:
            gestor.enviar(destino(), "congelar_raton", {"segundos": int(t)})

    def fondo():
        ruta = filedialog.askopenfilename(
            title="Imagen de fondo",
            filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Todos", "*.*")])
        if ruta:
            with open(ruta, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            gestor.fondo(destino(), b64)

    def on_nuevo(sala, hostname):
        root.after(0, lambda: crear_celda(sala, hostname))

    def on_estado(sala, est):
        def _ui():
            if sala not in celdas:
                return
            estado[sala] = est
            on = est == "conectado"
            lbl_est[sala].configure(text="ENCENDIDO" if on else "desconectado",
                                    fg="#1b5e20" if on else "#b71c1c")
            if not on:
                lbl_img[sala].configure(image="", text="(desconectado)")
                imgs.pop(sala, None)
            recolocar()
        root.after(0, _ui)

    def on_frame(sala, msg):
        if not HAY_PIL or sala not in celdas:
            return
        datos = base64.b64decode(msg.get("img") or msg.get("jpeg") or "")

        def _ui():
            try:
                original = Image.open(io.BytesIO(datos))
                w, h = original.size
                if w > ANCHO:
                    original = original.resize((ANCHO, max(1, int(h * ANCHO / w))))
                imgs[sala] = ImageTk.PhotoImage(original)
                lbl_img[sala].configure(image=imgs[sala], text="")
            except Exception:
                pass
        root.after(0, _ui)

    def on_respuesta(sala, msg):
        nombre = gestor.hostname(sala)
        root.after(0, lambda: messagebox.showinfo("Respuesta", f"[{nombre}] {msg.get('mensaje','')}"))

    gestor.on_nuevo = on_nuevo
    gestor.on_estado = on_estado
    gestor.on_frame = on_frame
    gestor.on_respuesta = on_respuesta
    gestor.conectar()

    root.protocol("WM_DELETE_WINDOW", lambda: (gestor.cerrar(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
