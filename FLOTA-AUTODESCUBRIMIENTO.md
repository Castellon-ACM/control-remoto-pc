# Modo flota: un solo .exe, aparecen todos solos

Esto es lo que pediste: repartes **un mismo ejecutable**, cada PC lo abre **sin
ver nada** (ni ventana ni pestaña), y en tu monitor **aparecen todos solos**,
listos para controlar. Sin configurar salas a mano.

## Cómo funciona

- El ejecutable que repartes es **`AgenteAuto.exe`** (de `agente_auto.py`). Al
  abrirse: no muestra ventana, calcula **su propia sala única** (a partir del
  nombre del PC y su MAC), se conecta al broker público y **anuncia su presencia**
  cada pocos segundos por un canal común cifrado. Además se **auto-instala** para
  arrancar solo en cada inicio de sesión.
- Tu monitor es **`MonitorFlota.exe`** (de `consola_flota.py`). Escucha ese canal
  común y va **descubriendo** los equipos; según cada uno abre el agente, aparece
  en la rejilla. Eliges uno (o "Todos") y le mandas apagar / suspender / reiniciar
  / cancelar / congelar ratón / poner fondo, y ves su pantalla en miniatura.

Toda la seguridad es la de `nube.py`: cada mensaje va cifrado y firmado con la
clave; el broker público solo ve bytes aleatorios.

## Clave fija (para que sea "solo ejecutar")

La clave está **fijada en el código**, la misma en `agente_auto.py` y
`consola_flota.py` (constante `CLAVE`). Por eso solo hay que ejecutar: no se
escribe nada. Puedes cambiarla, pero tiene que ser **idéntica en los dos**.

> IMPORTANTE: como la clave está en el código, **mantén el repositorio y los
> `.exe` en PRIVADO**. Cualquiera con esa clave y el broker podría controlar los
> equipos. Para la defensa: "credenciales fijadas para la demo, repo privado; en
> producción irían en configuración".

## Uso (3 pasos)

1. En Actions descarga los `.exe` (`AgenteAuto.exe`, `MonitorFlota.exe`).
2. Reparte `AgenteAuto.exe` a los 3 PCs y que hagan doble clic. No verán nada;
   es normal. (Se instala y queda arrancando solo.)
3. Abre tú `MonitorFlota.exe`. En unos segundos van apareciendo los 3 en la
   rejilla. Selecciona y controla.

## Requisitos y límites (honesto)

- El **monitor** necesita Pillow para ver las pantallas (el `build.yml` ya lo
  incluye; si lo ejecutas con Python: `pip install pillow`). El agente NO necesita
  Pillow.
- El agente corre en la **sesión del usuario** (por eso ver pantalla, congelar
  ratón y fondo funcionan). No es un servicio de la Sesión 0.
- Depende del **broker público** gratuito (`broker.emqx.io`); si algún día falla,
  cambia `BROKER` en los dos archivos por `broker.hivemq.com`. Algunas redes muy
  cerradas bloquean el puerto 8883.
- El visor es una miniatura de pocos fotogramas por segundo.

## Tests

`tests/test_flota.py` levanta un broker local, un agente que se anuncia y el
monitor, y comprueba que el monitor **descubre el equipo solo**, lo **controla**
(ping) y **ve su pantalla**. Son 4 pruebas (77 en total en el proyecto).
