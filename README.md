# InjectFlow

**InjectFlow** es una aplicación de escritorio desarrollada en Python para automatizar la generación de hojas de parámetros de proceso de máquinas de inyección Haitian.

El sistema interpreta los archivos de parámetros descargados directamente de la máquina, convierte los valores internos a las unidades mostradas en el HMI y escribe automáticamente la información en plantillas Excel estandarizadas.

> **Versión actual:** InjectFlow v3.0.0 — Release 3.0  
> **Repositorio:** https://github.com/ProcesosCazel/InjectFlow  
> **Autor:** Ing. José Antonio Guzmán Trujillo  
> **Cargo:** Becario de Procesos  
> **Contacto:** tecnicosprocesos@cazel.mx

---

## Objetivo

Reducir el tiempo y los errores asociados con la elaboración manual de hojas de parámetros de proceso, manteniendo una estructura de Excel estandarizada para distintas generaciones y configuraciones de máquinas Haitian.

InjectFlow automatiza, entre otros:

- Apertura y cierre de molde.
- Protección de molde.
- Inyección.
- Sostenimiento.
- Transferencia.
- Dosificación / carga.
- Descompresión.
- Temperaturas de barril.
- Hot Runner System (HRS).
- Valve Gates.
- Cores.
- Mesa rotatoria en máquinas TwoShot.
- Datos generales de molde y máquina.
- Activación, desactivación y sombreado dinámico de campos.
- Total dinámico de zonas HRS.

---

## Máquinas y familias soportadas

### Haitian Zeres

El proyecto conserva soporte para las familias previamente validadas:

- Haitian Zeres Gen V.
- Haitian Zeres Gen III 500.
- Haitian Zeres Gen III 800.
- Haitian Zeres Gen III 1080.

Las plantillas correspondientes se encuentran en:

```text
plantillas/
├── Haitian Zeres Gen V.xlsx
├── Haitian Zeres Gen III_500.xlsx
├── Haitian Zeres Gen III_800.xlsx
└── Haitian Zeres Gen III_1080.xlsx
```

### Haitian Jupiter TwoShot

A partir de Release 3.0 se agregó soporte para:

- Máquina **308B**.
- Máquina **309**.

Plantilla:

```text
plantillas/Haitian Jupiter TwoShot_1080.xlsx
```

Para Jupiter, la entrada de proceso es únicamente el archivo `.xml` del molde.

Las constantes físicas y de conversión de cada máquina están integradas internamente en el proyecto; el operador no necesita descargar archivos adicionales de configuración para generar cada hoja.

---

## Flujo de trabajo

### Zeres

Dependiendo de la máquina y configuración seleccionada, InjectFlow utiliza los archivos de parámetros correspondientes, por ejemplo:

```text
Param.dat
Resul.csv
```

Cuando aplica, `Resul.csv` se utiliza para calcular valores resultantes/promedios configurados por el proyecto.

### Jupiter TwoShot

El flujo de trabajo es:

```text
XML del molde
    ↓
Interpretación de parámetros
    ↓
Aplicación de constantes internas de la máquina
    ↓
Conversión a valores HMI
    ↓
Mapeo a plantilla Excel
    ↓
Hoja de parámetros
```

El usuario solo selecciona:

1. Máquina.
2. Número de molde.
3. Archivo `.xml`.

El número de molde capturado por el usuario se utiliza tal como fue ingresado y no se valida contra el número contenido en el XML.

---

## Conversiones Jupiter

La lógica de Jupiter fue reconstruida utilizando los archivos reales de configuración de las máquinas 308B y 309.

Entre las conversiones implementadas se encuentran:

- Posición de husillo mediante volumen y carrera.
- Presión de inyección y sostenimiento mediante relación de áreas hidráulicas.
- Velocidad de inyección según el transformador HMI configurado por máquina.
- RPM / velocidad relativa de carga.
- Clamp Force.
- Mold Release Pressure.
- Velocidad de cores.
- Apertura y cierre de molde.
- Modos de transferencia.
- Modos de decompression.
- Modos y secuencias de cores.
- Valve Gates.
- HRS.
- Mesa rotatoria.

La lógica de 308B y 309 se mantiene separada cuando sus transformadores HMI o constantes son diferentes.

---

## Hot Runner System

El programa determina dinámicamente las zonas HRS activas.

Ejemplos validados:

```text
117B  → TOTAL: 2 ZONAS
308B  → TOTAL: 16 ZONAS
309   → TOTAL: 19 ZONAS
```

`HRSTotalZonesText` es un valor derivado por el programa y no se busca directamente dentro de los archivos `.dat` o `.xml`.

---

## Estructura del proyecto

```text
AutomatizacionParametros_v3.0/
│
├── app/
│   ├── main.py
│   ├── jupiter_xml_parser.py
│   ├── catalogs.py
│   └── ...
│
├── data/
│   ├── Data.xlsx
│   ├── Mapeo.xlsx
│   └── Moldes.xlsx
│
├── plantillas/
│   ├── Haitian Jupiter TwoShot_1080.xlsx
│   ├── Haitian Zeres Gen V.xlsx
│   ├── Haitian Zeres Gen III_500.xlsx
│   ├── Haitian Zeres Gen III_800.xlsx
│   └── Haitian Zeres Gen III_1080.xlsx
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
├── requirements.txt
├── requirements-build.txt
├── VERSION.txt
└── README.md
```

