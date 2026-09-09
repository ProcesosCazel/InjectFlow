# InjectFlow v2.0

**Automatización de hojas de parámetros de proceso para máquinas de inyección**

InjectFlow es una aplicación de escritorio desarrollada en Python que automatiza la generación de hojas de parámetros de proceso a partir de archivos exportados por máquinas de inyección.

La versión **2.0.0** representa la primera release estable de la interfaz InjectFlow basada en **PyWebView**, manteniendo la lógica de proceso validada de `AutomatizacionParametros_v1.3`.

> **Estado:** FINAL RELEASE  
> **Versión:** 2.0.0  
> **Plataforma principal:** Windows  
> **Uso del repositorio:** referencia técnica

---

## Objetivo

Reducir el trabajo manual requerido para llenar las hojas oficiales de parámetros de proceso, conservando:

- formatos de Excel;
- tamaños de filas y columnas;
- celdas combinadas;
- colores, rellenos y bordes;
- formatos decimales;
- configuración de impresión;
- reglas específicas por familia de máquina;
- lógica de zonas, cores y Valve Gates;
- historial de hojas generadas.

Flujo general:

```text
Máquina de inyección
        │
        ├── Param.dat
        └── Resul.csv (opcional)
                │
                ▼
            InjectFlow
                │
        ┌───────┴────────┐
        │                │
    Data.xlsx        Mapeo.xlsx
        │                │
        └───────┬────────┘
                │
            Plantilla
                │
                ▼
      HojaDeParametros.xlsx
```

---

## Características principales

### Generación automática

InjectFlow procesa los archivos exportados por la máquina y genera automáticamente la hoja oficial de parámetros.

Entradas principales:

- `Param.dat`
- `Resul.csv` opcional
- `Data.xlsx`
- `Mapeo.xlsx`
- plantilla correspondiente a la máquina

Salida:

- archivo `.xlsx` generado en `output/`

---

## Máquinas soportadas en v2.0

### Haitian Zeres Gen V

```text
112C
114B
114C
124
125
126
129
130
```

Grupo lógico:

```text
HAITIAN_ZE_V
```

Plantilla:

```text
Haitian Zeres Gen V.xlsx
```

Características principales:

- hasta 2 cores;
- hasta 4 Valve Gates activos;
- 40 zonas HRS;
- SuckBack configurable;
- PreRelease configurable;
- Hold Advanced para cores;
- lógica dinámica de zonas;
- soporte de modo Solo Param.dat.

### Haitian Zeres Gen III

```text
101
102
103
104
105
106
107
108
111B
111C
113C
115
116
117
123
127
128
131
```

Grupo lógico:

```text
HAITIAN_ZE_III
```

Plantilla:

```text
Haitian Zeres Gen III.xlsx
```

Características principales:

- máximo 1 core activo;
- 28 zonas HRS;
- SuckBack siempre activo;
- sin PreRelease;
- mapas específicos de Valve Gates Gen III;
- soporte de modo Solo Param.dat.

---

## Interfaz InjectFlow

La interfaz de v2.0 utiliza:

- Python
- PyWebView
- HTML
- CSS
- JavaScript

Arquitectura:

```text
Python
│
├── lógica
├── lectura de archivos
├── resolución de parámetros
├── reglas de máquinas
├── generación Excel
├── historial
├── preview
└── API hacia la interfaz

JavaScript
└── estado y comportamiento visual de la interfaz

HTML
└── estructura de las pantallas

CSS
└── presentación visual
```

> Las reglas de proceso permanecen en Python. JavaScript no contiene reglas específicas de Gen V, Gen III, cores o Valve Gates.

---

## Funciones de la interfaz

### Home

Permite:

- seleccionar máquina;
- seleccionar control de inyección;
- ingresar número de molde;
- cargar `Param.dat`;
- cargar `Resul.csv`;
- generar la hoja;
- abrir la hoja recién generada;
- abrir la carpeta de salida;
- visualizar Vista Previa;
- acceder al historial.

### Drag & Drop

Los archivos pueden cargarse mediante:

- botón de selección;
- Drag & Drop nativo de PyWebView.

Extensiones aceptadas:

```text
Param → .dat
Resul → .csv
```

La validación de extensión no distingue entre mayúsculas y minúsculas.

---

## Vista Previa

Después de una generación exitosa, InjectFlow puede mostrar una vista previa real de la hoja.

```text
XLSX generado
    │
    ▼
Excel en segundo plano
    │
    ▼
Exportación temporal a PDF
    │
    ▼
Vista Previa en InjectFlow
```

La vista previa:

- respeta el área de impresión;
- utiliza el archivo generado en la sesión actual;
- se almacena temporalmente en memoria;
- elimina el PDF temporal;
- se invalida cuando se genera una nueva hoja.

---

## Historial

InjectFlow conserva un historial de generaciones en:

```text
data/Historial.csv
```

El historial registra:

- fecha;
- hora;
- máquina;
- molde;
- modo de generación;
- archivo generado;
- disponibilidad del archivo.

La retención configurada es de:

```text
90 días
```

Desde el historial se pueden abrir hojas generadas en sesiones anteriores.

