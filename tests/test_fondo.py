"""Tests del cambio de fondo de pantalla (accion_fondo_pantalla)."""

import io
import base64
import types

import agente
import remoto
import pytest


def _png_pequeno_b64():
    """Genera un PNG rojo 4x4 real y lo devuelve en base64 (necesita Pillow)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 0, 0)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_simulado_fuera_de_windows(monkeypatch):
    monkeypatch.setattr(agente, "_es_windows", lambda: False)
    assert "Simulado" in agente.accion_fondo_pantalla(_png_pequeno_b64())


def test_imagen_no_valida(monkeypatch):
    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    # No es base64 valido -> mensaje de error, sin reventar.
    assert "no valida" in agente.accion_fondo_pantalla("###no-base64###").lower()


def test_cambia_fondo_en_windows(monkeypatch, tmp_path):
    llamadas = []

    class _User32:
        def SystemParametersInfoW(self, accion, uparam, ruta, flags):
            llamadas.append((accion, str(ruta)))
            return 1  # exito

    monkeypatch.setattr(agente, "_es_windows", lambda: True)
    monkeypatch.setattr(agente.ctypes, "windll",
                        types.SimpleNamespace(user32=_User32()), raising=False)
    # Guarda el fondo en una carpeta temporal (no en C:\ProgramData).
    monkeypatch.setenv("ProgramData", str(tmp_path))

    msg = agente.accion_fondo_pantalla(_png_pequeno_b64())
    assert "cambiado" in msg.lower()
    # Se ha llamado a la API con accion 20 (SPI_SETDESKWALLPAPER).
    assert llamadas and llamadas[0][0] == 20
    # Y se ha escrito el BMP del fondo.
    assert (tmp_path / "ControlRemotoPC" / "fondo.bmp").exists()


def test_leer_imagen_base64_ida_y_vuelta(tmp_path):
    from PIL import Image
    ruta = tmp_path / "prueba.png"
    Image.new("RGB", (10, 8), (0, 128, 255)).save(ruta, format="PNG")

    b64 = remoto.leer_imagen_base64(str(ruta))
    datos = base64.b64decode(b64)
    # Debe ser una imagen valida que Pillow pueda reabrir.
    img = Image.open(io.BytesIO(datos))
    assert img.size[0] > 0 and img.size[1] > 0
