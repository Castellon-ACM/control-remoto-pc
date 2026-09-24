# Modo nube: entre ciudades sin relé, sin VPN y sin instalar nada

Con el modo nube, un PC en Madrid y otro en Barcelona se controlan a través de Internet sin montar ningún servidor. No hace falta abrir puertos, ni instalar Tailscale, ni ejecutar `pip install`.

## Cómo funciona

Los dos equipos abren una conexión **saliente** hacia un broker MQTT público y gratuito (por defecto `broker.emqx.io`, puerto 8883 con TLS). Hace de centralita: el agente escucha en un canal, la consola en otro y el broker pasa los mensajes de uno a otro. Como la conexión la inician los dos PCs, atraviesa cualquier router doméstico, igual que abrir una web.

```
 PC Barcelona (agente_nube)  ──TLS──►  broker.emqx.io  ◄──TLS──  PC Madrid (consola_nube)
```

Todo está hecho con la librería estándar de Python (`socket`, `ssl`, `hashlib`, `hmac`, `zlib`, `ctypes`). El visor de pantalla funciona también sin Pillow: captura la pantalla con la API de Windows y genera un PNG que Tk muestra directamente. Si tienes Pillow instalado, usa JPEG, que ocupa menos y se ve mejor.

## Fondo de pantalla remoto

Con «Poner fondo de pantalla…» eliges una imagen en la consola y el otro PC la pone como fondo de escritorio, algo parecido a lo que haces con AnyDesk en el escritorio del otro equipo. El broker público limita el tamaño de cada mensaje, así que la imagen viaja partida en trozos de 150 KB, cada uno cifrado y firmado, y el agente la reconstruye. Después la aplica con la API de Windows (`SystemParametersInfoW`, `SPI_SETDESKWALLPAPER`).

- Con Pillow, la consola reduce la imagen a 1920 px y el agente la convierte a BMP.
- Sin Pillow, se envía el archivo tal cual (máximo 15 MB) y Windows usa directamente el JPG, PNG o BMP. El agente comprueba por los primeros bytes que de verdad es una imagen y rechaza cualquier otra cosa.

## Seguridad (el broker es público)

Cualquiera puede conectarse al broker, así que el programa no se fía de él:

- **Canal secreto.** El nombre del canal se calcula a partir de la sala y la clave (PBKDF2, 100.000 iteraciones). Sin la clave no se sabe dónde escuchar.
- **Cifrado de extremo a extremo.** Cada mensaje va cifrado (flujo SHAKE-256) y firmado (HMAC-SHA256). El broker solo ve bytes aleatorios; ni las órdenes ni las capturas de pantalla viajan en claro.
- **La clave nunca viaja por la red.** La firma demuestra que quien envía la conoce.
- **Anti-replay.** Se rechazan los mensajes repetidos, los de hace más de 5 minutos y los reenviados en sentido contrario.
- **No arranca con la clave por defecto** ni con claves de menos de 8 caracteres.

Los tests (`tests/test_nube.py`) comprueban todo esto: un intruso con otra clave no puede apagar el equipo, reenviar un mensaje capturado no lo ejecuta dos veces y el broker nunca ve ni la clave ni el texto de las órdenes.

## Puesta en marcha (5 minutos)

### Opción A: con los .exe (sin Python)

GitHub Actions compila `AgenteNube.exe` y `ConsolaNube.exe` en cada push (pestaña **Actions**, último run, artefacto `control-remoto-exe`).

1. **PC controlado (Barcelona):** abre `AgenteNube.exe`. En la ventana pon una **sala** y una **clave** tuyas y pulsa *Guardar y conectar*. Tiene que aparecer «Conectado a broker.emqx.io».
2. **PC que controla (Madrid):** abre `ConsolaNube.exe`, escribe la misma sala y la misma clave y pulsa *Conectar*. A los pocos segundos verás «Equipo en línea: NOMBRE-PC».
3. Usa los botones (apagar, suspender, reiniciar, cancelar, congelar ratón, «Poner fondo de pantalla…») o marca «Ver pantalla en vivo».

Para que el agente arranque solo: pulsa `Win + R`, escribe `shell:startup` y pega ahí un acceso directo a `AgenteNube.exe`.

### Opción B: con Python

```
python agente_nube.py        # en el PC controlado (ventana de estado)
python consola_nube.py       # en el PC que controla
```

`instalar_agente_nube.ps1` lo deja arrancando solo al iniciar sesión, sin ventana (`agente_nube.py --oculto`). No instala nada con pip.

## Configuración (`config.ini`, se crea solo)

```ini
[agente]
clave = tu-clave-larga-y-secreta

[nube]
broker = broker.emqx.io
puerto = 8883
sala = casa-mi-pc
```

Si `broker.emqx.io` fallara, hay otros brokers públicos gratuitos con TLS en el 8883, como `broker.hivemq.com` o `test.mosquitto.org`. Pon el mismo broker en el agente y en la consola.

## Limitaciones, para contarlas en la defensa

- Depende de un servicio público gratuito, sin garantía de disponibilidad. Para producción se usaría un broker propio o de pago; el código no cambia, solo `broker` en `config.ini`.
- Algunas redes muy cerradas (institutos, empresas) bloquean el puerto 8883. En casa funciona.
- El visor es una miniatura de 3-4 fotogramas por segundo: sirve para ver qué se está haciendo, no para jugar.
- El agente tiene que ejecutarse en la sesión del usuario, no como servicio, porque el visor y congelar el ratón actúan sobre el escritorio.
