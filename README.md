# InjectFlow

**InjectFlow** es una aplicación de escritorio desarrollada en Python para automatizar la generación de hojas de parámetros de proceso en máquinas de inyección de plástico.

El proyecto interpreta archivos de parámetros descargados directamente de las máquinas, aplica reglas de conversión y lógica de proceso, y escribe automáticamente los resultados en plantillas Excel estandarizadas.

Su objetivo principal es reducir tiempo de captura, evitar errores manuales y mantener un formato uniforme para las hojas de parámetros utilizadas en producción.

> **Versión actual:** InjectFlow v3.0.0 — Release 3.0  
> **Repositorio:** https://github.com/ProcesosCazel/InjectFlow  
> **Autor:** Ing. José Antonio Guzmán Trujillo  
> **Cargo:** Becario de Procesos  
> **Contacto:** tecnicosprocesos@cazel.mx

---

## Objetivo del proyecto

InjectFlow fue creado para sustituir la captura manual de parámetros de proceso en Excel por un flujo automatizado y repetible.

El sistema permite:

- Seleccionar la máquina de inyección.
- Cargar el archivo de parámetros correspondiente.
- Interpretar los valores internos de la máquina.
- Convertirlos a las unidades mostradas en el HMI.
- Aplicar reglas específicas por familia o modelo de máquina.
- Activar o desactivar secciones según la configuración real del proceso.
- Escribir los valores en la plantilla correcta.
- Conservar formato, celdas combinadas, sombreado y área de impresión.
- Generar una hoja final lista para revisión, impresión o resguardo.

---

## Alcance actual

InjectFlow soporta actualmente diferentes configuraciones de máquinas Haitian, incluyendo:

### Haitian Zeres

- Haitian Zeres Gen V.
- Haitian Zeres Gen III 500.
- Haitian Zeres Gen III 800.
- Haitian Zeres Gen III 1080.

### Haitian Jupiter

- Haitian Jupiter TwoShot 1080.
- Máquinas actualmente validadas: 308B y 309.

La arquitectura del proyecto permite incorporar nuevas máquinas, generaciones y plantillas sin modificar el flujo principal de uso.

---

## Flujo general

El flujo de InjectFlow puede resumirse así:

```text
Archivo de máquina
      ↓
Selección de máquina
      ↓
Parser correspondiente
      ↓
Conversión de unidades
      ↓
Aplicación de reglas de proceso
      ↓
Mapeo de parámetros
      ↓
Plantilla Excel
      ↓
Hoja de parámetros terminada
```

Dependiendo de la familia de máquina, la entrada puede ser:

```text
.dat
.xml
.csv
```

El programa determina qué parser y qué reglas utilizar de acuerdo con la máquina seleccionada.

---

## Parámetros automatizados

Dependiendo de la máquina y la plantilla, InjectFlow puede procesar automáticamente:

- Datos generales de máquina.
- Datos de molde.
- Apertura de molde.
- Cierre de molde.
- Protección de molde.
- Fuerza de cierre.
- Inyección.
- Sostenimiento.
- Transferencia.
- Tiempo de inyección.
- Tiempo de enfriamiento.
- Dosificación / carga.
- Contrapresión.
- RPM o velocidad de rotación.
- Descompresión.
- Temperaturas de barril.
- Hot Runner System (HRS).
- Valve Gates.
- Cores.
- Mesa rotatoria.
- Tiempos de secuencia.
- Modos de operación.
- Campos activos e inactivos.
- Totales dinámicos de zonas.

No todas las máquinas utilizan todas estas funciones.

---

## Interpretación de datos

Los valores almacenados en los archivos descargados de máquina no siempre están expresados en las mismas unidades que aparecen en el HMI.

Por ello, InjectFlow incluye lógica para:

- Conversión de presión.
- Conversión de posición.
- Conversión de velocidad.
- Conversión de tiempo.
- Conversión de volumen.
- Conversión de RPM.
- Conversión de fuerza.
- Traducción de estados y modos.
- Interpretación de perfiles por etapas.
- Identificación de parámetros activos e inactivos.

