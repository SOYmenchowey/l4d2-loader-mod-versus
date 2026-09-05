# L4D2 Versus Mod Manager

Gestor gráfico para **habilitar y deshabilitar addons del Steam Workshop** en
**Left 4 Dead 2**, centrado especialmente en el modo **Versus**. Convierte la
tarea de activar mods en algo visual: marca, activa y juega.

##:V: mods en Versus

El núcleo del proyecto es activar/desactivar addons **sin tocar Steam ni la
consola**: elige qué mods quieres llevar a tu partida de Versus, actívalos y
pulsa **JUGAR**.

## Características

- 📦 **Explora tus addons del Workshop**: títulos, descripciones e imágenes de
  preview descargadas desde la API pública de Steam (con caché en disco).
- ✅ **Activa/desactiva mods**: inyecta las rutas en `gameinfo.txt` (sección
  `SearchPaths`) copiando el VPK a `mods/<id>/pak01_dir.vpk`. Mantiene intactos
  los mods ya activos (activación acumulativa).
- 🏷️ **Detección MOD / VSCRIPT**: analiza el árbol del VPK (formato Source
  VPK v1) para saber si un addon es un mod normal o un script.
- 🗂️ **Categorías automáticas**: Skins / Armas / Sonido / UI / Otro, más filtro
  dedicado para VScripts.
- ⭐ **Favoritos y presets**: guarda combinaciones de addons activos.
- 🔗 **Dependencias**: sugiere y resuelve requisitos entre addons (transitivo,
  con protección de ciclos).
- 👁️ **Visión de infectado**: quita/restaura el tinte naranja-azul de los
  infectados.
- 🧹 **Limpieza**: borra addons huérfanos o desuscritos y restaura el
  `gameinfo.txt` original (con backups automáticos).
- 🔍 **Watcher automático**: detecta cuando Steam descarga/elimina VPKs y
  refresca la lista sin reiniciar.
- 🛡️ **Guard de juego abierto**: bloquea cambios si Left 4 Dead 2 está
  corriendo.

## Requisitos

- Windows
- Python 3.10+
- Left 4 Dead 2 instalado vía Steam

## Cómo ejecutar

```bash
pip install -r requirements.txt
python main.py
```

## Cómo empaquetarlo como .exe standalone

```bash
pip install -r requirements.txt
pyinstaller --clean "L4D2 Mod Loader.spec"
```

El ejecutable queda en `dist/`.

## Notas

- Si el juego está en `Program Files`, ejecuta la app **como administrador**
  para poder escribir en `gameinfo.txt`.
- Los addons Vscripts pueden no funcionar con este método de activación.

## Créditos

Hecho por **Tokyossz**.
