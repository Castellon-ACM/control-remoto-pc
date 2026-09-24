"""Tests de la configuracion (config.ini) del agente."""

import agente


def test_crea_config_con_valores_por_defecto(tmp_path, monkeypatch):
    ruta = tmp_path / "config.ini"
    monkeypatch.setattr(agente, "CONFIG_FILE", str(ruta))

    seccion = agente.cargar_config()

    assert ruta.exists()                       # se crea el fichero
    assert seccion["puerto"] == "50505"
    assert seccion["clave"] == "cambia-esta-clave-2026"
    assert seccion["margen_segundos"] == "15"


def test_respeta_valores_existentes(tmp_path, monkeypatch):
    ruta = tmp_path / "config.ini"
    ruta.write_text(
        "[agente]\npuerto = 40000\nclave = secreta\nmargen_segundos = 3\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(agente, "CONFIG_FILE", str(ruta))

    seccion = agente.cargar_config()

    assert seccion["puerto"] == "40000"
    assert seccion["clave"] == "secreta"
    assert seccion["margen_segundos"] == "3"


def test_completa_claves_que_falten(tmp_path, monkeypatch):
    ruta = tmp_path / "config.ini"
    # Solo trae el puerto: el resto se debe rellenar con los valores por defecto.
    ruta.write_text("[agente]\npuerto = 12345\n", encoding="utf-8")
    monkeypatch.setattr(agente, "CONFIG_FILE", str(ruta))

    seccion = agente.cargar_config()

    assert seccion["puerto"] == "12345"
    assert seccion["clave"] == "cambia-esta-clave-2026"
    assert seccion["margen_segundos"] == "15"
