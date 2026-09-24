# Control Remoto (proyecto educativo)

Dos programas cliente-servidor en Python para **apagar, suspender o reiniciar
tu propio PC en remoto**, y ver si está encendido.

- **`agente.py`** → va en el PC que quieres controlar (p. ej. el de casa).
  Abre una ventana **visible** que indica que está activo y muestra un registro
  de las órdenes recibidas. Escucha por red y solo obedece si le llega la
  **clave** correcta.
- **`consola.py`** → va en el PC desde el que controlas (p. ej. el del trabajo).
  Lista tus equipos, comprueba si están **encendidos** y permite mandarles
  apagar / suspender / reiniciar (con confirmación).

No incluye funciones ocultas ni de control del ratón: es una herramienta
transparente de administración de tus propios equipos.

---

## 1. Requisitos

- Windows 10 u 11 en ambos PCs.
- Python 3.10 o superior (solo para ejecutarlo desde código o para crear los `.exe`).
  Descárgalo de https://www.python.org y marca **"Add Python to PATH"** al instalar.
- `tkinter` viene incluido con Python en Windows (no hay que instalar nada más).

No hacen falta librerías externas para ejecutar los programas.

---

## 2. Configuración de la clave (IMPORTANTE)

Los dos programas usan una **clave compartida**. Debe ser la misma en los dos.

- En el **Agente**: se guarda en `config.ini` (se crea solo la primera vez que lo
  ejecutas, junto al programa). Cambia el valor de `clave`.
- En la **Consola**: escribe la misma clave en el campo "Clave compartida" de la
  ventana. (El valor por defecto de ambos es `cambia-esta-clave-2026`; cámbialo.)

Ejemplo de `config.ini`:

```ini
[agente]
puerto = 50505
clave = mi-clave-secreta-larga
margen_segundos = 15
```

`margen_segundos` es el tiempo de aviso antes de apagar o reiniciar. Durante
ese margen puedes cancelar con el botón "Cancelar apagado" de la Consola.

---

## 3. Uso rápido (desde código)

En el PC de casa:

```
python agente.py
```

Deja esa ventana abierta (puedes minimizarla). Ya está escuchando.

En el PC del trabajo:

```
python consola.py
```

1. Escribe la clave compartida.
2. Pulsa **Añadir** e introduce nombre, la IP del PC de casa y el puerto (50505).
3. Verás su estado en verde (ENCENDIDO) o rojo (offline).
4. Selecciónalo y pulsa **Apagar**, **Suspender** o **Reiniciar**.

---

## 4. Red: que se puedan ver entre ellos

- **Misma red local:** usa la IP local del PC de casa (algo como `192.168.1.x`).
  La ves en la propia ventana del Agente.
- **A través de Internet** (casa ↔ trabajo): necesitas abrir/redirigir el puerto
  (50505) en el router de casa hacia el PC de casa (port forwarding), y usar la
  IP pública de casa. Alternativa más segura y sencilla: una VPN entre ambos
  sitios (por ejemplo Tailscale o WireGuard), y así usas la IP privada sin tocar
  el router.
- **Firewall de Windows:** la primera vez que arranque el Agente, Windows puede
  preguntar si permites la conexión. Acéptalo para redes privadas.

> Consejo de seguridad: usa una clave larga y, si sales a Internet, mejor con VPN.

---

## 5. Descargar los .exe ya compilados (GitHub Actions)

Este repo incluye un flujo de trabajo que **compila los dos `.exe` en Windows
automáticamente** en la nube de GitHub. No necesitas Python para esto.

1. Ve a la pestaña **Actions** del repositorio.
2. Abre la ejecución más reciente de "Compilar .exe (Windows)".
3. Al final, en **Artifacts**, descarga `control-remoto-exe` (un ZIP con
   `Agente.exe` y `Consola.exe`).

Si creas una etiqueta de versión (tag `v1.0`, por ejemplo), el flujo además
publica una **Release** con los dos `.exe` adjuntos.

> El archivo del flujo está en `.github/workflows/build.yml`. Si al crear el
> repo no se subió, créalo a mano copiando el contenido de la sección 5b.

### 5b. Contenido de `.github/workflows/build.yml`

```yaml
name: Compilar .exe (Windows)

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    steps:
      - name: Descargar el codigo
        uses: actions/checkout@v4

      - name: Instalar Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Instalar PyInstaller
        run: pip install pyinstaller

      - name: Compilar Agente.exe
        run: pyinstaller --onefile --windowed --name Agente agente.py

      - name: Compilar Consola.exe
        run: pyinstaller --onefile --windowed --name Consola consola.py

      - name: Subir los .exe como artifact
        uses: actions/upload-artifact@v4
        with:
          name: control-remoto-exe
          path: |
            dist/Agente.exe
            dist/Consola.exe

      - name: Publicar Release (solo al crear un tag vX.Y.Z)
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/Agente.exe
            dist/Consola.exe
```

---

## 6. Crear los dos .exe tú mismo con PyInstaller

Si prefieres compilarlos en tu propio Windows, en una ventana de comandos (CMD)
dentro de la carpeta del proyecto:

```
pip install pyinstaller

pyinstaller --onefile --windowed --name Agente agente.py
pyinstaller --onefile --windowed --name Consola consola.py
```

- `--onefile`: un único `.exe`.
- `--windowed`: sin ventana negra de consola (es app gráfica).

Los ejecutables aparecen en la carpeta `dist\`:

```
dist\Agente.exe
dist\Consola.exe
```

Copia `Agente.exe` al PC de casa y `Consola.exe` al del trabajo.
El `config.ini` y `equipos.json` se crean solos junto a cada `.exe`.

> Nota: algunos antivirus marcan los `.exe` recién hechos con PyInstaller como
> sospechosos (falso positivo típico). Si pasa, añade una excepción para tu
> propio archivo.

---

## 7. Arranque automático del Agente (opcional)

Para que el Agente se abra al encender el PC de casa: pulsa `Win + R`, escribe
`shell:startup` y pega ahí un acceso directo a `Agente.exe`.

---

## 8. Qué se puede añadir (ideas para subir nota)

- Cifrado de la conexión (TLS con `ssl`).
- Log en fichero con fecha de cada acción.
- Autenticación por token que caduca en vez de clave fija.
- Más acciones: bloquear sesión, cerrar sesión, ver uso de CPU/RAM.
