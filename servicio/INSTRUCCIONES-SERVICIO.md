# Agente como servicio de Windows (segundo plano + arranque automático)

Convierte el **Agente** en un **servicio de Windows** que arranca solo al
encender el PC, corre sin ventana y no depende de que inicies sesión.

## Por qué un archivo nuevo y no tocar `agente.py`

Tu `agente.py` abre una ventana con **tkinter**. Los servicios de Windows se
ejecutan en la **Sesión 0**, que no tiene escritorio, así que una ventana ahí
no se puede mostrar. Por eso se añade `agente_servicio.py`: una versión **sin
interfaz** que **reutiliza tu misma clase de red (`ServidorAgente`) y tu mismo
`config.ini`**. Consecuencia importante: **la Consola sigue funcionando igual**,
porque el protocolo, el puerto y la clave no cambian.

## Archivos

- `agente_servicio.py` — el servicio (va junto a `agente.py`).
- `instalar_servicio.ps1` — instala pywin32, registra el servicio con arranque
  automático y abre el puerto en el firewall.
- `desinstalar_servicio.ps1` — lo quita todo.
- `requirements-servicio.txt` — la dependencia `pywin32`.

## Instalación (en el PC de casa)

1. Copia estos archivos a la **misma carpeta** que `agente.py` y `consola.py`.
   Recomendado: `C:\ControlRemotoPC\` (evita `Archivos de programa`, así el
   servicio puede escribir `config.ini` y los logs sin problemas de permisos).
2. **Configura la clave primero**: ejecuta una vez `python agente.py`, cierra la
   ventana y edita `config.ini` para poner tu clave (la misma que en la Consola).
3. Clic derecho en `instalar_servicio.ps1` → **Ejecutar con PowerShell**
   (pedirá permisos de Administrador).
4. Reinicia el PC y comprueba que el servicio se levanta solo.

Comprobaciones:

```powershell
sc query ControlRemotoPC
```

O abre `services.msc` y busca **Control Remoto PC - Agente** (Estado: En
ejecución; Tipo de inicio: Automático). El registro de actividad queda en:

```
C:\ProgramData\ControlRemotoPC\logs\agente.log
```

## Desinstalación

Clic derecho en `desinstalar_servicio.ps1` → **Ejecutar con PowerShell**.

## Notas

- Con el servicio activo **ya no necesitas** poner el `Agente.exe` en el inicio
  (`shell:startup`). El servicio lo sustituye. Puedes seguir abriendo la ventana
  de `agente.py` a mano si quieres ver el log en vivo para depurar.
- Requiere Python instalado en el PC de casa. Es la vía más limpia y fiable para
  un servicio en Python (compilar un servicio pywin32 a un único `.exe` es
  bastante más frágil, por eso no se recomienda para esto).

---

## Bloque para el README (sustituye tu sección 7)

```markdown
## 7. Ejecutar el Agente como servicio de Windows (segundo plano)

En lugar de dejar la ventana abierta, puedes instalar el Agente como un
**servicio de Windows**: arranca solo al encender el PC, corre en segundo plano
y no depende del inicio de sesión.

Como el Agente con ventana (tkinter) no puede correr como servicio (la Sesión 0
no tiene escritorio), se incluye `agente_servicio.py`, una versión sin interfaz
que reutiliza la misma lógica de red y el mismo `config.ini`. La Consola no
necesita ningún cambio.

Instalación (PC de casa, con Python instalado):

1. Deja `agente_servicio.py` junto a `agente.py`.
2. Ejecuta `python agente.py` una vez y pon tu clave en `config.ini`.
3. Clic derecho en `instalar_servicio.ps1` → "Ejecutar con PowerShell" (admin).

El servicio se llama `ControlRemotoPC` ("Control Remoto PC - Agente"). Compruébalo
con `sc query ControlRemotoPC` o en `services.msc`. Logs en
`C:\ProgramData\ControlRemotoPC\logs\agente.log`. Para quitarlo:
`desinstalar_servicio.ps1`.
```

---

## Para la defensa (por qué sube nota)

- Usa el **Service Control Manager** de Windows vía `pywin32`
  (`win32serviceutil.ServiceFramework`), con inicio **automático**: es un
  servicio de verdad, no un acceso directo en el arranque.
- **Separación de responsabilidades**: la lógica de red (`ServidorAgente`) se
  reutiliza tal cual; solo cambia la "carcasa" (ventana vs. servicio). Eso
  demuestra un diseño desacoplado.
- **Compatibilidad**: mismo protocolo y `config.ini`, así que la Consola no se
  toca.
- **Operación**: ciclo de vida start/stop del SCM, logs rotados en disco y regla
  de firewall creada en la instalación.