Cuando existe información física real de la máquina, las conversiones se basan en esas constantes y no en factores arbitrarios.

---

## Arquitectura del proyecto

```text
AutomatizacionParametros_v3.0/
│
├── app/
│   ├── main.py
│   ├── jupiter_xml_parser.py
│   ├── catalogs.py
│   ├── plan.py
│   └── ...
│
├── data/
│   ├── Data.xlsx
│   ├── Mapeo.xlsx
│   └── Moldes.xlsx
│
├── plantillas/
│   ├── Haitian Zeres Gen V.xlsx
│   ├── Haitian Zeres Gen III_500.xlsx
│   ├── Haitian Zeres Gen III_800.xlsx
│   ├── Haitian Zeres Gen III_1080.xlsx
│   └── Haitian Jupiter TwoShot_1080.xlsx
│
├── web/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/
│
├── tests/
├── build_tools/
├── input/
├── output/
│
├── ABRIR_INJECTFLOW.bat
├── CREAR_INJECTFLOW_EXE.bat
├── INSTALAR_DEPENDENCIAS.bat
├── InjectFlow.spec
├── launcher_web.py
├── requirements.txt
├── requirements-build.txt
├── VERSION.txt
└── README.md
```

---

## Componentes principales

### `app/`

Contiene la lógica principal del programa:

- Lectura de archivos.
- Parsers.
- Conversión de datos.
- Selección de plantilla.
- Construcción del plan de escritura.
- Aplicación de reglas de proceso.
- Comunicación con la interfaz.

### `data/Data.xlsx`

Contiene el catálogo lógico del sistema:

- Parámetros.
- Claves de origen.
- Transformaciones.
- State Maps.
- Reglas de conversión.
- Constantes de máquina.
- Configuración de comportamiento.

### `data/Mapeo.xlsx`

Define dónde debe escribirse cada parámetro en cada plantilla.

También contiene reglas relacionadas con:

- Activación de campos.
- Sombreado.
- HRS.
- Cores.
- Valve Gates.
- Secciones dinámicas.
- Referencias de formato.

### `data/Moldes.xlsx`

Catálogo auxiliar de moldes.

Puede utilizarse para completar información adicional, pero el programa no requiere que todos los moldes existan previamente en este archivo.

El número de molde ingresado por el usuario se respeta como valor principal.

### `plantillas/`

Contiene las hojas Excel oficiales utilizadas para generar los documentos finales.

Las plantillas deben conservar:

- Celdas combinadas.
- Formatos.
- Bordes.
- Fórmulas.
- Rellenos.
- Escala.
- Área de impresión.
- Etiquetas fijas.

La lógica del programa debe adaptarse a la plantilla, no al contrario.

### `web/`

Contiene la interfaz visual de InjectFlow:

- HTML.
- CSS.
- JavaScript.
- Imágenes y recursos.

Estos archivos deben permanecer junto al ejecutable cuando se distribuye la aplicación.

---

## Hot Runner System

InjectFlow determina dinámicamente las zonas HRS activas.

El texto de total de zonas se calcula internamente a partir del estado real de las zonas.

Ejemplo:

```text
TOTAL: 2 ZONAS
TOTAL: 16 ZONAS
TOTAL: 19 ZONAS
```

Este valor no se busca directamente en el archivo de máquina.

---

## Campos activos e inactivos

El programa controla visualmente los campos que aplican al proceso.

Cuando un parámetro está activo:

- Se habilita visualmente.
- Se escribe el valor correspondiente.

Cuando no aplica:

- Puede dejarse vacío.
- Puede conservar o recibir relleno gris según la plantilla.

Cada plantilla tiene referencias de formato definidas en `Mapeo.xlsx`.

---

## Requisitos

- Windows 10 o Windows 11.
- Python 3.x para ejecución desde código fuente.
- Microsoft Excel instalado para las operaciones que requieren Excel COM.
- Dependencias indicadas en `requirements.txt`.

