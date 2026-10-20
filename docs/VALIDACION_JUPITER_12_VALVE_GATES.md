# InjectFlow v3.0 - Secuenciador Jupiter de 12 compuertas

## Alcance

Correccion para 308B y 309, grupo `HAITIAN_JUPITER_TWOSHOT`, layout
`JUPITER_TWOSHOT_1080_V1`. La capacidad real de la plantilla es de **12 filas
fisicas (66 a 77)**. No son los canales XML 1 a 12: se pueden seleccionar hasta
12 compuertas activas de los indices XML 1..48, con numeracion directa.

Base usada: `AutomatizacionParametros_v3.0_startup_fix.zip`, mas
`InjectFlow_v3.0_ValveGate_103_Fix_Delta.zip` y
`InjectFlow_v3.0_Plantillas_20261015_Delta.zip`, disponibles en este chat.
No se modifico el repositorio de GitHub ni el equipo Windows del usuario.

## Diagnostico y correccion

- `Data.xlsx / Config / B66`: `JUPITER_VALVE_GATE_MAX_ACTIVE`, 9 -> 12.
  C66 documenta las filas 66..77. No se modifican Param, Resul, StateMap,
  Jupiter ni MachineConstants.
- `Mapeo.xlsx / ValveGateLogic / D66`: `TEMPLATE_MAX_ACTIVE_GATES`, 9 -> 12.
  Se actualizan las explicaciones de capacidad, asignacion y limite.
- `Mapeo.xlsx / ValveGateLayout`: se conservan SLOT1..SLOT9 y se agregan
  SLOT10, SLOT11 y SLOT12, con 12 campos cada uno (36 entradas nuevas).
  La tabla Jupiter queda con 144 destinos fisicos. Se actualizan los filtros
  visibles y los nombres internos de filtro de las dos hojas de secuenciador.
- `app/jupiter_xml_parser.py`: `MAX_VALVE_GATE_ACTIVE`, 9 -> 12.
  Era un bloqueo adicional: cambiar solo Mapeo.xlsx no permitia procesar
  recetas de 10, 11 o 12 compuertas con el ejecutable anterior.
- `tests/test_jupiter_integration.py`: el limite negativo pasa de mas de 9
  a exactamente 13 activas. No se elimina la comprobacion de desbordamiento.
- `tests/test_jupiter_valve_gate_capacity.py`: 22 casos nuevos con datos
  sinteticos independientes del maestro Moldes.xlsx.

El planner ya obtiene la capacidad y los destinos desde Mapeo.xlsx; no hizo
falta modificar app/plan.py. Tanto parser como planner siguen bloqueando
mas de 12 activas. No se truncan ni omiten compuertas para hacerlas caber.

## Nuevas posiciones

| Campo | SLOT10 | SLOT11 | SLOT12 |
|---|---|---|---|
| Numero real de compuerta | AV75 | AV76 | AV77 |
| OPEN - USE | AX75 | AX76 | AX77 |
| OPEN - MODE | BA75 | BA76 | BA77 |
| OPEN - MM | BE75 | BE76 | BE77 |
| OPEN - DELAY | BI75 | BI76 | BI77 |
| CLOSE - MODE | BN75 | BN76 | BN77 |
| CLOSE - MM | BR75 | BR76 | BR77 |
| CLOSE - DELAY | BV75 | BV76 | BV77 |
| HOLD - USE | CA75 | CA76 | CA77 |
| HOLD - DELAY | CD75 | CD76 | CD77 |
| HOLD - HOLD | CH75 | CH76 | CH77 |
| Inyection No. | CM75 | CM76 | CM77 |

Todos son anclas de celdas combinadas existentes. Se respeta G17 como
referencia activa/sin relleno y G20 como referencia inactiva. Las filas sin
compuerta quedan vacias y sombreadas. Cuando HOLD esta apagado, se ocultan
sus tiempos residuales sin desactivar toda la fila.

## Plantilla conservada

El adjunto `Haitian Jupiter TwoShot_1080(10).xlsx` es identico byte por byte
a la plantilla canonica de la actualizacion anterior. La capacidad de 12
filas ya existia; la limitacion estaba en los catalogos y el parser.

SHA-256:
`e763ca4e75a79f704b99b20b02f9f76ac153935ce5a011e53749504dbc17f87f`

