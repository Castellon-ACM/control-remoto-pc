# Modo remoto (entre ciudades) + visor de pantalla en vivo

Esto añade dos cosas:

1. **Funcionar entre ciudades instalando solo las dos aplicaciones**, sin tocar
   el router de ninguna de las dos casas, mediante un **relé** (rendezvous).
2. **Ver la pantalla del equipo remoto en vivo**, en una **miniatura**.

Todo esto está probado de punta a punta (relé + agente + consola en local):
`test_remoto.py`, `test_relay.py`, `test_remoto_e2e.py`.

---

## Por qué hace falta un relé (y qué es lo más sencillo para ti)

El PC de casa está detrás del router (NAT): desde fuera, nadie puede iniciar una
conexión hacia él sin configurar el router, y su IP pública cambia sola. Por eso
"instalar y ya" entre Barcelona y Madrid no es posible con conexión directa.

La solución es la que usan TeamViewer o AnyDesk: un pequeño **relé con IP
pública** al que **los dos programas se conectan hacia fuera** (las conexiones
salientes sí atraviesan el router sin configurar nada). El relé empareja al
Agente y a la Consola de la misma *sala* y hace de puente.

**Importante y honesto:** ese requisito de "algo con IP pública" no desaparece,
se traslada del PC de casa al relé. Necesitas alojar `relay.py` en algún sitio
accesible. Ordenado de más simple a menos:

- **Lo más sencillo para desarrollar y demostrar:** ejecuta `relay.py` en tu
  propio PC y prueba los tres (relé, agente, consola) en la misma red. Cero
  hosting. Para la demo cruzando ciudades necesitarás una de las siguientes.
- **Una VM gratuita en la nube** (p. ej. la capa "always free" de Oracle Cloud o
  Google Cloud): tiene IP pública. Subes `relay.py`, lo ejecutas y abres el
  puerto 50510 en su firewall. Es lo más parecido a "profesional".
- **Tu propio PC de casa con un único puerto reenviado** (port forwarding del
  50510). Aquí el Agente y la Consola del profesor no tocan nada; la única
  configuración (una vez) está en TU router.

> ### Atajo si quieres el MÍNIMO esfuerzo de implementación
> Si no quieres alojar el relé, instala **Tailscale** (VPN gratuita, sin
> configurar router) en los dos PCs. Les da una IP fija tipo `100.x.x.x` y
> puedes usar el **agente y la consola originales** (`agente.py` / `consola.py`)
> con esa IP, sin relé y sin cambiar más código. Es la vía con menos trabajo;
> el relé es la vía "self-contained" que luce más de cara a nota.

---

## Piezas nuevas

- **`relay.py`** — el relé. Se despliega en el host con IP pública.
  `python relay.py` (escucha en 50510).
- **`remoto.py`** — utilidades compartidas: *framing* de mensajes (para que
  órdenes, respuestas y fotogramas viajen por el mismo socket sin mezclarse) y
  captura de pantalla en JPEG.
- **`agente_relay.py`** — el Agente en modo relé (lo que se instala en casa).
  Se conecta al relé, atiende las órdenes (reutiliza `agente.ejecutar_orden`) y
  envía la pantalla cuando la Consola lo pide.
- **`consola_relay.py`** — la Consola/monitor en modo relé, con botones de acción
  y el **visor en miniatura**. La red está en `ClienteConsolaRelay` (sin
  interfaz, testeable) y la ventana en `VentanaConsolaRelay`.
- **`instalar_agente_relay.ps1`** — deja el agente-relé arrancando solo al
  iniciar sesión (sin ventana, sin admin).
- **`requirements-remoto.txt`** — `pillow` (para el visor).

---

## Puesta en marcha

### 1. El relé (una vez, en el host con IP pública)
```bash
python relay.py            # puerto 50510
```

### 2. El Agente (PC de casa del profesor)
1. Copia `agente.py`, `agente_relay.py`, `remoto.py` a una carpeta.
2. Ejecuta `instalar_agente_relay.ps1` (instala Pillow, crea `config.ini` y el
   arranque automático).
3. Edita `config.ini`:
   ```ini
   [agente]
   clave = una-clave-larga-secreta

   [relay]
   host = ip-o-dominio-del-rele
   puerto = 50510
   sala = casa-profesor
   ```
El agente arrancará solo en cada inicio de sesión, en segundo plano.

### 3. La Consola (el PC desde donde controla)
```bash
pip install pillow
python consola_relay.py
```
Escribe el mismo `host`, `puerto`, `sala` y `clave`, pulsa **Conectar**, y ya
puedes mandar órdenes y marcar **Ver pantalla en vivo** para la miniatura.

---

## El visor de pantalla

El Agente captura la pantalla (Pillow `ImageGrab`), la reduce a una **miniatura**
(por defecto 480 px de ancho), la comprime en JPEG y la manda a la Consola, que
la muestra en vivo. Expectativa realista: no es calidad TeamViewer, son unos
pocos fotogramas por segundo a resolución reducida para que fluya (y para no
gastar mucho ancho de banda a través del relé). Puedes ajustar `fps` y `ancho`.

---

## Aviso importante (sesión de usuario vs. servicio)

Tanto **ver la pantalla** como **congelar el ratón** actúan sobre el escritorio
del usuario. Un **servicio de Windows** corre en la **Sesión 0**, aislada del
escritorio, y desde ahí NO puede capturar la pantalla ni mover el cursor. Por eso
el agente-relé se instala para arrancar **en la sesión del usuario** (con
`instalar_agente_relay.ps1`), no como servicio.

Resumen de qué usar:
- **Apagar / suspender / reiniciar en segundo plano** → sirve el servicio
  (`servicio/`) o el agente-relé.
- **Ver pantalla + congelar ratón + funcionar entre ciudades** → agente-relé en
  la sesión del usuario (esta carpeta).

Para la demo completa que pide el profesor (instalar dos cosas, que arranque
solo, ver la pantalla y controlar entre ciudades), usa **agente_relay.py** +
**consola_relay.py** + **relay.py**.

---

## Tests

```bash
pip install pytest
python -m pytest -v
```
Son 41 pruebas. Las del modo remoto levantan el relé, el agente-relé y el cliente
de consola en localhost y comprueban: *framing*, emparejamiento del relé (en los
dos órdenes de llegada), rechazo de un segundo cliente, órdenes por el relé
(ping, apagar con Windows simulado, congelar, clave incorrecta) y el **streaming
de pantalla** (con captura simulada, sin necesidad de pantalla real).