La opción **Borrar historial** elimina únicamente los registros del historial y no elimina los archivos `.xlsx` existentes en `output/`.

---


## Estructura del proyecto

```text
AutomatizacionParametros/
│
├── app/
│   ├── catalogs.py
│   ├── errors.py
│   ├── excel_writer.py
│   ├── history.py
│   ├── main.py
│   ├── parsers.py
│   ├── plan.py
│   ├── plan_debug.py
│   ├── report.py
│   ├── resolver.py
│   ├── template_validation.py
│   └── utils.py
│
├── data/
│   ├── Data.xlsx
│   └── Mapeo.xlsx
│
├── plantillas/
│   ├── Haitian Zeres Gen III.xlsx
│   └── Haitian Zeres Gen V.xlsx
│
├── web/
│   ├── assets/
│   ├── css/
│   ├── js/
│   └── index.html
│
├── tests/
├── input/
├── output/
├── release_tools/
│
├── launcher_web.py
├── loading_screen.py
├── preview_renderer.py
├── web_api.py
├── requirements.txt
├── requirements-build.txt
├── InjectFlow.spec
├── VERSION.txt
└── LEEME.txt
```

---

## Archivos principales

### `Data.xlsx`

Catálogo central de parámetros, conversiones, configuraciones y mapas de estados.

### `Mapeo.xlsx`

Relaciona parámetros, grupos de máquinas, grupos de plantilla, celdas destino y reglas de visualización.

### `app/parsers.py`

Lectura y normalización de los archivos de entrada.

### `app/resolver.py`

Resuelve los valores finales que se utilizarán durante la construcción de la hoja.

### `app/plan.py`

Construye el plan de escritura de la plantilla y aplica reglas dependientes de familia como la traducción de condiciones de Valve Gates.

### `app/excel_writer.py`

Aplica el plan de escritura sobre la plantilla Excel conservando el formato oficial.

### `web_api.py`

Puente entre la interfaz HTML/JavaScript y el backend Python mediante PyWebView.

---


## Requisitos

Entorno de desarrollo validado:

```text
Windows
Python 3.14.x 64-bit
Microsoft Excel instalado
```

Dependencias principales:

```text
pywebview
openpyxl
pywin32
```

Instalación:

```powershell
pip install -r requirements.txt
```

Dependencias de build:

```powershell
pip install -r requirements-build.txt
```

---

## Ejecutar desde código fuente

Desde la raíz del proyecto:

```powershell
python launcher_web.py
```

---

## Construcción del ejecutable

La release v2.0 utiliza PyInstaller en modalidad:

```text
onedir
```

Script de construcción:

```text
CONSTRUIR_EXE_V2.0.bat
```

La distribución resultante utiliza una estructura similar a:

```text
AutomatizacionParametros_v2.0/
│
├── InjectFlow.exe
├── _internal/
├── data/
├── plantillas/
├── web/
├── input/
├── output/
├── VERSION.txt
└── LEEME_RELEASE.txt
```

Los archivos maestros permanecen externos al `.exe` para permitir mantenimiento sin reconstruir la aplicación.

### PyInstaller y PyWin32

La configuración del build incluye imports explícitos requeridos por Excel COM:

```text
pythoncom
pywintypes
win32timezone
win32com
win32com.client
```

---

## Pruebas

La versión 2.0 se congeló con:

```text
21 / 21 pruebas aprobadas
```

Las pruebas cubren áreas como:

- lectura de Param;
- lectura de Resul;
- catálogo;
- resolución;
- lógica de cores;
- Valve Gates;
- modo Solo Param;
- celdas combinadas;
- generación y verificación.

Para ejecutar las pruebas:

```powershell
pytest
```

---

## Estado de la versión

```text
InjectFlow v2.0.0
FINAL RELEASE
```

La versión 2.0 está congelada.

No se agregarán nuevas máquinas ni nuevas funciones a esta versión. Solo se contemplan correcciones de bugs bloqueantes en caso de ser necesarias.

---

## Desarrollo futuro

El desarrollo posterior continúa en:

```text
InjectFlow v2.1
```

La incorporación de nuevas máquinas y nuevos formatos de entrada no forma parte del alcance de v2.0.

---


## Notas

- No modificar `Data.xlsx`, `Mapeo.xlsx` o las plantillas sin validar el impacto en las familias existentes.
- Las reglas de máquina deben mantenerse en Python/configuración y no trasladarse a JavaScript.
- Los archivos generados en `output/` no deben versionarse.
- `data/Historial.csv` es un archivo de ejecución y no debe versionarse.
- Los entornos virtuales, builds y ejecutables se excluyen mediante `.gitignore`.

---

# Autor:

## Ing. José Antonio Guzmán Trujillo
### Becario de Procesos | Industrias Cazel
**tecnicosprocesos@cazel.mx**

---

## Licencia / uso

Este proyecto se comparte con fines educativos, de colaboración técnica y referencia interna.

La información, plantillas y configuraciones asociadas al proceso deben manejarse de acuerdo con las políticas internas aplicables.

---

**InjectFlow v2.0.0**  
Automatización de hojas de parámetros de proceso.
