# InjectFlow v3.0 - Compatibilidad de plantillas

Revisión: **2026-10-15**.

## Base y alcance

Se inspecciono la base completa disponible `AutomatizacionParametros_v3.0_startup_fix.zip` y se aplico el delta validado `InjectFlow_v3.0_ValveGate_103_Fix_Delta.zip`. No se accedio al checkout de Windows ni se modifico GitHub. La entrega es incremental: no sustituye el maestro productivo `Moldes.xlsx`, `Data.xlsx` ni codigo de ejecucion.

## Problema reproducido

La nueva plantilla Gen III_500 incorpora `A75:Q81`, por lo que pasa de 544 a 545 combinaciones. El validador anterior rechazo esta plantilla con:

```text
Merged range count changed: expected 544, found 545
```

La correccion esta en `Mapeo.xlsx`, hoja `Templates`, celda `M3`: **544 -> 545**. No se desactiva la validacion estricta. El test negativo nuevo confirma que registrar 544 con la plantilla actual sigue fallando.

## Cambios observados por plantilla

| Plantilla | Revision observada | Ajuste de compatibilidad |
|---|---|---|
| Jupiter TwoShot_1080 | Nota de referencia/no auditable en A76 y ajustes de formato. | Se conserva el contenido original; no hay desplazamiento de destinos. |
| Zeres Gen III_500 | Nuevo aviso en A75:Q81. | Se actualiza a 545 combinaciones. |
| Zeres Gen III_800 | El contenido interno del XLSX coincide con la base comparada. | Se registra y entrega el archivo recibido. |
| Zeres Gen III_1080 | El contenido interno del XLSX coincide con la base comparada. | Se registra y entrega el archivo recibido. |
| Zeres Gen V | OBSERVACIONES se mueve a U78:AV78; texto a U79:AV82. | Es contenido fijo, fuera de las escrituras; no requiere mover parametros. |

Los avisos se mantienen como texto de plantilla. No se dedujo de ellos que deban eliminarse parametros de prensa o expulsor.

## Cambios en Mapeo.xlsx

- Templates: M3 y las cinco firmas SHA-256 N2:N6; notas de revision O2:O6.
- Audit: descripciones vigentes en C2, C3, C24, C31 y C35, y nueva entrada de revision.
- README: nueva entrada explicativa de la revision.
- Se preservaron las otras once hojas, incluidas Mapping, ZoneRules, CoreLogic, CoreLayout, ValveGateLogic/Layout/Fields, Machines y ManualInputs.
- Todos los estilos de celdas preexistentes del catalogo se compararon y permanecen iguales. No contiene formulas que requieran recalculo.
- Los SHA-256 sirven para identificar esta revision y se verifican en las nuevas pruebas; no se agrego una comprobacion de hash al writer ni se altero su funcionamiento.

## Inspeccion de referencias

| Plantilla | Combinaciones | Referencias revisadas | Celdas únicas | Anclas inválidas |
|---|---:|---:|---:|---:|
| Haitian Zeres Gen V.xlsx | 565 | 352 | 277 | 0 |
| Haitian Zeres Gen III_500.xlsx | 545 | 309 | 236 | 0 |
| Haitian Zeres Gen III_1080.xlsx | 738 | 451 | 378 | 0 |
| Haitian Zeres Gen III_800.xlsx | 738 | 451 | 378 | 0 |
| Haitian Jupiter TwoShot_1080.xlsx | 730 | 396 | 342 | 0 |

Se revisaron **1959 referencias** (1611 celdas unicas contando cada layout por separado). Las referencias incluyen destinos estaticos, layouts dinamicos, identificadores, etiquetas y rellenos. Ninguna apunta al interior no-ancla de una combinacion ni a los avisos protegidos.

Las cinco plantillas pasan `validate_template(..., strict=True)` sin advertencias. Se mantienen las areas de impresion, orientacion, escala y formulas originales. Se revisaron vistas renderizadas de las cinco plantillas y del catalogo; no equivalen a una impresion nativa de Excel.

Las formulas de piezas/hora de Zeres ya existentes dividen por un ciclo vacio en la plantilla sin llenar. No se reescribieron: el flujo de solo parametros limpia estas formulas dependientes y se incluyo esta ruta en las pruebas.

## Planes con archivos reales

| Máquina en catalogo | Molde | Operaciones | Advertencias | Faltantes | Plan frente a base |
|---|---|---:|---:|---:|---|
| 103A | I-1954 | 433 | 0 | 0 | Identico byte por byte |
| 117B | I-1625 | 441 | 0 | 0 | Identico byte por byte |
| 308B | I-1689 | 693 | 0 | 0 | Identico byte por byte |
| 309 | I-1695 | 753 | 0 | 0 | Identico byte por byte |