Instalación:

```powershell
pip install -r requirements.txt
```

También puede utilizarse:

```text
INSTALAR_DEPENDENCIAS.bat
```

---

## Ejecutar desde código fuente

Desde Windows PowerShell:

```powershell
cd "C:\ruta\al\proyecto\AutomatizacionParametros_v3.0"
python launcher_web.py
```

O ejecutar:

```text
ABRIR_INJECTFLOW.bat
```

---

## Crear el ejecutable

Para generar la versión distribuible:

```text
CREAR_INJECTFLOW_EXE.bat
```

El proceso utiliza PyInstaller.

La salida esperada es:

```text
dist/
└── InjectFlow/
    ├── InjectFlow.exe
    ├── _internal/
    ├── data/
    ├── plantillas/
    ├── web/
    ├── input/
    └── output/
```

### Importante

Debe distribuirse la carpeta completa:

```text
dist\InjectFlow
```

No solamente:

```text
InjectFlow.exe
```

La aplicación necesita los recursos externos ubicados en:

```text
data/
plantillas/
web/
```

El batch de compilación valida que estos recursos hayan sido copiados correctamente.

---

## Validación y pruebas

El proyecto contiene pruebas automatizadas dentro de:

```text
tests/
```

Las pruebas cubren, entre otros:

- Parsers.
- Conversiones.
- Catálogos.
- Mapeos.
- Plan de escritura.
- Lógica dinámica.
- Compatibilidad entre familias.
- Preview.
- Regresión.

Además de las pruebas automáticas, cada nueva máquina debe validarse con:

1. Archivo real descargado de la máquina.
2. Hoja de parámetros o HMI de referencia.
3. Comparación de valores generados.
4. Prueba final en Windows con Microsoft Excel.

---

## Incorporación de nuevas máquinas

Para agregar una nueva máquina al sistema se recomienda:

1. Obtener un archivo de parámetros real.
2. Obtener una hoja de referencia validada.
3. Identificar la familia y generación.
4. Analizar unidades internas.
5. Identificar constantes físicas si son necesarias.
6. Definir o reutilizar parser.
7. Agregar reglas a `Data.xlsx`.
8. Agregar mapeos a `Mapeo.xlsx`.
9. Validar la plantilla.
10. Ejecutar pruebas de regresión.
11. Habilitar la máquina únicamente después de confirmar los resultados.

---

## Reglas de mantenimiento del proyecto

Para evitar regresiones:

- No modificar una plantilla oficial sin revisar `Mapeo.xlsx`.
- No utilizar factores empíricos si existe una constante real de máquina.
- Mantener separada la lógica específica por familia.
- No asumir que todas las generaciones utilizan las mismas conversiones.
- Mantener los campos fijos dentro de la plantilla cuando corresponda.
- Probar una familia después de modificar otra.
- Ejecutar pruebas antes de publicar una nueva versión.
- Probar nuevamente la creación del `.exe` después de modificar recursos web o configuración de PyInstaller.

---

## Control de versiones

Repositorio:

```text
https://github.com/ProcesosCazel/InjectFlow
```

Rama principal:

```text
main
```

Release principal:

```text
v3.0
```

Flujo recomendado para cambios:

```powershell
git status
git add <archivos>
git commit -m "Descripción del cambio"
git push origin main
```

Los cambios posteriores al tag `v3.0` pueden mantenerse como correcciones sobre `main` hasta que se defina una nueva versión.

---

## Estado del proyecto

InjectFlow v3.0 se encuentra operativo para la generación automatizada de hojas de parámetros en las familias actualmente soportadas.

El enfoque del proyecto es mantener una plataforma extensible donde nuevas máquinas puedan integrarse mediante:

```text
Parser
+ Reglas
+ Mapeo
+ Plantilla
+ Validación
```

sin reconstruir la aplicación completa para cada nuevo modelo.

---

## Autor

**Ing. José Antonio Guzmán Trujillo**  
Becario de Procesos  
CAZEL  
tecnicosprocesos@cazel.mx