---

## Requisitos

- Windows 10/11.
- Python 3.x.
- Microsoft Excel instalado para el flujo de escritura basado en Excel COM.
- Dependencias indicadas en `requirements.txt`.

Para instalar dependencias:

```powershell
pip install -r requirements.txt
```

O ejecutar:

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

También puede utilizarse:

```text
ABRIR_INJECTFLOW.bat
```

---

## Crear el ejecutable

Ejecutar:

```text
CREAR_INJECTFLOW_EXE.bat
```

El proceso utiliza PyInstaller y genera:

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

> **Importante:** para distribuir InjectFlow debe copiarse la carpeta completa `dist\InjectFlow`, no solamente `InjectFlow.exe`.

El ejecutable necesita conservar junto a él los recursos externos de:

- `data/`
- `plantillas/`
- `web/`

El batch de Release 3.0 valida que estos recursos hayan sido copiados correctamente.

---

## Archivos principales de configuración

### `data/Data.xlsx`

Contiene:

- Reglas de parámetros.
- Transformaciones.
- State Maps.
- Configuración por familia.
- Constantes internas de Jupiter.
- Reglas derivadas.

### `data/Mapeo.xlsx`

Define:

- Destino de cada parámetro en las plantillas.
- Reglas de activación.
- Reglas de sombreado.
- Lógica de cores.
- Lógica de zonas.
- Referencias visuales.

Para la plantilla Jupiter final:

```text
G17 = referencia de campo activo / sin relleno
G20 = referencia de campo inactivo / gris #7F7F7F
```

### `data/Moldes.xlsx`

Catálogo auxiliar de moldes y datos asociados.

La existencia de un número de molde en este catálogo no es obligatoria para generar una hoja.

---

## Plantilla Jupiter

La plantilla oficial es:

```text
Haitian Jupiter TwoShot_1080.xlsx
```

Las etiquetas físicas de Injection/Hold:

```text
1
2
3
End
```

forman parte de la plantilla y no deben ser escritas ni borradas por el programa.

Los campos inactivos utilizan:

```text
#7F7F7F
```

---

## Validación de Release 3.0

La versión fue validada utilizando archivos reales de proceso de las máquinas soportadas.

### 308B / I-1689

Se validaron:

- XML real.
- Cores A/B.
- HRS.
- Valve Gates.
- Injection 1 / Injection 2.
- Mesa rotatoria.
- Transferencia.
- Charge.
- Decompression.

### 309 / I-1695

Se validaron:

- XML real.
- Cores A/B.
- HRS.
- 9 Valve Gates activas.
- Injection 1 / Injection 2.
- Mesa rotatoria.
- Transferencia.
- Charge.
- Decompression.

También se realizó regresión sobre máquinas Zeres para evitar que la lógica Jupiter interfiera con las familias existentes.

---

## Correcciones posteriores al tag v3.0

Después del tag inicial `v3.0` se incorporaron correcciones en `main`.

### HRS Total Zones

Se corrigió una condición donde una máquina Zeres podía intentar resolver:

```text
Jupiter.HRSTotalZonesText
```

La lógica actual calcula este valor después de interpretar las zonas HRS y no lo solicita directamente al archivo de máquina.

### Build del EXE

Se corrigió `CREAR_INJECTFLOW_EXE.bat` para garantizar que `dist\InjectFlow` incluya:

- `web/`
- `data/`
- `plantillas/`
- recursos estáticos necesarios.

El batch también elimina un build incompleto si ocurre un error durante la copia de recursos.

---

## Git / GitHub

Repositorio:

```text
https://github.com/ProcesosCazel/InjectFlow
```

Rama principal:

```text
main
```

Tag principal:

```text
v3.0
```

Para revisar el estado local:

```powershell
git status
```

Para actualizar GitHub después de realizar cambios:

```powershell
git add <archivos>
git commit -m "Descripción del cambio"
git push origin main
```

---

## Recomendaciones de desarrollo

Antes de modificar el proyecto:

1. Crear respaldo o commit.
2. No modificar plantillas validadas sin confirmar el impacto en `Mapeo.xlsx`.
3. Mantener separada la lógica Zeres y Jupiter.
4. No introducir factores de conversión empíricos si existe una constante real de máquina.
5. Ejecutar pruebas de regresión después de modificar parser, resolver, mapeo o plantillas.
6. Probar el EXE después de cualquier cambio en `web`, PyInstaller o el batch de compilación.

---

## Estado actual

InjectFlow v3.0 permite generar hojas de parámetros de proceso para familias Haitian Zeres y Haitian Jupiter TwoShot utilizando los archivos descargados de las máquinas y las reglas de conversión/mapeo validadas durante el desarrollo.

El proyecto continúa en evolución y cualquier nueva máquina debe validarse contra su archivo real de proceso y una hoja HMI de referencia antes de habilitarse para uso normal.
