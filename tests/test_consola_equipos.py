"""Tests del guardado/carga de equipos (equipos.json) de la consola."""

import consola


def test_guardar_y_cargar(tmp_path, monkeypatch):
    ruta = tmp_path / "equipos.json"
    monkeypatch.setattr(consola, "EQUIPOS_FILE", str(ruta))

    datos = [
        {"nombre": "PC Casa", "ip": "192.168.1.50", "puerto": "50505"},
        {"nombre": "Portatil", "ip": "10.0.0.7", "puerto": "50505"},
    ]
    consola.guardar_equipos(datos)

    assert ruta.exists()
    assert consola.cargar_equipos() == datos


def test_cargar_sin_fichero(tmp_path, monkeypatch):
    monkeypatch.setattr(consola, "EQUIPOS_FILE", str(tmp_path / "no_existe.json"))
    assert consola.cargar_equipos() == []


def test_cargar_json_corrupto_no_rompe(tmp_path, monkeypatch):
    ruta = tmp_path / "equipos.json"
    ruta.write_text("{ esto no es json valido ", encoding="utf-8")
    monkeypatch.setattr(consola, "EQUIPOS_FILE", str(ruta))
    assert consola.cargar_equipos() == []


def test_enviar_orden_incluye_campos_extra(monkeypatch):
    """enviar_orden debe fusionar 'extra' dentro del mensaje enviado."""
    enviados = {}

    class _SockFalso:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def sendall(self, data):
            enviados["mensaje"] = data

        def settimeout(self, t):
            pass

        def recv(self, n):
            import json
            return (json.dumps({"ok": True, "mensaje": "ok"}) + "\n").encode()

    monkeypatch.setattr(
        consola.socket, "create_connection", lambda *a, **k: _SockFalso()
    )

    consola.enviar_orden("1.2.3.4", 50505, "clave", "congelar_raton",
                         extra={"segundos": 42})

    import json
    payload = json.loads(enviados["mensaje"].decode())
    assert payload["accion"] == "congelar_raton"
    assert payload["clave"] == "clave"
    assert payload["segundos"] == 42