Se conservan sus 730 rangos combinados, area A1:CV89, escala 49,
formulas, etiquetas fijas y observaciones. Las escrituras adicionales estan
en AV:CU, no en A75/A76. No es necesario reemplazar la plantilla y no se
incluye una copia duplicada dentro de este delta.

## Pruebas automatizadas ejecutadas

La base previa paso 204 pruebas de logica (UI ejecutada separadamente).

Resultado final, en dos procesos:

```text
python -m pytest -q -ra -k "not test_ui"
226 passed, 4 deselected in 94.46s (0:01:34)

python -m pytest -q -ra tests/test_jupiter_integration.py -k test_ui
4 passed, 37 deselected in 10.22s
```

**230 pruebas distintas aprobadas: 226 de logica y 4 de interfaz.** Los
22 casos nuevos estan incluidos en las 226, no se suman nuevamente.
Las 4 deseleccionadas en logica se ejecutaron en el bloque de interfaz.
Los tests de interfaz usan Chromium sin ventana; no son el EXE WinForms.
En el PC del usuario, estas 4 pruebas pueden seguir omitiendose si falta
su dependencia opcional.

Cobertura nueva: 308B y 309 con 0, 1, 4, 9, 10, 11 y 12 compuertas; todos
los campos de las nuevas filas; unidades U1/U2; POSITION/TIME; rellenos;
HOLD activo/inactivo; limpieza de datos residuales; preservacion de
observaciones y etiquetas; coincidencia de los tres limites; rechazo de
13 activas tanto en parser como en planner. Se incluyen indices dispersos
como 9, 13, 37 y 48 para no confundir numero de compuerta con numero de fila.

Tambien se compilaron los modulos con compileall sin errores. Se revisaron
renders de la plantilla, los cambios de catalogos y una hoja sintetica con
las doce compuertas activas. Las copias sinteticas NO son recetas reales
ni parametros recomendados de operacion.

## Regresion con los archivos reales disponibles

| Maquina | Molde | Operaciones antes | Ahora | Advertencias | Faltantes |
|---|---|---:|---:|---:|---:|
| 103A | I-1954 | 433 | 433 | 0 | 0 |
| 117B | I-1625 | 441 | 441 | 0 | 0 |
| 308B | I-1689 | 693 | 765 | 0 | 0 |
| 309 | I-1695 | 753 | 825 | 0 | 0 |

103A es el nombre de catalogo de la maquina 103 del usuario. Los planes
Zeres son identicos byte por byte. En Jupiter, al quitar las 72 operaciones
nuevas de CLEAR/COPY_FILL de las filas 75..77 e ignorar el indice SEQ,
las operaciones anteriores son identicas, en contenido y orden.
Los archivos reales de Jupiter disponibles tienen 4 y 9 compuertas
activas respectivamente; los ensayos con 10 a 12 son sinteticos.

## Integridad y cambios protegidos

- Los catalogos XLSX pasan la comprobacion interna ZIP.
- Data.xlsx: solo cambia xl/worksheets/sheet1.xml (Config).
- Mapeo.xlsx: solo cambian los XML de ValveGateLogic, ValveGateLayout,
  README, Audit y las dos referencias de filtro en workbook.xml.
- Los demas componentes internos XLSX, incluidos estilos, permanecen
  identicos. No hay formulas en los catalogos que requieran recalculo.
- Se verificaron sin cambios los archivos main.py, resolver.py, plan.py,
  parsers.py, excel_writer.py, launcher_web.py, el batch, Moldes.xlsx y las
  cinco plantillas. Los limites y mapeos Zeres no se modifican.

## Instalacion y limite de validacion

Reemplazar los cinco archivos del delta en la raiz del proyecto,
respetando carpetas. Mantener la plantilla adjunta con el nombre canonico
`plantillas/Haitian Jupiter TwoShot_1080.xlsx`.

Es necesario volver a ejecutar `CREAR_INJECTFLOW_EXE.bat`, ya que el parser
forma parte del EXE. El batch actualizado copia Data.xlsx y Mapeo.xlsx a la
nueva distribucion. Usar la carpeta dist/InjectFlow completa, sin mezclar
el EXE viejo con los catalogos nuevos.

No se ejecuto Windows, WinForms ni Excel COM en este entorno Linux.
La verificacion final de generacion, impresion y vista previa en el EXE
debe realizarse en el PC del usuario.