La 103 del usuario corresponde a `103A` en el catalogo disponible. Se ejecuto el motor real con `--plan-only --param-only`, y control de inyeccion 0 en DAT. Se conservaron el fix de Valve Gates 103, la separacion de fuentes Zeres/Jupiter y el total HRS. La identidad de planes demuestra que esta actualizacion no altera los valores ni las operaciones ya obtenidas; no representa una nueva medicion del HMI.

Gen V y Gen III_800/_1080 se validaron estructuralmente y con planes sinteticos en estados inactivo/completo. No se dispuso de nuevas recetas reales para esos tres layouts.

## Pruebas ejecutadas

Base, sin UI en este proceso:

```text
python -m pytest -vv -ra -k "not test_ui"
162 passed, 4 deselected in 30.03s
```

Estado final, ejecuciones separadas:

```text
python -m pytest -vv -ra -k "not test_ui"
204 passed, 4 deselected in 53.37s

python -m pytest -vv -ra tests/test_jupiter_integration.py -k test_ui
4 passed, 37 deselected in 6.04s
```

**208 pruebas distintas aprobadas: 204 de logica + 4 de interfaz. Cero fallos en esas ejecuciones.** Las deseleccionadas no se cuentan como aprobadas en su proceso; se cubren en el otro bloque. Los 42 casos nuevos estan incluidos en las 204 pruebas de logica, no se suman otra vez.

Los nuevos casos cubren registro de plantillas, hash, destinos y rellenos, proteccion de observaciones, planes sinteticos con/sin resultantes, slots activos/inactivos, etiquetas fijas y rechazo del conteo antiguo de combinaciones. No leen el maestro Moldes.xlsx productivo como fixture.

Tambien se ejecuto `compileall` sobre app, tests, launcher_web.py, loading_screen.py, web_api.py y preview_renderer.py sin errores.

Las ejecuciones de suite completa en un solo proceso no se usaron como evidencia: excedieron el tiempo limite de esta herramienta. Los resultados declarados son los de los dos bloques que si terminaron.

## Integridad y archivos protegidos

Cada plantilla entregada tiene exactamente los mismos bytes que su adjunto original, solo cambia el nombre de archivo para usar el nombre canonico que espera el programa. Las cinco plantillas y Mapeo.xlsx pasaron la comprobacion interna ZIP.

No se cambiaron: app/main.py, app/resolver.py, parsers, planner, writer, launcher, interfaz web, batch de compilacion, Data.xlsx ni Moldes.xlsx. Los fixes anteriores se conservaron en la base utilizada para las pruebas; el delta no los vuelve a reemplazar.

## Limites de la validacion

No se ejecuto Microsoft Excel COM ni el EXE nativo Windows en este entorno Linux. Los tests de interfaz son headless Chromium; los ensayos de plantillas aplican planes a copias temporales mediante openpyxl. Es necesario comprobar una generacion final en el PC de Windows, especialmente impresion/vista previa y recursos de la distribucion.

## Instalacion

Ver README_ACTUALIZACION_PLANTILLAS.txt. Actualizar data/Mapeo.xlsx y las cinco plantillas tanto en el proyecto como en dist/InjectFlow cuando se usa un EXE ya compilado. Al ser datos externos y no cambios de codigo productivo, esta revision no requiere recompilar el EXE existente.

## SHA-256 de los archivos funcionales del delta

- `data/Mapeo.xlsx`: `065edacd83dc22cb83629034ddef6ec235ef4bcce13b09b082dddc68db0bec58`
- `plantillas/Haitian Jupiter TwoShot_1080.xlsx`: `e763ca4e75a79f704b99b20b02f9f76ac153935ce5a011e53749504dbc17f87f`
- `plantillas/Haitian Zeres Gen III_500.xlsx`: `13070306b7373fb5456a2a880c453f06f1fd9f0476582a0ed941ac62b3a595aa`
- `plantillas/Haitian Zeres Gen III_800.xlsx`: `23c8709bb064df0ac709b1378e23e2d2fa778c2e277b2555f325685143ee838d`
- `plantillas/Haitian Zeres Gen III_1080.xlsx`: `3bc0fbe813ad2e7880303a995251b26daec82d1e44c0e68ce31e27cc1ab26704`
- `plantillas/Haitian Zeres Gen V.xlsx`: `0eff30c4f827d5c5a31afccb08591af6bb680ac7d7d8161c07f1bffa0a40caa1`
- `tests/test_template_compatibility.py`: `39d1475a60f9d073ac99de014c0b8b49b3a8b4841c263304230f18f98fb38487`
