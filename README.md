# L4D2 Mod Loader — Versus

Herramienta para gestionar addons de **Left 4 Dead 2** sin tener que modificar Steam ni utilizar la consola.

Elige los mods que quieres utilizar en tu partida de Versus, actívalos y pulsa **JUGAR**.

## Características

* 📦 **Explora tus addons del Workshop**: títulos, descripciones e imágenes de preview descargadas desde la API pública de Steam, con caché en disco.
* ✅ **Activa/desactiva mods**: gestiona las rutas en `gameinfo.txt` mediante la sección `SearchPaths`, copiando los VPK a `mods/<id>/pak01_dir.vpk`.
* 🔄 **Activación acumulativa**: mantiene intactos los mods que ya estaban activos al agregar nuevos addons.
* 🏷️ **Detección MOD / VSCRIPT**: analiza el árbol del VPK (formato Source VPK v1) para identificar si un addon es un mod normal o un script.
* 🗂️ **Categorías automáticas**: Skins / Armas / Sonido / UI / Otro, además de un filtro dedicado para VScripts.
* ⭐ **Favoritos y presets**: guarda combinaciones de addons activos para reutilizarlas rápidamente.
* 🔗 **Dependencias**: detecta y sugiere requisitos entre addons, incluyendo dependencias transitivas y protección contra ciclos.
* 👁️ **Visión de infectado**: permite quitar o restaurar el tinte naranja/azul de los infectados.
* 🧹 **Limpieza**: elimina addons huérfanos o desuscritos y permite restaurar el `gameinfo.txt` original mediante backups automáticos.
* 🔍 **Watcher automático**: detecta cuando Steam descarga o elimina VPKs y actualiza la lista sin reiniciar la aplicación.
* 🛡️ **Guard de juego abierto**: bloquea modificaciones mientras Left 4 Dead 2 está ejecutándose.

## Requisitos

### Para usuarios

* Windows
* Left 4 Dead 2 instalado mediante Steam
* Permisos de administrador cuando el juego esté instalado en `Program Files`

**No necesitas instalar Python ni ejecutar comandos para utilizar la versión `.exe`.**

### Para desarrolladores

Si quieres ejecutar el proyecto desde el código fuente:

* Windows
* Python 3.10+
* Left 4 Dead 2 instalado mediante Steam

## Descargar

Descarga la última versión del ejecutable desde la sección **Releases**.

El programa se distribuye como un ejecutable standalone, por lo que el usuario final no necesita instalar Python ni Flet.

## Cómo ejecutar desde el código fuente

```bash
pip install -r requirements.txt
python main.py
```

## Cómo empaquetarlo como `.exe` standalone

Instala las dependencias:

```bash
pip install -r requirements.txt
```

Después ejecuta:

```bash
pyinstaller --clean "L4D2 Mod Loader.spec"
```

El ejecutable se generará en:

```text
dist/
```

## Notas

* Si Left 4 Dead 2 está instalado dentro de `Program Files`, ejecuta la aplicación **como administrador** para permitir modificaciones en `gameinfo.txt`.
* El programa crea backups automáticos antes de modificar `gameinfo.txt`.
* Los addons de tipo VSCRIPT pueden no funcionar correctamente mediante este método de activación.
* La información e imágenes de los addons del Workshop pueden requerir conexión a Internet cuando todavía no están disponibles en la caché local.
* El programa bloquea las modificaciones mientras Left 4 Dead 2 está abierto para evitar conflictos con los archivos del juego.

## Créditos

Hecho por **Tokyossz**.
