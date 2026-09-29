# InjectFlow v3.0 - Jupiter TwoShot Release 3.0

## Estado

308B y 309 estan habilitadas en Release 3.0.

## Entrada de usuario

La unica entrada de proceso para Jupiter es el archivo XML del molde. Las
constantes fisicas y de conversion de cada maquina estan embebidas en
`data/Data.xlsx`.

El numero de molde capturado por el usuario es autoritativo y no se valida
contra el numero contenido en el XML ni contra `Moldes.xlsx`.

## Plantilla

`plantillas/Haitian Jupiter TwoShot_1080.xlsx` es la plantilla final bloqueada.

- Area de impresion: A1:CV89
- Orientacion: portrait
- Escala: 49 %
- 730 rangos combinados
- G17 = referencia de campo activo / sin relleno
- G20 = referencia de campo inactivo / #7F7F7F
- Las etiquetas fijas 1, 2, 3, End forman parte de la plantilla. El planner no
  las escribe ni las limpia.

SHA-256 de la plantilla final:
`98359b2edd83ac46b5192b3b78ba7ca49a28da051c315e175dd9fa696e39df40`

## Pendiente conocido

`Rotary Fast Velocity` permanece sin automatizar hasta disponer de una fuente
validada.
