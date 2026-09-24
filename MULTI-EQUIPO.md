# Monitor multi-equipo (varios PCs a la vez)

Permite ver **varios equipos a la vez** en una rejilla y, seleccionando uno (o
"Todos"), mandarle: apagar, suspender, reiniciar, cancelar, congelar ratón o
poner fondo de pantalla. También ver todas las pantallas en vivo en miniatura.

## Cómo funciona (sin cambiar el relé)

Cada agente se registra en el relé con **su propia sala** (`pc1`, `pc2`, ...).
El monitor abre una conexión con cada uno. Como el relé ya empareja por salas
independientes, no hay que tocarlo: simplemente el monitor gestiona 4
conexiones a la vez. La lógica está en `GestorMulti` (sin interfaz, testeada);
la rejilla la dibuja `VentanaMulti`.

## Puesta en marcha

1. En cada PC, pon una **sala distinta** en su `config.ini` (`[relay] sala`):
   `pc1`, `pc2`, `pc3`, `pc4`. La clave y el host del relé son los mismos.
2. En tu PC, ejecuta `python consola_multi.py`. La primera vez crea
   `equipos_multi.json`; edítalo con tu relé, tu clave y la lista de equipos:
   ```json
   {
     "host": "mi-rele",
     "puerto": 50510,
     "clave": "cambia-esta-clave-2026",
     "equipos": [
       {"nombre": "PC-1", "sala": "pc1"},
       {"nombre": "PC-2", "sala": "pc2"},
       {"nombre": "PC-3", "sala": "pc3"},
       {"nombre": "PC-4", "sala": "pc4"}
     ]
   }
   ```
3. Marca "Ver todas" para las miniaturas. Elige un equipo con su radio-botón (o
   "Todos") y pulsa la acción que quieras.

## Tests

`tests/test_multi.py` levanta el relé y **dos agentes en salas distintas**, y
comprueba: ping a cada uno por separado, que una orden dirigida a PC-1 no llega
a PC-2, fondo a uno + apagar a otro a la vez, broadcast a "Todos", y que el
streaming solo llega del equipo que lo comparte. Son 5 pruebas nuevas.

## Nota

Sigue aplicando lo de siempre: ver pantalla, congelar ratón y fondo necesitan
que el agente corra en la sesión del usuario (no como servicio de la Sesión 0),
y para funcionar entre ciudades hace falta el relé encendido (o Tailscale).


## Novedades: lista persistente, estado en vivo y renombrar

- **Persistencia**: los equipos que anades quedan guardados en `equipos_multi.json`.
  Los apagados **no desaparecen**: se muestran como "desconectado".
- **Estado en vivo con reconexion**: el monitor manda un latido a cada equipo. Si
  esta encendido, sale como ENCENDIDO; si se apaga, pasa a desconectado; y cuando
  vuelve a encenderse, se detecta solo y vuelve a ENCENDIDO, sin quitar a nadie.
- **Orden**: los conectados se colocan arriba; los desconectados debajo.
- **Renombrar**: boton "Renombrar" en cada equipo para ponerle el nombre que
  quieras ("PC Casa", "PC Empresa", "Ordenador Papa"...). Se guarda solo.

La identidad estable de cada equipo es su `sala` del rele; el nombre es solo una
etiqueta editable. Los tests (`tests/test_multi.py`) cubren: guardar/cargar y
renombrar, deteccion de encendidos/apagados, **reconexion al encenderse**, y
acciones/streaming dirigidos a un equipo concreto.
