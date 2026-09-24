# Extra (congelar el ratón) + batería de tests

## 1. El extra: congelar el ratón desde la Consola

Se añade una orden nueva, `congelar_raton`, con un parámetro `segundos`.

**Cómo funciona:** el Agente lee la posición actual del cursor (`GetCursorPos`)
y lo mantiene clavado justo ahí (`SetCursorPos` en bucle), de modo que el ratón
no se puede mover durante el tiempo indicado. Al terminar, se libera solo.

**Decisiones de diseño (importantes para la defensa):**
- **El teclado sigue funcionando**: solo se "congela" el ratón, nunca se
  bloquea al usuario por completo. Es reversible.
- **Se libera solo** al agotarse el tiempo (no hace falta ninguna otra orden).
- **Tope de seguridad de 300 s** (`CONGELAR_TOPE_SEGUNDOS`): aunque pidas más,
  nunca congela más de eso.
- **No permite dos congelaciones a la vez** (guard con `threading.Event`).

**Uso desde la Consola:** selecciona el equipo, escribe los segundos en el campo
"Segundos" y pulsa **Congelar ratón** (pide confirmación).

### Cambios (dónde tocar)

- `agente.py`: nueva función `accion_congelar_raton()` y una rama nueva en el
  servidor para la acción `congelar_raton`. (`import time`, `import ctypes`.)
- `consola.py`: `enviar_orden()` ahora admite un `extra` opcional; nuevo campo
  "Segundos" + botón "Congelar ratón" y el método `congelar_raton()`.

Puedes copiar los archivos completos `agente.py` y `consola.py` de esta carpeta,
o aplicar solo esos trozos.

### Aviso técnico (Sesión 0)

El congelado del ratón actúa sobre el escritorio del usuario, así que funciona
cuando el Agente corre **en la sesión del usuario** (la ventana de `agente.py`).
Un servicio de Windows corre en la **Sesión 0**, aislada del escritorio, y desde
ahí no puede mover el cursor del usuario. Es decir: para demostrar el extra,
ejecuta el Agente con ventana; el servicio es para las otras órdenes (apagar,
suspender, reiniciar), que sí funcionan en segundo plano.

---

## 2. Batería de tests (29 pruebas, todas en verde)

Los tests están en la carpeta `tests/`. Prueban Agente y Consola **juntos** por
red real en localhost, y las piezas por separado.

### Cómo ejecutarlos

```bash
pip install pytest
python -m pytest tests -v
```

Nota: Agente y Consola importan `tkinter` solo para las ventanas. Para poder
lanzar los tests en cualquier entorno (incluida integración continua sin
escritorio), `tests/conftest.py` inyecta un stub de `tkinter` **solo si no está
instalado**. No cambia el código del proyecto.

### Qué cubren

- **`test_config.py`** — `config.ini`: se crea con valores por defecto, respeta
  los existentes y completa los que falten.
- **`test_acciones.py`** — apagar/reiniciar/suspender/cancelar llaman al comando
  correcto de Windows (con `subprocess` simulado) y, fuera de Windows, no
  ejecutan nada.
- **`test_congelar_raton.py`** — el extra: validaciones (segundos no numéricos,
  ≤ 0), tope de 300 s, que congela y **se libera solo**, y que no permite dos a
  la vez.
- **`test_integracion.py`** — levanta el servidor real y le habla con la
  `enviar_orden` real de la Consola: ping, clave incorrecta, acción desconocida,
  JSON inválido, conexión rechazada, apagar por protocolo y **congelar el ratón
  por protocolo** (comprobando que el parámetro `segundos` viaja bien).
- **`test_consola_equipos.py`** — guardado/carga de `equipos.json` (incluido
  JSON corrupto) y que `enviar_orden` fusiona bien los campos `extra`.

### Para el repo

Puedes subir `tests/` y `pytest.ini`, y añadir un paso de tests a tu
`build.yml` (antes de compilar):

```yaml
      - name: Instalar dependencias de test
        run: pip install pytest

      - name: Ejecutar tests
        run: python -m pytest tests -v
```

Así el propio flujo de GitHub Actions ejecuta las pruebas en cada push: otro
punto a favor de cara a la nota.
