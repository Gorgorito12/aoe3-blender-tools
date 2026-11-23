# SPDX-License-Identifier: GPL-3.0-or-later
"""Every command-line tool of the repository, described for a form: its options, what it needs,
what it writes and how safely. The studio draws one form per entry and builds the command line
from it; `tests/test_studio.py` holds each entry to its script's own usage text.

Strings are given in English and Spanish side by side (`L`). A tool that writes in place or into
a test copy is marked: one with a trial mode (`trial`) runs it first and its `commit` only after
a trial of the same values passed; one without asks for a confirmation (`confirm`).
"""
import hashlib
import json
import os
import sys

from . import ROOT
from .jobs import python_command


def L(en, es):
    return {"en": en, "es": es}


AREAS = {
    "buildings": L("Buildings", "Edificios"),
    "textures": L("Textures and units", "Texturas y unidades"),
    "survey": L("Survey and inspection", "Estudio e inspección"),
    "art": L("Art utilities", "Utilidades de arte"),
    "dev": L("Developer tools", "Herramientas de desarrollo"),
}

# what a tool may need, and how the studio tells whether it is there
NEEDS = {
    "blender": L("Blender (installed, or the bpy module)", "Blender (instalado, o el módulo bpy)"),
    "granny": L("The Granny bridge (Settings)", "El puente Granny (Ajustes)"),
    "comfy": L("ComfyUI running, with a GPU", "ComfyUI en marcha, con GPU"),
    "game": L("The game's folder (Settings)", "La carpeta del juego (Ajustes)"),
    "test_copy": L("A test copy of the game (Settings)", "Una copia de prueba del juego (Ajustes)"),
    "profile": L("A texture profile (texture survey)", "Un perfil de texturas (estudio de texturas)"),
    "network": L("Internet access", "Acceso a Internet"),
    "fonttools": L("fontTools and Pillow (pip install -r requirements-fonts.txt)",
                   "fontTools y Pillow (pip install -r requirements-fonts.txt)"),
}

# what a tool writes: shown on its form
WRITES = {
    "nothing": L("Reads only: writes nothing.", "Solo lee: no escribe nada."),
    "out": L("Writes only into the output you choose.", "Solo escribe en la salida que elijas."),
    "in_place": L("Changes the files you give it (a backup is kept).",
                  "Modifica los archivos que le das (guarda una copia de seguridad)."),
    "copy": L("Changes the test copy of the game (a backup and an undo are kept).",
              "Modifica la copia de prueba del juego (con copia de seguridad y deshacer)."),
    "repo": L("Writes into this program's own folders.", "Escribe en las carpetas del propio programa."),
    "external": L("Writes into ComfyUI's folders.", "Escribe en las carpetas de ComfyUI."),
}


class ToolError(ValueError):
    pass


class Arg:
    """One option of a form.

    kind: text, int, float, bool, choice, color, file, files, folder, folders, save, outdir
    flag: the option (None: positional, in the order given); repeat: `--flag a --flag b`
    rest: the values go last on the command line (an option that takes the rest of it)
    setting: the studio setting that gives its default
    """

    def __init__(self, key, flag, kind, label, help=None, required=False, default=None, choices=(),
                 setting=None, repeat=False, rest=False, filters=(), placeholder="", work=None):
        self.key, self.flag, self.kind, self.label = key, flag, kind, label
        self.work = work                    # left empty: this name in the tool's work folder
        self.help = help or L("", "")
        self.required, self.default, self.choices = required, default, tuple(choices)
        self.setting, self.repeat, self.rest = setting, repeat, rest
        self.filters, self.placeholder = tuple(filters), placeholder

    def public(self):
        d = {"key": self.key, "flag": self.flag, "kind": self.kind, "label": self.label, "help": self.help,
             "required": self.required, "default": self.default, "setting": self.setting,
             "placeholder": self.placeholder, "work": self.work is not None}
        if self.choices:
            d["choices"] = [{"value": c[0], "label": c[1]} if isinstance(c, tuple) else {"value": c, "label": c}
                            for c in self.choices]
        if self.filters:
            d["filters"] = [list(f) for f in self.filters]
        return d


class Tool:
    def __init__(self, id, script, area, title, desc, args, engine="python", needs=(), writes="out",
                 fixed=(), trial=None, commit=(), confirm=None, outputs=(), dev=False, minutes=None,
                 doc=None):
        self.id, self.script, self.area, self.title, self.desc = id, script, area, title, desc
        self.args, self.engine, self.needs, self.writes = list(args), engine, tuple(needs), writes
        self.fixed, self.trial, self.commit, self.confirm = list(fixed), trial, list(commit), confirm
        self.outputs, self.dev, self.minutes, self.doc = tuple(outputs), dev, minutes, doc

    def public(self):
        return {"id": self.id, "script": self.script, "area": self.area, "title": self.title, "desc": self.desc,
                "args": [a.public() for a in self.args], "engine": self.engine, "needs": list(self.needs),
                "writes": self.writes, "trial": self.trial is not None, "confirm": self.confirm,
                "outputs": list(self.outputs), "dev": self.dev, "minutes": self.minutes, "doc": self.doc}


# shared option builders ---------------------------------------------------------------------

DDT = (("DDT texture", "*.ddt"),)
PNG = (("PNG image", "*.png"),)
IMAGES = (("Images", "*.png *.jpg *.jpeg *.ddt"),)
JSON = (("JSON", "*.json"),)
XML = (("XML", "*.xml *.xmb"),)
GR2 = (("Granny model", "*.gr2"),)
TTF = (("TrueType font", "*.ttf"),)


def out_dir(required=True, key="out", flag="--out", label=None, help=None):
    """An output folder; left empty, the tool's own folder in the studio's work folder (never the
    tool's default, which is inside this program)."""
    return Arg(key, flag, "outdir", label or L("Output folder", "Carpeta de salida"),
               help or L("Empty: a folder of its own in the work folder",
                         "Vacío: una carpeta propia dentro de la carpeta de trabajo"), required=required, work="")


def game_dir(required=True, flag="--game"):
    return Arg("game", flag, "folder", L("Game folder", "Carpeta del juego"),
               L("The game (or a copy of it): read only", "El juego (o una copia): solo se lee"),
               required=required, setting="game")


def granny_args():
    return [Arg("granny", "--granny", "file", L("Granny bridge", "Puente Granny"),
                L("The external .exe that writes compressed models uncompressed",
                  "El .exe externo que descomprime los modelos"), setting="granny", filters=(("Program", "*.exe"),)),
            Arg("granny_install", "--granny-install", "folder", L("Granny runtime folder", "Carpeta del runtime Granny"),
                L("Where the game's granny2.dll is (default: the game folder)",
                  "Dónde está granny2.dll del juego (por defecto: la carpeta del juego)"))]


def cache_dir(required=False):
    return Arg("cache", "--cache", "folder", L("Cache folder", "Carpeta de caché"),
               L("Uncompressed copies of models, outside the game folder",
                 "Copias descomprimidas de modelos, fuera de la carpeta del juego"), required=required, setting="cache")


def comfy_url():
    return Arg("url", "--url", "text", L("ComfyUI address", "Dirección de ComfyUI"), setting="comfy_url")


def presets(include_all=False):
    from . import engine
    keys = [p["key"] for p in engine.presets()]
    return (["ALL"] if include_all else []) + keys


def preset_choices():
    try:
        return presets()
    except Exception:                       # the catalog must load even if the generator does not
        return []


PRESETS = preset_choices()
STYLES = ("NEOCLASSICAL", "COLONIAL", "TIMBER", "AFRICAN", "PROP")


# the tools ----------------------------------------------------------------------------------

TOOLS = [
    # -- buildings --------------------------------------------------------------------------
    Tool("mesh_to_game", "scripts/mesh_to_game.py", "buildings",
         L("Your own model for the game", "Tu propio modelo para el juego"),
         L("A static model of your own (.obj with its .mtl, .glb, .gltf) as a game bundle, without Blender: "
           "model, texture, anim file, proto and strings, icons. The screen \"Your own model\" shows it first.",
           "Un modelo estático tuyo (.obj con su .mtl, .glb, .gltf) como paquete del juego, sin Blender: modelo, "
           "textura, archivo de animación, proto y textos, iconos. La pantalla \"Tu propio modelo\" lo muestra antes."),
         [Arg("in", "--in", "file", L("Model", "Modelo"), required=True,
              filters=(("Model", "*.obj *.glb *.gltf"),)),
          out_dir(),
          Arg("name", "--name", "text", L("Name", "Nombre"), L("Letters, digits and _", "Letras, cifras y _"), required=True),
          Arg("up", "--up", "choice", L("Vertical axis of the file", "Eje vertical del archivo"), choices=("y", "z"), default="y"),
          Arg("scale", "--scale", "float", L("Scale into metres", "Escala a metros"),
              L("A model in centimetres: 0.01", "Un modelo en centímetros: 0,01"), default=1.0),
          Arg("fit_units", "--fit-units", "float", L("Size in game units", "Tamaño en unidades del juego"),
              L("The plot's longer side: 4 for a building of the 4x4 class (instead of the scale)",
                "El lado mayor de la parcela: 4 para un edificio de la clase 4x4 (en lugar de la escala)")),
          Arg("turn", "--turn", "choice", L("Turn (degrees)", "Girar (grados)"), choices=("0", "90", "180", "270"), default="0"),
          Arg("flat", "--flat", "bool", L("Flat faces", "Caras planas")),
          Arg("texture_png", "--texture-png", "file", L("Another texture (PNG)", "Otra textura (PNG)"), filters=PNG),
          Arg("kind", "--kind", "choice", L("Kind", "Tipo"), choices=("BUILDING", "PROP"), default="BUILDING"),
          Arg("template", "--template", "text", L("Proto template", "Plantilla de proto"),
              L("The unit whose proto entry it copies", "La unidad cuya entrada de proto copia"), default="House"),
          Arg("prefix", "--prefix", "text", L("Mod folder", "Carpeta del mod"), default="mod"),
          Arg("display", "--display", "text", L("Name in game", "Nombre en el juego")),
          Arg("folder", "--folder", "text", L("Art folder", "Carpeta de arte")),
          Arg("texture", "--texture", "choice", L("Texture format", "Formato de textura"),
              choices=("DXT3", "DXT1", "BGRA"), default="DXT3"),
          Arg("no_icons", "--no-icons", "bool", L("No icon or portrait", "Sin icono ni retrato")),
          Arg("check_only", "--check-only", "bool", L("Only check, write nothing", "Solo comprobar, sin escribir"))]),
    Tool("game_export", "scripts/game_export.py", "buildings",
         L("Export a preset for the game", "Exportar un preset al juego"),
         L("Writes a preset as a game bundle: model, texture, anim file, proto fields and strings, icons, "
           "technical sheet.", "Escribe un preset como paquete del juego: modelo, textura, archivo de "
           "animación, campos de proto y textos, iconos y ficha técnica."),
         [out_dir(), Arg("preset", "--preset", "choice", L("Preset", "Preset"), choices=PRESETS, default="WHITE_HOUSE"),
          Arg("detail", "--detail", "choice", L("Detail", "Detalle"), choices=("", "LOW", "MEDIUM")),
          Arg("prefix", "--prefix", "text", L("Mod folder", "Carpeta del mod"),
              L("The mod's own folder under art", "La carpeta propia del mod dentro de art"), default="mod"),
          Arg("name", "--name", "text", L("Name", "Nombre")),
          Arg("display", "--display", "text", L("Name in game", "Nombre en el juego")),
          Arg("template", "--template", "text", L("Proto template", "Plantilla de proto"),
              L("The unit whose proto entry it copies", "La unidad cuya entrada de proto copia")),
          Arg("kind", "--kind", "choice", L("Kind", "Tipo"), choices=("", "BUILDING", "PROP")),
          Arg("folder", "--folder", "text", L("Art folder", "Carpeta de arte")),
          Arg("texture", "--texture", "choice", L("Texture format", "Formato de textura"),
              choices=("DXT3", "DXT1", "BGRA"), default="DXT3"),
          Arg("player_colour", "--player-colour", "bool", L("Player colour", "Color del jugador")),
          Arg("materials", "--materials", "bool", L("Material swatches", "Muestras de material")),
          Arg("no_icons", "--no-icons", "bool", L("No icon or portrait", "Sin icono ni retrato")),
          Arg("no_lowpoly", "--no-lowpoly", "bool", L("No low-poly model", "Sin modelo de pocos polígonos")),
          Arg("no_damaged", "--no-damaged", "bool", L("No damaged model", "Sin modelo dañado")),
          Arg("no_v_flip", "--no-v-flip", "bool", L("Do not flip V", "No invertir V")),
          Arg("ai", "--ai", "float", L("AI repaint strength", "Fuerza del repintado IA"),
              L("Empty: no AI repaint (needs ComfyUI)", "Vacío: sin repintado IA (necesita ComfyUI)")),
          Arg("ai_seed", "--ai-seed", "int", L("AI seed", "Semilla IA")),
          Arg("ai_url", "--ai-url", "text", L("ComfyUI address", "Dirección de ComfyUI"), setting="comfy_url"),
          Arg("texture_png", "--texture-png", "file", L("Texture to use", "Textura a usar"),
              L("A PNG of this building's texture size, in place of the painted one",
                "Un PNG del tamaño de la textura de este edificio, en lugar de la pintada"), filters=PNG),
          Arg("profile", "--profile", "file", L("Calibration profile", "Perfil de calibración"), filters=JSON),
          Arg("no_profile", "--no-profile", "bool", L("No calibration profile", "Sin perfil de calibración")),
          Arg("proto", "--proto", "file", L("Game proto (for the sheet)", "Proto del juego (para la ficha)"),
              filters=XML)],
         engine="blender", needs=("blender",), outputs=("out",)),
    Tool("game_export_set", "scripts/game_export.py", "buildings",
         L("Export a prop set for the game", "Exportar un set de props al juego"),
         L("A generated prop set as one unit whose models are its variations, on one texture.",
           "Un set de props generado como una unidad cuyas variaciones son sus modelos, en una sola textura."),
         [out_dir(), Arg("set", "--set", "choice", L("Set", "Set"), choices=("GOODS", "CAMP"), required=True),
          Arg("prefix", "--prefix", "text", L("Mod folder", "Carpeta del mod"), default="mod"),
          Arg("texture_size", "--texture-size", "choice", L("Texture size", "Tamaño de textura"),
              choices=("256", "512", "1024"), default="256"),
          Arg("texture", "--texture", "choice", L("Texture format", "Formato de textura"),
              choices=("DXT3", "DXT1", "BGRA"), default="DXT3"),
          Arg("display", "--display", "text", L("Name in game", "Nombre en el juego")),
          Arg("template", "--template", "text", L("Proto template", "Plantilla de proto"), default="PropsColony"),
          Arg("folder", "--folder", "text", L("Art folder", "Carpeta de arte"), default="objects"),
          Arg("no_icons", "--no-icons", "bool", L("No icon or portrait", "Sin icono ni retrato"))],
         engine="blender", needs=("blender",), outputs=("out",)),
    Tool("generate", "scripts/generate.py", "buildings",
         L("Generate a preset with renders", "Generar un preset con renders"),
         L("Mesh, texture, GLB/FBX/OBJ exports, a .blend and preview renders of a preset.",
           "Malla, textura, exportaciones GLB/FBX/OBJ, un .blend y renders de vista previa de un preset."),
         [Arg("preset", "--preset", "choice", L("Preset", "Preset"), choices=PRESETS, default="WHITE_HOUSE"),
          Arg("detail", "--detail", "choice", L("Detail", "Detalle"), choices=("", "LOW", "MEDIUM")),
          out_dir(required=False),
          Arg("views", "--views", "text", L("Views", "Vistas"), L("Comma list of front34, back34, wire, front, back",
                                                                  "Lista separada por comas: front34, back34, wire, front, back"),
              default="front34,back34,wire"),
          Arg("no_render", "--no-render", "bool", L("No renders", "Sin renders")),
          Arg("materials", "--materials", "bool", L("Material swatches", "Muestras de material")),
          Arg("textures", "--textures", "folder", L("Texture library", "Biblioteca de texturas")),
          Arg("poly", "--poly", "float", L("Segments", "Segmentos"))],
         engine="blender", needs=("blender",), outputs=("out",), minutes=1),
    Tool("check", "scripts/check.py", "buildings",
         L("Check a preset", "Comprobar un preset"),
         L("The game-ready checks of the add-on: the triangle budget of its footprint class, overlapping faces, "
           "UVs outside their region, repeated corners.",
           "Las comprobaciones del complemento: el presupuesto de triángulos de su clase, caras solapadas, UV fuera "
           "de su región, esquinas repetidas."),
         [Arg("preset", "--preset", "choice", L("Preset", "Preset"), choices=PRESETS, default="WHITE_HOUSE"),
          Arg("params", "--params", "file", L("Or a building's options", "O las opciones de un edificio"),
              L("A .json saved from the building screen", "Un .json guardado desde la pantalla de edificios"),
              filters=JSON),
          Arg("detail", "--detail", "choice", L("Detail", "Detalle"), choices=("", "LOW", "MEDIUM")),
          Arg("budget", "--budget", "int", L("Triangle budget without a profile", "Presupuesto sin perfil"),
              default=6000),
          Arg("no_profile", "--no-profile", "bool", L("Without the measured budget", "Sin el presupuesto medido"))],
         engine="blender", needs=("blender",), writes="nothing"),
    Tool("deploy", "tools/game_deploy.py", "buildings",
         L("Deploy bundles to the test copy", "Desplegar paquetes en la copia de prueba"),
         L("Installs one or more game bundles into a test copy of the game. Undo takes them out again.",
           "Instala uno o más paquetes en una copia de prueba del juego. Deshacer los quita de nuevo."),
         [Arg("install", "--install", "folder", L("Test copy", "Copia de prueba"), required=True, setting="test_copy"),
          Arg("bundle", "--bundle", "folders", L("Bundles", "Paquetes"), required=True, repeat=True),
          Arg("keep", "--keep", "bool", L("Add to what is deployed", "Añadir a lo ya desplegado"),
              L("Without it, a deployment replaces the one before it", "Sin esto, un despliegue sustituye al anterior")),
          Arg("show_as", "--show-as", "text", L("Show as unit", "Mostrar como unidad"),
              L("Also points this unit's model at the new building (e.g. TownCenter)",
                "También apunta el modelo de esta unidad al nuevo edificio (p. ej. TownCenter)")),
          Arg("builder", "--builder", "text", L("Builder", "Constructor"),
              L("The unit that gets it in its build list", "La unidad que lo recibe en su lista de construcción"),
              default="Settler"),
          Arg("validate", "--validate", "bool", L("Run the mod's validators", "Ejecutar los validadores del mod"),
              L("Runs the validate_*.py scripts found in the copy", "Ejecuta los scripts validate_*.py de la copia"))],
         needs=("test_copy",), writes="copy",
         confirm=L("This changes the test copy of the game. Backups are kept and Undo restores it.",
                   "Esto modifica la copia de prueba del juego. Se guardan copias de seguridad y Deshacer la restaura.")),
    Tool("deploy_grouping", "tools/game_deploy.py", "buildings",
         L("Deploy a grouping to the test copy", "Desplegar un grouping en la copia de prueba"),
         L("Copies grouping files (settlements) into every RM*/groupings folder of the test copy.",
           "Copia archivos de grouping (asentamientos) en cada carpeta RM*/groupings de la copia de prueba."),
         [Arg("install", "--install", "folder", L("Test copy", "Copia de prueba"), required=True, setting="test_copy"),
          Arg("grouping", "--grouping", "files", L("Groupings", "Groupings"), required=True, repeat=True, filters=XML)],
         needs=("test_copy",), writes="copy",
         confirm=L("This changes the test copy of the game.", "Esto modifica la copia de prueba del juego.")),
    Tool("deploy_files", "tools/game_deploy.py", "buildings",
         L("Deploy edited files to the test copy", "Desplegar archivos editados en la copia de prueba"),
         L("Copies a folder laid out as the copy (data, art, FONTS: the game interface's saved layouts and rows "
           "file, the fonts with their missing letters) into the test copy; what it replaces is backed up, a "
           "compiled twin of an edited XML taken out; Undo puts everything back.",
           "Copia una carpeta con la estructura de la copia (data, art, FONTS: las disposiciones y el archivo de "
           "filas guardados de la interfaz, las fuentes con sus letras que faltaban) en la copia de prueba; lo que "
           "sustituye se respalda y se quita el gemelo compilado de un XML editado; Deshacer lo restaura todo."),
         [Arg("install", "--install", "folder", L("Test copy", "Copia de prueba"),
              L("A copy of the game for testing (never the Steam folder: it is refused).",
                "Una copia del juego para pruebas (nunca la carpeta de Steam: se rechaza)."),
              required=True, setting="test_copy"),
          Arg("files", "--files", "folder", L("Folder to deploy", "Carpeta a desplegar"),
              L("Laid out as the copy: data\\..., art\\... (what the game interface screen saves).",
                "Con la estructura de la copia: data\\..., art\\... (lo que guarda la pantalla de la interfaz)."),
              required=True)],
         needs=("test_copy",), writes="copy",
         confirm=L("This changes the test copy of the game. Backups are kept and Undo restores it.",
                   "Esto modifica la copia de prueba del juego. Se guardan copias de seguridad y Deshacer la restaura.")),
    Tool("deploy_undo", "tools/game_deploy.py", "buildings",
         L("Undo the deployment", "Deshacer el despliegue"),
         L("Takes out what was deployed and restores the backed-up files.",
           "Quita lo desplegado y restaura los archivos respaldados."),
         [Arg("install", "--install", "folder", L("Test copy", "Copia de prueba"), required=True, setting="test_copy")],
         fixed=["--undo"], needs=("test_copy",), writes="copy",
         confirm=L("This restores the test copy as it was before the deployments.",
                   "Esto restaura la copia de prueba como estaba antes de los despliegues.")),
    Tool("deploy_validate", "tools/game_deploy.py", "buildings",
         L("Validate the test copy", "Validar la copia de prueba"),
         L("Runs the mod's validators found at the root of the copy.",
           "Ejecuta los validadores del mod que hay en la raíz de la copia."),
         [Arg("install", "--install", "folder", L("Test copy", "Copia de prueba"), required=True, setting="test_copy")],
         fixed=["--validate"], needs=("test_copy",), writes="nothing",
         confirm=L("This runs Python scripts that are inside the test copy (the mod's own validators). Run them only "
                   "if you trust that copy.", "Esto ejecuta scripts de Python que están dentro de la copia de prueba "
                   "(los validadores del mod). Ejecútalos solo si confías en esa copia.")),

    # -- textures and units -----------------------------------------------------------------
    Tool("make_texture", "tools/make_texture.py", "textures",
         L("Make a tileable texture", "Crear una textura repetible"),
         L("A seamless texture from a picture or a description, kept in the texture library with its licence.",
           "Una textura sin costuras a partir de una imagen o una descripción, guardada en la biblioteca con su "
           "licencia."),
         [Arg("name", "--name", "text", L("Name", "Nombre"), required=True, placeholder="factory_roof"),
          Arg("licence", "--licence", "text", L("Licence", "Licencia"),
              L("Where the picture comes from and its licence", "De dónde viene la imagen y su licencia"),
              required=True, placeholder="my own photo"),
          Arg("image", "--image", "file", L("Picture", "Imagen"), filters=IMAGES),
          Arg("crop", "--crop", "text", L("Crop", "Recorte"), L("cx,cy,part (0..1)", "cx,cy,parte (0..1)"),
              placeholder="0.5,0.5,1"),
          Arg("prompt", "--prompt", "text", L("Description", "Descripción"),
              L("Words for ComfyUI to draw (needs ComfyUI)", "Palabras para que ComfyUI dibuje (necesita ComfyUI)")),
          Arg("size", "--size", "choice", L("Size", "Tamaño"), choices=("128", "256", "512"), default="256"),
          Arg("tile_m", "--tile-m", "float", L("Metres per tile", "Metros por repetición"), default=2.0),
          Arg("seed", "--seed", "int", L("Seed", "Semilla"), default=1),
          Arg("strength", "--strength", "float", L("Repaint strength", "Fuerza del repintado")),
          Arg("style", "--style", "choice", L("Style", "Estilo"), choices=("",) + STYLES),
          Arg("role", "--role", "text", L("Role", "Papel"), placeholder="roof"),
          Arg("folder", "--folder", "folder", L("Library folder", "Carpeta de la biblioteca")),
          Arg("material", "--material", "text", L("Material", "Material"), placeholder="wood"),
          Arg("category", "--category", "text", L("Category", "Categoría"), placeholder="buildings"),
          Arg("no_fit", "--no-fit", "bool", L("Do not fit to the mod", "No ajustar al mod")),
          Arg("lora", "--lora", "text", L("LoRA", "LoRA")),
          Arg("lora_strength", "--lora-strength", "float", L("LoRA strength", "Fuerza del LoRA")),
          Arg("no_ai", "--no-ai", "bool", L("Without AI", "Sin IA"), L("Never asks ComfyUI", "Nunca usa ComfyUI")),
          Arg("keep_light", "--keep-light", "bool", L("Keep the light", "Conservar la luz")),
          Arg("no_heal", "--no-heal", "bool", L("No healing", "Sin corrección de costuras")),
          comfy_url()],
         writes="out"),                     # a picture with "Without AI" needs no ComfyUI
    Tool("texture_library", "tools/make_texture.py", "textures",
         L("List the texture library", "Ver la biblioteca de texturas"),
         L("Prints the textures the library holds.", "Muestra las texturas de la biblioteca."),
         [Arg("folder", "--folder", "folder", L("Library folder", "Carpeta de la biblioteca"))],
         fixed=["--list"], writes="nothing"),
    Tool("uv_atlas", "tools/uv_atlas.py", "textures",
         L("UV atlas of a unit", "Atlas UV de una unidad"),
         L("The UV layout of a unit's model over its texture, labelled by body part, with one mask per part.",
           "El mapa UV del modelo de una unidad sobre su textura, con cada parte del cuerpo marcada y una "
           "máscara por parte."),
         [Arg("target", None, "text", L("Unit, anim file or model", "Unidad, archivo de animación o modelo"),
              required=True, placeholder="Musketeer"),
          game_dir(), out_dir(),
          Arg("prefer", "--prefer", "text", L("Preferred branches", "Ramas preferidas")),
          Arg("texture", "--texture", "file", L("Paint over this texture", "Pintar sobre esta textura"), filters=IMAGES),
          Arg("size", "--size", "text", L("Mask size", "Tamaño de las máscaras"), placeholder="512x512"),
          Arg("by", "--by", "choice", L("Parts by", "Partes según"), choices=("bone", "position"), default="bone"),
          Arg("overlay", "--overlay", "folder", L("Overlay folder", "Carpeta superpuesta")),
          cache_dir()] + granny_args(),
         needs=("game",), outputs=("out",)),
    Tool("recolor_textures", "tools/recolor_textures.py", "textures",
         L("Recolour textures", "Recolorear texturas"),
         L("Shifts the hue, saturation and lightness of textures (a terrain, a plant) and measures how far they are "
           "from the player colours before and after. Bump maps are left as they are.",
           "Cambia el tono, la saturación y la luminosidad de texturas (un terreno, una planta) y mide cuánto se "
           "alejan de los colores de los jugadores antes y después. Los mapas de relieve no se tocan."),
         [Arg("inputs", None, "folders", L("Textures or folders", "Texturas o carpetas"), required=True),
          out_dir(required=False),
          Arg("hue", "--hue", "float", L("Hue shift (degrees)", "Cambio de tono (grados)"), default=0.0),
          Arg("chroma", "--chroma", "float", L("Saturation factor", "Factor de saturación"), default=1.0),
          Arg("lightness", "--lightness", "float", L("Lightness factor", "Factor de luminosidad"), default=1.0),
          Arg("hue_window", "--hue-window", "text", L("Only these hues", "Solo estos tonos"), placeholder="25,20,25"),
          Arg("mix", "--mix", "file", L("Terrain mix", "Mezcla de terreno"), filters=XML),
          Arg("player_colors", "--player-colors", "file", L("Player colours file", "Archivo de colores de jugador"),
              filters=XML),
          Arg("against", "--against", "text", L("Other colours", "Otros colores"), placeholder="p2=210,40,40"),
          Arg("mapcolor", "--mapcolor", "text", L("Minimap colour", "Color del minimapa"), placeholder="160,15,30"),
          Arg("near", "--near", "float", L("Near threshold (dE)", "Umbral de cercanía (dE)"), default=20.0),
          Arg("report", "--report", "save", L("Report", "Informe"), filters=JSON, work="report.json"),
          Arg("preview", "--preview", "save", L("Before and after picture", "Imagen de antes y después"),
              filters=PNG, work="preview.png"),
          Arg("dry_run", "--dry-run", "bool", L("Measure only, write no texture", "Solo medir, sin escribir texturas"))],
         outputs=("out", "report", "preview")),
    Tool("retexture", "tools/retexture.py", "textures",
         L("Repaint a unit by parts", "Repintar una unidad por partes"),
         L("Repaints a unit's texture part by part from a recipe, and writes the .ddt and its bump map.",
           "Repinta la textura de una unidad parte por parte según una receta, y escribe el .ddt y su mapa de "
           "relieve."),
         [Arg("recipe", None, "file", L("Recipe", "Receta"), required=True, filters=JSON),
          Arg("preview", "--preview", "save", L("Preview sheet", "Hoja de vista previa"), filters=PNG),
          comfy_url()],
         outputs=("preview",), doc="tools/retexture.py"),
    Tool("own_texture", "tools/retexture.py", "textures",
         L("Model copy with its own texture", "Copia del modelo con su propia textura"),
         L("A copy of an uncompressed model whose texture paths are renamed (same length).",
           "Una copia de un modelo sin comprimir con las rutas de textura renombradas (misma longitud)."),
         [Arg("model_in", None, "file", L("Model", "Modelo"), required=True, filters=GR2),
          Arg("model_out", None, "save", L("New model", "Nuevo modelo"), required=True, filters=GR2),
          Arg("pairs", None, "text", L("Renames OLD=NEW", "Cambios OLD=NEW"),
              L("Space-separated art paths without extension", "Rutas de arte sin extensión, separadas por espacios"),
              required=True, rest=True)],
         fixed=["--own-texture"], outputs=("model_out",)),
    Tool("lora_dataset", "tools/lora_dataset.py", "textures",
         L("LoRA dataset from the mod", "Dataset de LoRA del mod"),
         L("Pieces of the mod's own textures to train a LoRA of its hand on.",
           "Fragmentos de las texturas propias del mod para entrenar un LoRA con su estilo."),
         [Arg("report", None, "file", L("Texture survey report", "Informe del estudio de texturas"), required=True,
              filters=JSON),
          out_dir(),
          Arg("models", "--models", "file", L("Model survey report", "Informe del estudio de modelos"), filters=JSON),
          Arg("categories", "--categories", "text", L("Categories", "Categorías"),
              placeholder="buildings,buildingsets,homecity,objects,nuggets,other"),
          Arg("side", "--side", "int", L("Piece size", "Tamaño de cada fragmento"), default=512),
          Arg("max", "--max", "int", L("Most pieces", "Máximo de fragmentos"), default=900),
          Arg("trigger", "--trigger", "text", L("Trigger word", "Palabra clave"), default="aoe3bt"),
          Arg("seed", "--seed", "int", L("Seed", "Semilla"), default=1)],
         outputs=("out",)),
    Tool("train_lora", "tools/train_lora.py", "textures",
         L("Train a LoRA", "Entrenar un LoRA"),
         L("Trains a LoRA with the local ComfyUI, in chunks, watching the PC's free memory.",
           "Entrena un LoRA con el ComfyUI local, por tramos, vigilando la memoria libre del PC."),
         [Arg("dataset", None, "folder", L("Dataset folder", "Carpeta del dataset"), required=True),
          Arg("comfy", "--comfy", "folder", L("ComfyUI folder", "Carpeta de ComfyUI"), required=True, setting="comfy_dir"),
          Arg("name", "--name", "text", L("Name", "Nombre"), default="aoe3bt_own"),
          Arg("steps", "--steps", "int", L("Steps", "Pasos"), default=1200),
          Arg("chunks", "--chunks", "int", L("Chunks", "Tramos"), default=3),
          Arg("rank", "--rank", "int", L("Rank", "Rango"), default=16),
          Arg("lr", "--lr", "text", L("Learning rate", "Tasa de aprendizaje"), default="1e-4"),
          Arg("batch", "--batch", "int", L("Batch", "Lote"), default=1),
          Arg("accumulate", "--accumulate", "int", L("Accumulation steps", "Pasos de acumulación"), default=2),
          Arg("offload", "--offload", "bool", L("Offload", "Descargar a RAM")),
          Arg("seed", "--seed", "int", L("Seed", "Semilla"), default=1),
          Arg("min_free", "--min-free", "float", L("Least free memory (GB)", "Memoria libre mínima (GB)"), default=2.5),
          Arg("resume", "--resume", "file", L("Resume from", "Continuar desde")),
          Arg("limit", "--limit", "int", L("Limit pictures", "Limitar imágenes")),
          comfy_url()],
         needs=("comfy",), writes="external", minutes=30),

    # -- survey and inspection --------------------------------------------------------------
    Tool("art_survey", "tools/art_survey.py", "survey",
         L("Art survey", "Estudio del arte"),
         L("What models, textures and anim files a game or mod has, how they reference each other and the "
           "conventions they follow. Its report names the mod's files: keep it private.",
           "Qué modelos, texturas y archivos de animación tiene un juego o mod, cómo se referencian y qué "
           "convenciones siguen. El informe nombra los archivos del mod: mantenlo privado."),
         [Arg("folders", None, "folders", L("Game or mod folders", "Carpetas del juego o del mod"), required=True,
              setting="mod"),
          out_dir(),
          Arg("bar", "--bar", "bool", L("Read the .bar archives", "Leer los archivos .bar")),
          Arg("label", "--label", "text", L("Label", "Etiqueta")),
          Arg("reference", "--reference", "file", L("Reference report", "Informe de referencia"), filters=JSON),
          Arg("proto", "--proto", "file", L("Game proto", "Proto del juego"), filters=XML),
          cache_dir()] + granny_args() +
         [Arg("profile_out", "--profile-out", "save", L("Profile to write", "Perfil a escribir"), filters=JSON)],
         outputs=("out", "profile_out")),
    Tool("texture_survey", "tools/texture_survey.py", "survey",
         L("Texture survey", "Estudio de texturas"),
         L("Measures every texture of a game or mod: colour, grain, saturation, seams, player colour.",
           "Mide cada textura de un juego o mod: color, grano, saturación, costuras, color del jugador."),
         [Arg("folders", None, "folders", L("Mod folders", "Carpetas del mod"), required=True, setting="mod"),
          out_dir(),
          Arg("reference", "--reference", "folders", L("Original game folders", "Carpetas del juego original"),
              setting="game"),
          Arg("workers", "--workers", "int", L("Workers", "Procesos")),
          Arg("limit", "--limit", "int", L("Limit", "Límite")),
          Arg("from_report", "--from", "file", L("From a report", "Desde un informe"), filters=JSON),
          Arg("models", "--models", "file", L("Model survey report", "Informe del estudio de modelos"), filters=JSON),
          Arg("profile_out", "--profile-out", "save", L("Profile to write", "Perfil a escribir"), filters=JSON),
          Arg("sheets", "--sheets", "outdir", L("Contact sheets folder", "Carpeta de hojas de contacto"))],
         outputs=("out", "profile_out", "sheets"), minutes=3),
    Tool("model_survey", "tools/model_survey.py", "survey",
         L("Model survey", "Estudio de modelos"),
         L("Opens every Granny file of a game or mod and measures it: triangles, bones, size, animations.",
           "Abre cada archivo Granny de un juego o mod y lo mide: triángulos, huesos, tamaño, animaciones."),
         [Arg("folders", None, "folders", L("Game or mod folders", "Carpetas del juego o del mod"), required=True,
              setting="mod"),
          out_dir()] + granny_args() + [cache_dir(),
          Arg("reference", "--reference", "folders", L("Original game folders", "Carpetas del juego original"),
              setting="game"),
          Arg("workers", "--workers", "int", L("Workers", "Procesos")),
          Arg("limit", "--limit", "int", L("Limit", "Límite")),
          Arg("only", "--only", "text", L("Only", "Solo"), placeholder="units"),
          Arg("from_report", "--from", "file", L("From a report", "Desde un informe"), filters=JSON),
          Arg("textures", "--textures", "file", L("Texture survey report", "Informe del estudio de texturas"),
              filters=JSON),
          Arg("profile_out", "--profile-out", "save", L("Profile to write", "Perfil a escribir"), filters=JSON)],
         needs=("granny",), outputs=("out", "profile_out"), minutes=6),
    Tool("grouping_survey", "tools/grouping_survey.py", "survey",
         L("Grouping survey", "Estudio de groupings"),
         L("What the settlements of a game or mod place round their socket, how far and facing where.",
           "Qué colocan los asentamientos de un juego o mod alrededor de su socket, a qué distancia y "
           "orientados hacia dónde."),
         [Arg("folder", None, "folder", L("Game or mod folder", "Carpeta del juego o del mod"), required=True,
              setting="mod"),
          Arg("proto", "--proto", "file", L("Game proto", "Proto del juego"), filters=XML),
          Arg("reference", "--reference", "folder", L("Original game folder", "Carpeta del juego original"),
              setting="game"),
          Arg("out", "--out", "save", L("Report", "Informe"), filters=JSON),
          Arg("profile_out", "--profile-out", "save", L("Profile to write", "Perfil a escribir"), filters=JSON)],
         outputs=("out", "profile_out")),
    Tool("shape_survey", "tools/shape_survey.py", "survey",
         L("Shape survey", "Estudio de formas"),
         L("How the buildings are made: one mass or many, how tall, how much of the plot they cover.",
           "Cómo están hechos los edificios: una masa o varias, qué altura, cuánto del terreno cubren."),
         [Arg("report", None, "file", L("Art survey report", "Informe del estudio del arte"), required=True,
              filters=JSON),
          Arg("raw", None, "folder", L("Cache raw folder", "Carpeta raw de la caché"), required=True),
          Arg("out", "--out", "save", L("Result", "Resultado"), filters=JSON),
          Arg("limit", "--limit", "int", L("Limit", "Límite"))],
         outputs=("out",)),
    Tool("palette_survey", "tools/palette_survey.py", "survey",
         L("Palette survey", "Estudio de paleta"),
         L("Mean colour and local contrast of the stock building textures.",
           "Color medio y contraste local de las texturas de edificios del juego."),
         [Arg("bars", None, "files", L("Art .bar archives", "Archivos .bar de arte"), required=True,
              filters=(("BAR archive", "*.bar"),)),
          Arg("filter", "--filter", "text", L("Filter", "Filtro"), default="buildings"),
          Arg("limit", "--limit", "int", L("Limit", "Límite"), default=80)],
         writes="nothing"),
    Tool("style_check", "tools/style_check.py", "survey",
         L("Style check", "Comprobar el estilo"),
         L("How far each preset's texture is from the mod's own textures: grain, saturation, luminance.",
           "Cuánto se aleja la textura de cada preset de las texturas propias del mod: grano, saturación, "
           "luminancia."),
         [Arg("presets", None, "text", L("Presets", "Presets"), L("Space-separated; empty: a default set",
                                                                 "Separados por espacios; vacío: un grupo por defecto"),
              rest=True),
          Arg("materials", "--materials", "bool", L("Material swatches", "Muestras de material")),
          Arg("origin", "--origin", "choice", L("Origin", "Origen"), choices=("own", "stock"), default="own"),
          Arg("category", "--category", "text", L("Category", "Categoría"), default="buildings"),
          Arg("size", "--size", "int", L("Texture size", "Tamaño de textura"), default=1024)],
         needs=("profile",), writes="nothing"),
    Tool("model_sheets", "tools/model_sheets.py", "survey",
         L("Contact sheet of named models", "Hoja de contacto de modelos"),
         L("Renders a list of units or models from the game side by side, each with its caption.",
           "Renderiza una lista de unidades o modelos del juego lado a lado, cada uno con su título."),
         [Arg("models", "--models", "file", L("List of models", "Lista de modelos"), required=True,
              filters=(("Text", "*.txt"),)),
          game_dir(),
          Arg("out", "--out", "save", L("Sheet", "Hoja"), required=True, filters=PNG),
          Arg("cell", "--cell", "int", L("Cell size", "Tamaño de celda"), default=220),
          Arg("cols", "--cols", "int", L("Columns", "Columnas"), default=6),
          Arg("title", "--title", "text", L("Title", "Título")),
          Arg("keep_scale", "--keep-scale", "bool", L("Same scale for all", "Misma escala para todos")),
          Arg("prefer", "--prefer", "text", L("Preferred branches", "Ramas preferidas")),
          Arg("attachments", "--attachments", "bool", L("Draw attachments", "Dibujar accesorios")),
          Arg("views", "--views", "text", L("Views (degrees)", "Vistas (grados)"), placeholder="-35,145"),
          Arg("overlay", "--overlay", "folder", L("Overlay folder", "Carpeta superpuesta")),
          Arg("team", "--team", "color", L("Player colour", "Color del jugador")),
          Arg("elevation", "--elevation", "float", L("Camera elevation", "Elevación de la cámara"), default=30),
          cache_dir()] + granny_args(),
         engine="blender", needs=("blender", "game"), outputs=("out",)),
    Tool("model_sheets_survey", "tools/model_sheets.py", "survey",
         L("Contact sheets of a model survey", "Hojas de contacto de un estudio de modelos"),
         L("A grid of sampled models per origin and category, each with its own texture.",
           "Una cuadrícula de modelos de muestra por origen y categoría, cada uno con su textura."),
         [Arg("report", None, "file", L("Model survey report", "Informe del estudio de modelos"), required=True,
              filters=JSON),
          cache_dir(required=True), out_dir(),
          Arg("textures", "--textures", "file", L("Texture survey report", "Informe del estudio de texturas"),
              filters=JSON),
          Arg("groups", "--groups", "text", L("Groups", "Grupos"), placeholder="own:buildings,stock:nuggets"),
          Arg("cell", "--cell", "int", L("Cell size", "Tamaño de celda"), default=160),
          Arg("cols", "--cols", "int", L("Columns", "Columnas"), default=8),
          Arg("rows", "--rows", "int", L("Rows", "Filas"), default=6),
          Arg("seed", "--seed", "int", L("Seed", "Semilla"), default=3)],
         engine="blender", needs=("blender",), outputs=("out",)),
    Tool("named_models", "tools/named_models.py", "survey",
         L("Check a list of models", "Comprobar una lista de modelos"),
         L("Prints what each entry of a list resolves to in the game (no Blender needed).",
           "Muestra a qué modelo del juego corresponde cada entrada de una lista (sin Blender)."),
         [Arg("list", None, "file", L("List of models", "Lista de modelos"), required=True,
              filters=(("Text", "*.txt"),)),
          game_dir(),
          Arg("prefer", "--prefer", "text", L("Preferred branches", "Ramas preferidas")),
          Arg("overlay", "--overlay", "folder", L("Overlay folder", "Carpeta superpuesta"))],
         needs=("game",), writes="nothing"),
    Tool("bar_list", "tools/bar.py", "survey",
         L("List a .bar archive", "Listar un archivo .bar"),
         L("The files inside a game archive (.bar).", "Los archivos dentro de un archivo del juego (.bar)."),
         [Arg("archive", None, "file", L("Archive", "Archivo"), required=True, filters=(("BAR archive", "*.bar"),)),
          Arg("filter", None, "text", L("Filter", "Filtro"), placeholder="tactics/explorer")],
         writes="nothing"),
    Tool("bar_extract", "tools/bar.py", "survey",
         L("Extract from a .bar archive", "Extraer de un archivo .bar"),
         L("Extracts the files of an archive (those matching the filter) into a folder.",
           "Extrae los archivos de un .bar (los que coincidan con el filtro) a una carpeta."),
         [Arg("archive", None, "file", L("Archive", "Archivo"), required=True, filters=(("BAR archive", "*.bar"),)),
          Arg("filter", None, "text", L("Filter", "Filtro"), placeholder="tactics/explorer"),
          out_dir(key="extract", flag="--extract")],
         outputs=("extract",)),
    Tool("xmb_check", "tools/xmbedit.py", "survey",
         L("Check a compiled XML (.xmb)", "Comprobar un XML compilado (.xmb)"),
         L("Decodes and re-encodes the file and confirms it comes back byte for byte.",
           "Decodifica y recodifica el archivo y confirma que vuelve idéntico byte a byte."),
         [Arg("file", None, "file", L("File", "Archivo"), required=True, filters=(("XMB", "*.xmb"),))],
         fixed=["check"], writes="nothing"),
    Tool("xmb_to_xml", "tools/xmbedit.py", "survey",
         L(".xmb to XML", ".xmb a XML"),
         L("A readable XML copy of a compiled XML file.", "Una copia XML legible de un archivo XML compilado."),
         [Arg("file", None, "file", L("Compiled file", "Archivo compilado"), required=True, filters=(("XMB", "*.xmb"),)),
          Arg("out", None, "save", L("XML to write", "XML a escribir"), required=True, filters=XML)],
         fixed=["to-xml"], outputs=("out",)),
    Tool("xml_to_xmb", "tools/xmbedit.py", "survey",
         L("XML to .xmb", "XML a .xmb"),
         L("Compiles an XML file the way the stock files are stored.",
           "Compila un archivo XML como están guardados los del juego."),
         [Arg("file", None, "file", L("XML file", "Archivo XML"), required=True, filters=XML),
          Arg("out", None, "save", L(".xmb to write", ".xmb a escribir"), required=True, filters=(("XMB", "*.xmb"),)),
          Arg("compress", "--compress", "bool", L("Compressed (l33t)", "Comprimido (l33t)"))],
         fixed=["from-xml"], outputs=("out",)),
    Tool("xmb_add_unittype", "tools/xmbedit.py", "survey",
         L("Add unit types to a proto", "Añadir tipos de unidad a un proto"),
         L("Adds <unittype> entries to named units of a compiled proto file.",
           "Añade entradas <unittype> a unidades de un proto compilado."),
         [Arg("file", None, "file", L("Proto (.xmb)", "Proto (.xmb)"), required=True, filters=(("XMB", "*.xmb"),)),
          Arg("out", None, "save", L("Proto to write", "Proto a escribir"), required=True, filters=(("XMB", "*.xmb"),)),
          Arg("pairs", None, "text", L("Unit and type pairs", "Pares unidad y tipo"),
              L("Unit UnitType [Unit UnitType ...]", "Unidad TipoDeUnidad [Unidad TipoDeUnidad ...]"),
              required=True, rest=True)],
         fixed=["add-unittype"], outputs=("out",)),
    Tool("gr2_tree", "tools/gr2_tree.py", "survey",
         L("Inspect a Granny model", "Inspeccionar un modelo Granny"),
         L("The data tree, statistics, types or shape of an uncompressed .gr2.",
           "El árbol de datos, estadísticas, tipos o forma de un .gr2 sin comprimir."),
         [Arg("model", None, "file", L("Model", "Modelo"), required=True, filters=GR2),
          Arg("mode", None, "choice", L("Show", "Mostrar"),
              choices=(("", "Tree"), ("--stats", "Statistics"), ("--types", "Types"), ("--shape", "Shape")),
              default="--stats")],
         writes="nothing"),

    # -- art utilities -----------------------------------------------------------------------
    Tool("make_flag", "tools/make_flag.py", "art",
         L("Civ flag set", "Juego de banderas de civilización"),
         L("A whole civ flag set (in-game flag, buttons, postgame flag) from one design image.",
           "Un juego completo de banderas (bandera en el juego, botones, bandera final) a partir de una imagen."),
         [Arg("design", "--design", "file", L("Flag design", "Diseño de la bandera"), required=True, filters=PNG),
          Arg("name", "--name", "text", L("Set name", "Nombre del juego"), required=True),
          game_dir(), out_dir(),
          Arg("flags_dir", "--flags-dir", "text", L("Flags folder in the copy", "Carpeta de banderas en la copia")),
          Arg("buttons_dir", "--buttons-dir", "text", L("Buttons folder in the copy", "Carpeta de botones en la copia")),
          Arg("preview", "--preview", "save", L("Preview sheet", "Hoja de vista previa"), filters=PNG),
          Arg("compare", "--compare", "text", L("Compare with", "Comparar con"), placeholder="japan,piratini"),
          Arg("fit_warp", "--fit-warp", "bool", L("Refit the warp (about a minute)", "Reajustar la deformación "
                                                  "(cerca de un minuto)"))],
         needs=("game",), outputs=("out", "preview")),
    Tool("make_icons", "tools/make_icons.py", "art",
         L("Test avatar icons", "Iconos de avatar de prueba"),
         L("Three small test icons for player avatars and the table that names them.",
           "Tres iconos de prueba para avatares de jugador y la tabla que los nombra."),
         [out_dir(required=False),
          Arg("prefix", "--prefix", "text", L("Prefix", "Prefijo"), default="test_"),
          Arg("table", "--table", "text", L("Table name", "Nombre de la tabla"))],
         outputs=("out",)),
    Tool("make_icons_install", "tools/make_icons.py", "art",
         L("Install avatar icons in the test copy", "Instalar iconos de avatar en la copia de prueba"),
         L("Writes the test icons and copies them into the test copy (a file already there is kept as .orig).",
           "Escribe los iconos de prueba y los copia en la copia de prueba (un archivo existente se guarda como "
           ".orig)."),
         [out_dir(required=False),
          Arg("prefix", "--prefix", "text", L("Prefix", "Prefijo"), default="test_"),
          Arg("install", "--install", "folder", L("Test copy", "Copia de prueba"), required=True, setting="test_copy")],
         needs=("test_copy",), writes="copy",
         confirm=L("This changes the test copy of the game.", "Esto modifica la copia de prueba del juego.")),
    Tool("make_rings", "tools/make_rings.py", "art",
         L("Ground rings and marks", "Anillos y marcas en el suelo"),
         L("Coloured ground rings, floating icons, rank marks and range rings for the effects folder.",
           "Anillos de colores en el suelo, iconos flotantes, insignias de rango y anillos de alcance."),
         [out_dir(required=False),
          Arg("folder", "--folder", "text", L("Effects folder name", "Nombre de la carpeta de efectos"),
              default="rings"),
          Arg("icon_sheet", "--icon-sheet", "file", L("Marker icons from a sheet", "Iconos de marcador de una hoja"),
              L("A drawn 3 x 3 sheet (PNG, or WebP with Pillow), one icon a cell: pickaxe, axe, meat; berries, hoe, "
                "fish; ship, leaves, oil drop. A white ground is made transparent. Empty: the drawn icons.",
                "Una hoja dibujada de 3 x 3 (PNG, o WebP con Pillow), un icono por celda: pico, hacha, carne; bayas, "
                "azada, pez; barco, hojas, gota de petróleo. Un fondo blanco se vuelve transparente. Vacío: los "
                "iconos dibujados."), filters=IMAGES),
          Arg("range_particles", "--range-particles", "bool", L("White range rings (particles)",
                                                                 "Anillos de alcance blancos (partículas)"),
              L("The range rings as white flat particles instead of meshes in the owner's colour.",
                "Los anillos de alcance como partículas planas blancas en vez de mallas del color del dueño.")),
          Arg("marker_sheet", "--marker-sheet", "save", L("Picture of the marker icons",
                                                           "Imagen de los iconos de marcador"),
              L("Each icon as drawn, enlarged, and at the sizes it takes in game, on grass, dirt, snow and dark.",
                "Cada icono como se dibujó, ampliado, y a los tamaños que ocupa en el juego, sobre hierba, tierra, nieve y oscuro."),
              filters=PNG, work="marker_icons.png")],
         outputs=("out",)),
    Tool("make_aura_rings", "tools/make_aura_rings.py", "art",
         L("Aura rings from the game's own", "Anillos de aura a partir de los del juego"),
         L("The ring of the Indian economic aura, recoloured in each ring colour, each colour a model of its own at "
           "the ground rings' sizes. Derived from the game's art: keep the result out of public places.",
           "El anillo del aura económica india, recoloreado en cada color de anillo, cada color con su propio modelo "
           "a los tamaños de los anillos del suelo. Sale del arte del juego: no publiques el resultado."),
         [Arg("game", "--game", "folder", L("Game folder", "Carpeta del juego"),
              L("Its art is only read; its granny2.dll uncompresses the mesh.",
                "Su arte solo se lee; su granny2.dll descomprime la malla."), required=True, setting="game"),
          out_dir(),
          Arg("folder", "--folder", "text", L("Effects folder name", "Nombre de la carpeta de efectos"),
              L("The folder under art\\effects\\ the files name, as for the ground rings.",
                "La carpeta bajo art\\effects\\ que nombran los archivos, como en los anillos del suelo."),
              default="rings"),
          Arg("compress", "--compress", "bool", L("Compress the models", "Comprimir los modelos"),
              L("Stores the copies compressed again (Oodle1), as the originals are.",
                "Guarda las copias comprimidas de nuevo (Oodle1), como los originales.")),
          Arg("preview", "--preview", "save", L("Picture of the colours", "Imagen de los colores"),
              L("The stock texture and every colour, enlarged, on grass, dirt and dark.",
                "La textura original y cada color, ampliados, sobre hierba, tierra y oscuro."),
              filters=PNG, work="aura_rings.png")],
         outputs=("out",)),
    Tool("make_bar", "tools/make_bar.py", "art",
         L("Health bar texture", "Textura de barra de vida"),
         L("A health-bar texture in another colour, shaded like the game's own bars.",
           "Una textura de barra de vida en otro color, sombreada como las del juego."),
         [Arg("colour", "--colour", "color", L("Colour", "Color"), default="FF8C00"),
          Arg("out", "--out", "save", L("Texture to write", "Textura a escribir"), filters=DDT, work="health_bar.ddt")],
         outputs=("out",)),
    Tool("ui_preview", "tools/ui_preview.py", "art",
         L("Preview an interface layout", "Vista previa de una disposición de la interfaz"),
         L("Draws a game UI layout file (ui*.xml or its .xmb) as a picture: every gadget's box numbered and "
           "coloured by nesting, the ones outside their parent in red, with a legend.",
           "Dibuja un archivo de disposición de la interfaz del juego (ui*.xml o su .xmb) como imagen: la caja de "
           "cada gadget numerada y coloreada según su anidamiento, en rojo las que salen de su padre, con una leyenda."),
         [Arg("layout", None, "file", L("Layout file", "Archivo de disposición"),
              L("A ui*.xml file of the game's data folder, or its compiled .xmb. It is only read.",
                "Un archivo ui*.xml de la carpeta data del juego, o su .xmb compilado. Solo se lee."),
              required=True, filters=XML),
          Arg("out", "--out", "save", L("Picture to write", "Imagen a escribir"),
              L("The PNG preview. Empty: ui_preview.png in the work folder.",
                "La vista previa en PNG. Vacío: ui_preview.png en la carpeta de trabajo."),
              filters=PNG, work="ui_preview.png"),
          Arg("scale", "--scale", "float", L("Scale", "Escala"),
              L("Pixels per unit of the game's 1024 x 768 layout space. Default 2.",
                "Píxeles por unidad del espacio de 1024 x 768 del juego. Por defecto 2."), default="2"),
          Arg("region", "--region", "text", L("Region", "Región"),
              L("auto (every box), or x1,y1,x2,y2 in the 1024 x 768 space.",
                "auto (todas las cajas), o x1,y1,x2,y2 en el espacio de 1024 x 768."), placeholder="auto"),
          Arg("hide", "--hide", "text", L("Leave out", "Dejar fuera"),
              L("A regular expression: gadgets whose name matches are not drawn, nor their children.",
                "Una expresión regular: los gadgets cuyo nombre coincide no se dibujan, ni sus hijos.")),
          Arg("mark", "--mark", "text", L("Highlight", "Resaltar"),
              L("A regular expression: gadgets whose name matches are filled in yellow (new rows of a proposal).",
                "Una expresión regular: los gadgets cuyo nombre coincide se rellenan de amarillo (filas nuevas de "
                "una propuesta).")),
          Arg("title", "--title", "text", L("Title", "Título"),
              L("A title written on the picture.", "Un título escrito en la imagen.")),
          Arg("strip", "--strip", "text", L("Name prefix to drop", "Prefijo de nombre a quitar"),
              L("Dropped from the names in the legend. Empty: the root's name followed by -.",
                "Se quita de los nombres en la leyenda. Vacío: el nombre de la raíz seguido de -.")),
          Arg("text", "--text", "bool", L("List each gadget's text", "Listar el texto de cada gadget"),
              L("The legend also shows what each gadget holds, such as its {...} placeholders.",
                "La leyenda muestra también lo que contiene cada gadget, como sus marcadores {...}.")),
          Arg("vline", "--vline", "text", L("Vertical guides", "Guías verticales"),
              L("x positions in the 1024 x 768 space, comma-separated: dashed lines to check symmetry.",
                "Posiciones x en el espacio de 1024 x 768, separadas por comas: líneas discontinuas para "
                "comprobar la simetría."), placeholder="512")],
         outputs=("out",)),
    Tool("make_stat_icon", "tools/make_stat_icon.py", "art",
         L("Stat icons for the unit panels", "Iconos de estadística para los paneles de unidad"),
         L("Draws the small icons the panels' rows put after a value (rate of fire, training time, line of "
           "sight, speed, armor, projectiles) as .ddt textures. No pixel comes from the game.",
           "Dibuja los iconos pequeños que las filas de los paneles ponen tras un valor (cadencia, tiempo de "
           "entrenamiento, línea de visión, velocidad, armadura, proyectiles) como texturas .ddt. Ningún píxel "
           "sale del juego."),
         [Arg("style", "--style", "choice", L("Style", "Estilo"),
              L("bold: 32x32 BGRA, hard edges and a black outline (the one to ship); soft: 16x16 DXT3, soft edges.",
                "bold: 32x32 BGRA, bordes duros y contorno negro (el que se usa); soft: 16x16 DXT3, bordes suaves."),
              choices=("bold", "soft"), default="bold"),
          Arg("glyph", "--glyph", "choice", L("Glyph", "Dibujo"),
              L("The icon to draw. The soft style also has heart, house and two speed variants; the bold one has "
                "the cylinder.",
                "El icono a dibujar. El estilo soft tiene además corazón, casa y dos variantes de velocidad; el "
                "bold tiene el tambor."),
              choices=("stopwatch", "hourglass", "eye", "boot_wings", "shield", "cylinder", "heart", "house",
                       "boot_arrows", "boot_lines"), default="stopwatch"),
          Arg("out", "--out", "save", L("Texture to write", "Textura a escribir"),
              L("The .ddt of one glyph. Empty: stat_icon.ddt in the work folder.",
                "El .ddt de un dibujo. Vacío: stat_icon.ddt en la carpeta de trabajo."),
              filters=DDT, work="stat_icon.ddt"),
          Arg("all", "--all", "outdir", L("Every glyph into", "Todos los dibujos en"),
              L("A folder: every glyph of the style is written there under its game file name "
                "(stat_icon_rof.ddt, ...), in place of the single texture.",
                "Una carpeta: cada dibujo del estilo se escribe allí con su nombre de archivo del juego "
                "(stat_icon_rof.ddt, ...), en lugar de la textura sola.")),
          Arg("png", "--png", "save", L("Preview picture", "Imagen de vista previa"),
              L("Also a PNG, enlarged 8 times, on the panel's brown and on grey.",
                "También un PNG, ampliado 8 veces, sobre el marrón del panel y sobre gris."), filters=PNG),
          Arg("check", "--check", "bool", L("Only compare", "Solo comparar"),
              L("Writes nothing: says whether the files on disk are what would be written.",
                "No escribe nada: dice si los archivos en disco son lo que se escribiría."))],
         outputs=("out", "all", "png")),
    Tool("make_type_icon", "tools/make_type_icon.py", "art",
         L("Unit type icons", "Iconos de tipo de unidad"),
         L("Draws the unit type icons a stat panel puts after a bonus multiplier (\"1.5x against <icon>\") in a "
           "painted style: 32x32 BGRA .ddt files under their game paths. No pixel comes from the game.",
           "Dibuja los iconos de tipo de unidad que un panel de estadísticas pone tras un multiplicador de "
           "bonificación (\"1.5x contra <icono>\") en un estilo pintado: archivos .ddt BGRA de 32x32 en sus rutas "
           "del juego. Ningún píxel sale del juego."),
         [out_dir(required=False, label=L("Art folder", "Carpeta art"),
                  help=L("Every glyph is written under this folder at its game path (ui/ingame/...). Empty: a folder "
                         "of its own in the work folder.",
                         "Cada dibujo se escribe en esta carpeta en su ruta del juego (ui/ingame/...). Vacío: una "
                         "carpeta propia dentro de la carpeta de trabajo.")),
          Arg("glyph", "--glyph", "text", L("Only these glyphs", "Solo estos dibujos"),
              L("Glyph names separated by spaces: line, standing, winged_arrow, winged_bullet (the alternative of "
                "winged_arrow, written only when named). Empty: line, standing and winged_arrow.",
                "Nombres de dibujo separados por espacios: line, standing, winged_arrow, winged_bullet (la "
                "alternativa de winged_arrow, solo se escribe si se nombra). Vacío: line, standing y winged_arrow."),
              repeat=True, placeholder="line standing"),
          Arg("png", "--png", "save", L("Preview picture", "Imagen de vista previa"),
              L("Also a PNG of the glyphs enlarged 8 times on the panel's brown.",
                "También un PNG con los dibujos ampliados 8 veces sobre el marrón del panel."), filters=PNG),
          Arg("check", "--check", "bool", L("Only compare", "Solo comparar"),
              L("Writes nothing: says whether the files in the art folder are what would be written.",
                "No escribe nada: dice si los archivos de la carpeta art son lo que se escribiría."))],
         outputs=("out", "png")),
    Tool("draw_praying_hands", "tools/draw_praying_hands.py", "art",
         L("Praying hands icon", "Icono de manos rezando"),
         L("Draws a praying hands icon (two hands pressed together, a white cuff, a brown sleeve) as a PNG, shaded "
           "like the painted resource icons of the in-game panel. No pixel comes from the game.",
           "Dibuja un icono de manos rezando (dos manos juntas, un puño blanco, una manga marrón) como PNG, "
           "sombreado como los iconos de recursos pintados del panel del juego. Ningún píxel sale del juego."),
         [Arg("out", "--out", "save", L("Picture to write", "Imagen a escribir"),
              L("The icon as a PNG. Empty: praying_hands.png in the work folder.",
                "El icono como PNG. Vacío: praying_hands.png en la carpeta de trabajo."), filters=PNG,
              work="praying_hands.png"),
          Arg("size", "--size", "int", L("Size", "Tamaño"),
              L("The square's side in pixels. Default 128.", "El lado del cuadrado en píxeles. Por defecto 128.")),
          Arg("halo", "--halo", "float", L("Halo", "Halo"),
              L("The strength of the pale gold halo behind the hands, 0 to 1. Default 0.35.",
                "La intensidad del halo dorado pálido detrás de las manos, de 0 a 1. Por defecto 0.35.")),
          Arg("tilt", "--tilt", "float", L("Tilt", "Inclinación"),
              L("Degrees the hands lean to the right. Default 6.",
                "Grados que las manos se inclinan a la derecha. Por defecto 6.")),
          Arg("width", "--width", "float", L("Width", "Anchura"),
              L("Horizontal stretch of the figure. Default 1.15.",
                "Estiramiento horizontal de la figura. Por defecto 1.15.")),
          Arg("sheet", "--sheet", "save", L("Preview picture", "Imagen de vista previa"),
              L("Also the icon at its size and at 64, 34 and 24 pixels on the panel's dark wood.",
                "También el icono a su tamaño y a 64, 34 y 24 píxeles sobre la madera oscura del panel."),
              filters=PNG)],
         outputs=("out", "sheet")),
    Tool("panel_rows", "tools/panel_rows.py", "art",
         L("Resource panel rows", "Filas del panel de recursos"),
         L("Re-lays the painted rows of a resource panel in the game's interface textures and inserts new rows "
           "with an icon of your own (a new resource), so the new row looks like the others. A JSON spec gives "
           "the panels' rows; the textures are rebuilt from the originals and only the panel's blocks change.",
           "Reorganiza las filas pintadas de un panel de recursos en las texturas de la interfaz del juego e "
           "inserta filas nuevas con un icono propio (un recurso nuevo), para que la fila nueva se vea como las "
           "demás. Un JSON describe las filas de los paneles; las texturas se reconstruyen desde las originales y "
           "solo cambian los bloques del panel."),
         [Arg("spec", "--spec", "file", L("Spec", "Especificación"),
              L("The JSON that names the textures, their panels' rows, the new order and the icons.",
                "El JSON que nombra las texturas, las filas de sus paneles, el orden nuevo y los iconos."),
              required=True, filters=JSON),
          Arg("src", "--in", "folder", L("Original textures folder", "Carpeta de las texturas originales"),
              L("The folder the spec's paths start from (a game copy's root): read only.",
                "La carpeta de la que parten las rutas de la especificación (la raíz de una copia del juego): "
                "solo se lee."), required=True, setting="game"),
          out_dir(required=False, help=L("The rebuilt .ddt files at the spec's paths. Empty: a folder of its own "
                                         "in the work folder.",
                                         "Los .ddt reconstruidos en las rutas de la especificación. Vacío: una "
                                         "carpeta propia dentro de la carpeta de trabajo.")),
          Arg("png", "--png", "outdir", L("PNG copies into", "Copias PNG en"),
              L("Also each rebuilt texture as a PNG, to look at.",
                "También cada textura reconstruida como PNG, para verla.")),
          Arg("positions", "--positions", "save", L("Row positions", "Posiciones de las filas"),
              L("A JSON with every panel's new rows (texture rows), to place a layout's gadgets on.",
                "Un JSON con las filas nuevas de cada panel (filas de la textura), para colocar los elementos de "
                "una interfaz."), filters=JSON)],
         outputs=("out", "png", "positions")),
    Tool("import_icon", "tools/import_icon.py", "art",
         L("Import a drawn icon", "Importar un icono dibujado"),
         L("Turns an icon drawn elsewhere (a PNG with a transparent background) into a game icon texture: a "
           "square, uncompressed BGRA .ddt with one level. Optionally recolours one region, narrows a wide picture "
           "between two sides, and widens it for a panel that squeezes square icons. Nothing is redrawn.",
           "Convierte un icono dibujado en otro programa (un PNG con fondo transparente) en una textura de icono "
           "del juego: un .ddt BGRA cuadrado, sin comprimir, con un nivel. Opcionalmente recolorea una región, "
           "estrecha un dibujo ancho entre dos lados y lo ensancha para un panel que aplasta los iconos cuadrados. "
           "No se redibuja nada."),
         [Arg("png", "--png", "file", L("Drawn icon", "Icono dibujado"),
              L("A PNG with a transparent background (a .ddt is read too).",
                "Un PNG con fondo transparente (también se lee un .ddt)."), required=True, filters=IMAGES),
          Arg("out", "--out", "save", L("Texture to write", "Textura a escribir"),
              L("The icon's .ddt. Empty: icon.ddt in the work folder.",
                "El .ddt del icono. Vacío: icon.ddt en la carpeta de trabajo."), filters=DDT, work="icon.ddt"),
          Arg("size", "--size", "int", L("Size", "Tamaño"),
              L("The square's side in texels. Default 32.", "El lado del cuadrado en téxeles. Por defecto 32.")),
          Arg("aspect", "--aspect", "float", L("Panel aspect", "Proporción del panel"),
              L("The share of its width a panel keeps when it draws a square icon; the picture is widened by "
                "1 / aspect so it shows with its own proportions in game (the minimized unit panel: 0.65). 1 keeps "
                "it as drawn. Default 0.72.",
                "La parte de su anchura que un panel conserva al dibujar un icono cuadrado; el dibujo se ensancha "
                "1 / proporción para que se vea con sus propias proporciones en el juego (el panel de unidad "
                "minimizado: 0.65). 1 lo deja como está dibujado. Por defecto 0.72.")),
          Arg("set_height", "--set-height", "float", L("Set height", "Altura del conjunto"),
              L("Source pixels that fill the square's height: one scale for every picture of a set. Empty: the "
                "longer side fills the square.",
                "Píxeles de origen que llenan la altura del cuadrado: una escala para todos los dibujos de un "
                "conjunto. Vacío: el lado más largo llena el cuadrado.")),
          Arg("valign", "--valign", "choice", L("Vertical place", "Posición vertical"),
              L("centre, or bottom (set on the bottom edge: busts cut at the waist).",
                "centre, o bottom (apoyado en el borde inferior: bustos cortados por la cintura)."),
              choices=("centre", "bottom"), default="centre"),
          Arg("tint", "--tint", "color", L("Recolour a region toward", "Recolorear una región hacia"),
              L("The region connected to the seed pixel takes this colour; its shading, highlights and dark bands "
                "stay, the outline and every other region keep their pixels.",
                "La región conectada al píxel semilla toma este color; se conservan su sombreado, sus brillos y sus "
                "bandas oscuras, y el contorno y las demás regiones guardan sus píxeles.")),
          Arg("tint_seed", "--tint-seed", "text", L("Seed pixel", "Píxel semilla"),
              L("X,Y: a pixel of the region to recolour, in the PNG's pixels. Needed with a colour.",
                "X,Y: un píxel de la región a recolorear, en píxeles del PNG. Necesario con un color."),
              placeholder="120,340"),
          Arg("tint_floor", "--tint-floor", "float", L("Region floor", "Umbral de la región"),
              L("Luminance (0-255) between the outline's and the region's darkest part. Default 35.",
                "Luminancia (0-255) entre la del contorno y la parte más oscura de la región. Por defecto 35.")),
          Arg("tint_mid", "--tint-mid", "float", L("Grey that becomes the colour", "Gris que pasa a ser el color"),
              L("The luminance (0-255) of the region's main face. Empty: the region's median.",
                "La luminancia (0-255) de la cara principal de la región. Vacío: la mediana de la región.")),
          Arg("tint_lighten", "--tint-lighten", "float", L("Lighten the colour", "Aclarar el color"),
              L("Mixes the colour toward white first, 0 to 1. Default 0.",
                "Mezcla primero el color hacia el blanco, de 0 a 1. Por defecto 0.")),
          Arg("sides", "--sides", "text", L("Sides", "Lados"),
              L("L,R: the middle's first column and the right side's first column, for a picture made of a middle "
                "between two sides (a bullet between its wings) to be narrowed without redrawing it.",
                "L,R: la primera columna del centro y la primera del lado derecho, para estrechar sin redibujarlo "
                "un dibujo hecho de un centro entre dos lados (una bala entre sus alas)."), placeholder="321,769"),
          Arg("sides_cut", "--sides-cut", "text", L("Cut from the sides", "Recorte de los lados"),
              L("A,B: the columns A..L-1 and R..B-1 are taken out, where the sides run straight.",
                "A,B: se quitan las columnas A..L-1 y R..B-1, donde los lados son rectos."), placeholder="186,904"),
          Arg("sides_scale", "--sides-scale", "float", L("Scale of the sides", "Escala de los lados"),
              L("Default 1.", "Por defecto 1.")),
          Arg("sides_tuck", "--sides-tuck", "int", L("Tuck the sides", "Meter los lados"),
              L("Pixels each side slides behind the middle. Default 0.",
                "Píxeles que cada lado se desliza detrás del centro. Por defecto 0.")),
          Arg("preview", "--preview", "save", L("Preview picture", "Imagen de vista previa"),
              L("Also a PNG of the result enlarged 8 times on the panel's brown.",
                "También un PNG del resultado ampliado 8 veces sobre el marrón del panel."), filters=PNG)],
         outputs=("out", "preview")),
    Tool("make_command_icon", "tools/make_command_icon.py", "art",
         L("Command button icons", "Iconos de botones de comando"),
         L("Draws a command button's two icons, on and off, in the style of Wars of Liberty's own buttons: 64x64 "
           "BGRA .ddt files, a blue frame, a green tick for on, a red tint and cross for off. No pixel comes from "
           "the game.",
           "Dibuja los dos iconos de un botón de comando, activado y desactivado, en el estilo de los botones de "
           "Wars of Liberty: archivos .ddt BGRA de 64x64, un marco azul, una marca verde para activado, un tinte y "
           "una cruz rojos para desactivado. Ningún píxel sale del juego."),
         [Arg("glyph", "--glyph", "choice", L("Glyph", "Dibujo"),
              L("autoscout: a map half explored with a dotted route and a spyglass (uhc_autoscout_start.ddt, "
                "uhc_autoscout_stop.ddt).",
                "autoscout: un mapa medio explorado con una ruta punteada y un catalejo (uhc_autoscout_start.ddt, "
                "uhc_autoscout_stop.ddt)."),
              choices=("autoscout",), default="autoscout"),
          out_dir(required=False, key="all", flag="--all",
                  help=L("Both icons are written there under their game file names. Empty: a folder of its own in "
                         "the work folder.",
                         "Los dos iconos se escriben allí con sus nombres de archivo del juego. Vacío: una carpeta "
                         "propia dentro de la carpeta de trabajo.")),
          Arg("png", "--png", "save", L("Preview picture", "Imagen de vista previa"),
              L("Also a PNG of both icons enlarged 4 times.", "También un PNG de los dos iconos ampliados 4 veces."),
              filters=PNG),
          Arg("check", "--check", "bool", L("Only compare", "Solo comparar"),
              L("Writes nothing: says whether the files in the folder are what would be written.",
                "No escribe nada: dice si los archivos de la carpeta son lo que se escribiría."))],
         outputs=("all", "png")),
    Tool("extend_font", "tools/extend_font.py", "art",
         L("Missing letters in a font", "Letras que faltan en una fuente"),
         L("Adds the accented Latin letters a TrueType font lacks (ă ș ț ő ł ...), built from its own letters and "
           "accents, under a new family name. Writes a new font, a proof sheet and a report.",
           "Añade a una fuente TrueType las letras latinas con acento que le faltan (ă ș ț ő ł ...), hechas con sus "
           "propias letras y acentos, con un nombre de familia nuevo. Escribe una fuente nueva, una hoja de prueba y "
           "un informe."),
         [Arg("input", None, "file", L("Font", "Fuente"), required=True, filters=TTF),
          Arg("output", None, "save", L("Font to write", "Fuente a escribir"), filters=TTF, work="extended.ttf"),
          Arg("family", "--family", "text", L("New family name", "Nuevo nombre de familia"),
              placeholder="Formal436 BT WoL"),
          Arg("suffix", "--suffix", "text", L("Suffix of the name", "Sufijo del nombre"), default="Ext"),
          Arg("only", "--only", "text", L("Only these letters", "Solo estas letras"), placeholder="ăâîșț,U+0218-U+021B"),
          Arg("proof", "--proof", "save", L("Proof sheet", "Hoja de prueba"), filters=PNG, work="proof.png"),
          Arg("report", "--report", "save", L("Report", "Informe"), filters=JSON, work="report.json"),
          Arg("no_kern", "--no-kern", "bool", L("No kerning copied", "Sin copiar el interletraje"))],
         needs=("fonttools",), outputs=("output", "proof", "report")),
    Tool("game_fonts_survey", "tools/game_fonts.py", "art",
         L("A copy's fonts: the letters they lack", "Fuentes de una copia: las letras que les faltan"),
         L("Every typeface FONTS\\fonts3.xml names, how many entries use it, where its file is (loose in FONTS, in "
           "Fonts.bar, or a Windows font) and which accented Latin letters it lacks (ă ș ț ő ł ...). Reads only.",
           "Cada tipografía que nombra FONTS\\fonts3.xml, cuántas entradas la usan, dónde está su archivo (suelto "
           "en FONTS, en Fonts.bar o una fuente de Windows) y qué letras latinas con acento le faltan (ă ș ț ő ł "
           "...). Solo lee."),
         [game_dir(),
          Arg("only", "--only", "text", L("Only these letters", "Solo estas letras"), placeholder="ăâîșț,U+0218-U+021B"),
          Arg("json", "--json", "save", L("Report (JSON)", "Informe (JSON)"), filters=JSON)],
         fixed=["survey"], needs=("game",), outputs=("json",)),
    Tool("game_fonts_stage", "tools/game_fonts.py", "art",
         L("A copy's fonts: add the letters they lack", "Fuentes de una copia: añadir las letras que faltan"),
         L("Every font of the copy that lacks letters, extended from its own letters and accents under a new family "
           "name (<typeface> <word>), and fonts3.xml pointed at them; written outside the copy, laid out as it, "
           "ready for \"Deploy edited files to the test copy\" (Undo takes it out). Fonts.bar is never changed.",
           "Cada fuente de la copia a la que le faltan letras, ampliada con sus propias letras y acentos con un nombre "
           "de familia nuevo (<tipografía> <palabra>), y fonts3.xml apuntando a ellas; se escribe fuera de la copia, "
           "con su estructura, lista para \"Desplegar archivos editados en la copia de prueba\" (Deshacer la quita). "
           "Fonts.bar nunca se cambia."),
         [game_dir(), out_dir(),
          Arg("suffix", "--suffix", "text", L("Word after the family names", "Palabra tras los nombres de familia"),
              required=True, placeholder="WoL"),
          Arg("families", "--families", "text", L("Only these typefaces", "Solo estas tipografías"),
              placeholder="Formal436 BT,Monotype Corsiva"),
          Arg("only", "--only", "text", L("Only these letters", "Solo estas letras"), placeholder="ăâîșț,U+0218-U+021B"),
          Arg("no_kern", "--no-kern", "bool", L("No kerning copied", "Sin copiar el interletraje"))],
         fixed=["stage"], needs=("game", "fonttools"), outputs=("out",)),
    Tool("fix_hitpointbar", "tools/fix_hitpointbar_tags.py", "art",
         L("Fix jumping health bars", "Arreglar barras de vida que saltan"),
         L("Adds the HITPOINTBAR tag to the animations of a unit that lack it, so its health bar stops jumping.",
           "Añade la etiqueta HITPOINTBAR a las animaciones de una unidad que no la tienen, para que su barra de "
           "vida deje de saltar."),
         [Arg("inputs", None, "folders", L("Anim files or folders", "Archivos de animación o carpetas")),
          Arg("art", "--art", "folder", L("Art folder", "Carpeta art")),
          Arg("proto", "--proto", "file", L("Proto", "Proto"), filters=XML),
          Arg("units", "--units", "text", L("Units", "Unidades"), placeholder="Musketeer,Pikeman"),
          Arg("out", "--out", "outdir", L("Output folder", "Carpeta de salida"),
              L("Empty: into the art folder itself (a replaced file is kept as .orig)",
                "Vacío: en la propia carpeta art (el archivo sustituido se guarda como .orig)"))],
         writes="in_place", trial=["--dry-run"], outputs=("out",)),
    Tool("fix_bone_scale", "tools/fix_bone_scale.py", "art",
         L("Fix bone scale", "Arreglar la escala de huesos"),
         L("Brings the attach and impact bones of Granny models to unit scale (effects drawn 100 times too big).",
           "Lleva a escala unidad los huesos de anclaje e impacto de modelos Granny (efectos dibujados 100 veces "
           "más grandes)."),
         [Arg("inputs", None, "folders", L("Models or folders", "Modelos o carpetas"), required=True),
          Arg("out", "-o", "outdir", L("Output", "Salida"),
              L("Empty: in place (a .bak copy is kept)", "Vacío: en el sitio (se guarda una copia .bak)")),
          Arg("bones", "--bones", "text", L("Bones (regex)", "Huesos (regex)")),
          Arg("factor", "--factor", "float", L("Factor", "Factor"), default=10.0),
          Arg("verbose", "-v", "bool", L("Verbose", "Detallado"))] + granny_args(),
         writes="in_place", trial=["--dry-run"], outputs=("out",)),
    Tool("dmg_bones", "tools/dmg_bones.py", "art",
         L("Damage templates' bones", "Huesos de las plantillas de daño"),
         L("Lists the damage templates whose parts name a bone the model using them lacks, or one its anim file "
           "does not define (<definebone>): the game reloads such a model while units still draw it and can crash. "
           "Optionally writes fixed copies of the anim files (the missing <definebone> lines) into a folder of "
           "your choice; the game folder is only read.",
           "Lista las plantillas de daño cuyas partes nombran un hueso que el modelo que las usa no tiene, o que su "
           "anim file no define (<definebone>): el juego recarga ese modelo mientras las unidades aún lo dibujan y "
           "puede cerrarse. Opcionalmente escribe copias corregidas de los anim files (las líneas <definebone> que "
           "faltan) en una carpeta que elijas; la carpeta del juego solo se lee."),
         [game_dir(flag=None),
          Arg("granny_install", "--granny-install", "folder", L("Game folder (for granny2.dll)",
                                                                "Carpeta del juego (para granny2.dll)"),
              L("Reads compressed models through its granny2.dll, never copied or changed. Empty: the game folder.",
                "Lee los modelos comprimidos con su granny2.dll, que nunca se copia ni se modifica. Vacío: la "
                "carpeta del juego.")),
          Arg("helper", "--helper", "file", L("Helper program", "Programa auxiliar"),
              L("granny_recompress.exe, built by \"Build the recompression helper\". Empty: the one built there.",
                "granny_recompress.exe, hecho con \"Construir el auxiliar de recompresión\". Vacío: el que se "
                "construyó ahí."),
              filters=(("Program", "*.exe"),), work=os.path.join("..", "recompress_helper", "granny_recompress.exe")),
          Arg("only", "--only", "text", L("Only anim files containing", "Solo anim files que contengan"),
              L("Only the anim files whose path contains this text (any case). Empty: every one.",
                "Solo los anim files cuya ruta contenga este texto (sin distinguir mayúsculas). Vacío: todos.")),
          Arg("csv", "--csv", "save", L("Table to write", "Tabla a escribir"),
              L("Every listed pair as a CSV table.", "Cada par listado como una tabla CSV."),
              filters=(("CSV", "*.csv"),)),
          Arg("fix", "--fix", "outdir", L("Fixed anim files into", "Anim files corregidos en"),
              L("A folder outside the game: a copy of every anim file with a bone not defined, with its <definebone> "
                "lines added, at art\\<its own path>. Empty: nothing is fixed.",
                "Una carpeta fuera del juego: una copia de cada anim file con un hueso sin definir, con sus líneas "
                "<definebone> añadidas, en art\\<su propia ruta>. Vacío: no se corrige nada.")),
          Arg("fix_list", "--fix-list", "save", L("List of the fixed files", "Lista de los archivos corregidos"),
              L("With a fix folder: one CSV row per file written.",
                "Con una carpeta de corrección: una fila CSV por archivo escrito."), filters=(("CSV", "*.csv"),))],
         needs=("game",), outputs=("csv", "fix", "fix_list")),
    Tool("fit_borrowed", "tools/fit_borrowed.py", "art",
         L("Fit to a borrowed template or animation", "Ajustar a una plantilla o animación prestada"),
         L("Fits models that borrow another model's damage template or death animation: debris meshes "
           "renamed on export (debris_1a.001) get the template's names, so those pieces break off; bones "
           "take the reference model's rest frames, so its animation places every piece right.",
           "Ajusta modelos que toman prestada la plantilla de daños o la animación de muerte de otro modelo: "
           "las mallas de escombros renombradas al exportar (debris_1a.001) reciben los nombres de la "
           "plantilla, para que esas piezas se desprendan; los huesos toman los marcos de reposo del modelo "
           "de referencia, para que su animación coloque bien cada pieza."),
         [Arg("inputs", None, "folders", L("Models or folders", "Modelos o carpetas"), required=True),
          Arg("out", "-o", "outdir", L("Output", "Salida"),
              L("Empty: in place (a .bak copy is kept)", "Vacío: en el sitio (se guarda una copia .bak)")),
          Arg("dmg", "--dmg", "file", L("Damage template", "Plantilla de daños"),
              filters=(("Damage template", "*.dmg *.xmb"),)),
          Arg("rest_from", "--rest-from", "file", L("Reference model", "Modelo de referencia"), filters=GR2),
          Arg("verbose", "-v", "bool", L("Verbose", "Detallado"))] + granny_args(),
         writes="in_place", trial=["--dry-run"], outputs=("out",)),
    Tool("uncompress_models", "tools/uncompress_models.py", "art",
         L("Uncompressed models (fewer stutters)", "Modelos sin comprimir (menos tirones)"),
         L("Uncompressed copies of the archived models as loose files of a game copy: fewer stutters when a new "
           "unit appears, faster loads. The trial shows the plan; Apply writes them.",
           "Copias sin comprimir de los modelos archivados como archivos sueltos de una copia del juego: menos "
           "tirones cuando aparece una unidad nueva y cargas más rápidas. La prueba muestra el plan; Aplicar las "
           "escribe."),
         [Arg("copy", None, "folder", L("Game copy", "Copia del juego"), required=True, setting="test_copy")]
         + granny_args() +
         [Arg("only_used", "--only-used", "file", L("Only the models of a list", "Solo los modelos de una lista")),
          Arg("workers", "--workers", "int", L("Workers", "Procesos")),
          Arg("work", "--work", "folder", L("Work folder", "Carpeta de trabajo"))],
         needs=("granny", "test_copy"), writes="copy", trial=[], commit=["--install"], minutes=5),
    Tool("make_dismount", "tools/make_dismount.py", "art",
         L("Dismount and mount animations", "Animaciones de desmontar y montar"),
         L("For a cavalry unit whose rider hangs on its horse: the rider's animations on foot beside the horse, "
           "made from the game's infantry animations, and the dismount and mount transitions, as Granny files "
           "with the anim file blocks; optional contact sheets and clips.",
           "Para una unidad de caballería cuyo jinete cuelga de su caballo: las animaciones del jinete a pie junto "
           "al caballo, hechas con las animaciones de infantería del juego, y las transiciones de desmontar y "
           "montar, como archivos Granny con los bloques del anim file; hojas de contacto y clips opcionales."),
         [game_dir(),
          out_dir(help=L("Where the animations, the anim file blocks and the sheets go. Never a Steam library.",
                         "Dónde van las animaciones, los bloques del anim file y las hojas. Nunca una "
                         "biblioteca de Steam.")),
          Arg("recipe", "--recipe", "file", L("Recipe (JSON)", "Receta (JSON)"),
              L("The unit's models, side and animations; empty: the Chasseur a Cheval of Wars of Liberty.",
                "Los modelos, el lado y las animaciones de la unidad; vacío: el Chasseur a Cheval de Wars of "
                "Liberty."), filters=JSON),
          Arg("horse", "--horse", "choice", L("The horse on foot", "El caballo a pie"),
              choices=("", "keep", "hide")),
          Arg("test", "--test", "bool", L("Test animations (heal, build)", "Animaciones de prueba (curar, construir)")),
          Arg("sheets", "--sheets", "bool", L("Contact sheets", "Hojas de contacto")),
          Arg("overview", "--overview", "bool", L("Review sheet", "Hoja de revisión")),
          Arg("clips", "--clips", "bool", L("Clips (needs ffmpeg)", "Clips (necesita ffmpeg)"))],
         needs=("game",), outputs=("out",)),
    Tool("make_pray", "tools/make_pray.py", "art",
         L("Villager praying animations", "Animaciones de aldeano rezando"),
         L("Three praying animations for the villagers (kneeling with joined hands, standing with the sign of "
           "the cross, bowing down to the ground), each an entry from the idle, a seamless loop and an exit, for "
           "the male and the female villager, as Granny files checked by the game's runtime; optional review "
           "sheet and GIFs.",
           "Tres animaciones de rezo para los aldeanos (de rodillas con las manos juntas, de pie con la señal de "
           "la cruz, inclinándose hasta el suelo), cada una con entrada desde el reposo, un bucle sin cortes y "
           "una salida, para el aldeano y la aldeana, como archivos Granny comprobados por el runtime del juego; "
           "hoja de revisión y GIF opcionales."),
         [game_dir(),
          out_dir(help=L("Where the animations, the anim file blocks and the report go. Never a Steam library.",
                         "Dónde van las animaciones, los bloques del anim file y el informe. Nunca una "
                         "biblioteca de Steam.")),
          Arg("design", "--design", "text", L("Designs", "Diseños"), default="1,2,3"),
          Arg("sex", "--sex", "text", L("Villagers", "Aldeanos"), default="male,female"),
          Arg("preview", "--preview", "save", L("Review sheet", "Hoja de revisión"), filters=(("PNG", "*.png"),)),
          Arg("gifs", "--gifs", "folder", L("GIF folder", "Carpeta de GIF")),
          Arg("no_verify", "--no-verify", "bool", L("Skip the runtime checks", "Omitir las comprobaciones del runtime"))],
         needs=("game",), outputs=("out",)),
    Tool("recompress_models", "tools/recompress_models.py", "art",
         L("Compress models again", "Volver a comprimir modelos"),
         L("Compresses Granny models a tool wrote uncompressed (a bone scale fix, an own texture, a rebake) through "
           "the game's own granny2.dll, so they ship at the originals' size. Every result is checked; nothing is "
           "written over an input.",
           "Comprime de nuevo, con el granny2.dll del propio juego, los modelos Granny que una herramienta escribió "
           "sin comprimir (escala de huesos, textura propia, un rebake), para que ocupen lo que los originales. Cada "
           "resultado se comprueba; nunca se escribe sobre una entrada."),
         [Arg("input", None, "folder", L("Models", "Modelos"),
              L("A folder: every .gr2 below it is compressed, at the same relative path below the output.",
                "Una carpeta: se comprime cada .gr2 que contenga, en la misma ruta relativa bajo la salida."),
              required=True),
          out_dir(flag="-o", help=L("Where the compressed models go. Empty: a folder in the work folder. Never an "
                                    "input folder or a Steam library.",
                                    "Dónde van los modelos comprimidos. Vacío: una carpeta en la de trabajo. Nunca "
                                    "una carpeta de entrada ni una biblioteca de Steam.")),
          Arg("granny_install", "--granny-install", "folder", L("Game folder (for granny2.dll)",
                                                                "Carpeta del juego (para granny2.dll)"),
              L("Its granny2.dll is used, never copied or changed.",
                "Se usa su granny2.dll, que nunca se copia ni se modifica."), required=True, setting="game"),
          Arg("like", "--like", "folder", L("Originals (same relative paths)", "Originales (mismas rutas relativas)"),
              L("Each section is stored as the original stores it (a section it keeps uncompressed stays so). "
                "Empty: every section in the chosen format.",
                "Cada sección se guarda como la guarda el original (la que deja sin comprimir, sigue así). Vacío: "
                "todas las secciones en el formato elegido.")),
          Arg("format", "--format", "choice", L("Format", "Formato"),
              L("oodle1 is the format of almost every model of the game; none writes them uncompressed.",
                "oodle1 es el formato de casi todos los modelos del juego; none los escribe sin comprimir."),
              choices=("oodle1", "oodle0", "none"), default="oodle1"),
          Arg("helper", "--helper", "file", L("Helper program", "Programa auxiliar"),
              L("granny_recompress.exe, built by \"Build the recompression helper\". Empty: the one built there.",
                "granny_recompress.exe, hecho con \"Construir el auxiliar de recompresión\". Vacío: el que se "
                "construyó ahí."),
              filters=(("Program", "*.exe"),), work=os.path.join("..", "recompress_helper", "granny_recompress.exe")),
          Arg("workers", "--workers", "int", L("Workers", "Procesos"),
              L("Models compressed at once. Default: half the processors.",
                "Modelos que se comprimen a la vez. Por defecto: la mitad de los procesadores.")),
          Arg("verbose", "-v", "bool", L("One line per model", "Una línea por modelo"),
              L("Lists every model with its sizes, not only the totals.",
                "Lista cada modelo con sus tamaños, no solo los totales."))],
         needs=("game",), outputs=("out",), minutes=3),
    Tool("retarget_anims", "tools/retarget_anims.py", "art",
         L("A unit's animations on another model", "Las animaciones de una unidad en otro modelo"),
         L("Puts one model's animations on another model's skeleton (by default the Aztec Macehualtin's slinger "
           "animations on a standard infantry model, where the game would not play them): Granny files and their "
           "tag files, the anim file blocks to paste, a report; optionally a review sheet and contact sheets.",
           "Pone las animaciones de un modelo en el esqueleto de otro (por defecto las de hondero del Macehualtin "
           "azteca en un modelo de infantería estándar, donde el juego no las reproduce): archivos Granny y sus "
           "archivos de etiquetas, los bloques del anim file para pegar y un informe; opcionalmente una hoja de "
           "revisión y hojas de contacto."),
         [game_dir(),
          out_dir(help=L("Where the animations, the anim file blocks and the sheets go. Never a Steam library.",
                         "Dónde van las animaciones, los bloques del anim file y las hojas. Nunca una "
                         "biblioteca de Steam.")),
          Arg("recipe", "--recipe", "text", L("Recipes", "Recetas"), repeat=True, placeholder="skirmisher native"),
          Arg("granny_helper", "--granny-helper", "file", L("Helper program", "Programa auxiliar"),
              filters=(("Program", "*.exe"),), work=os.path.join("..", "recompress_helper", "granny_recompress.exe")),
          Arg("only", "--only", "text", L("Only these clips", "Solo estos clips")),
          Arg("preview", "--preview", "save", L("Review sheet", "Hoja de revisión"), filters=(("PNG", "*.png"),)),
          Arg("preview_clips", "--preview-clips", "text", L("Clips of the review sheet", "Clips de la hoja de revisión")),
          Arg("sheets", "--sheets", "bool", L("Contact sheets", "Hojas de contacto")),
          Arg("fps", "--fps", "float", L("Samples a second", "Muestras por segundo"))],
         needs=("game",), outputs=("out",), minutes=2),
    Tool("gr2_check", "tools/gr2_check.py", "art",
         L("Check models with the game's runtime", "Comprobar modelos con el motor del juego"),
         L("What the game's own granny2.dll reads in a model (meshes, vertices, bone bindings, skeletons), beside "
           "what the studio reads; optionally the model written again from its own tree, which must read the same. "
           "Writes nothing.",
           "Lo que el granny2.dll del propio juego lee en un modelo (mallas, vértices, enlaces de huesos, esqueletos), "
           "junto a lo que lee el estudio; si se pide, el modelo escrito de nuevo desde su propio árbol, que debe "
           "leerse igual. No escribe nada."),
         [Arg("model", None, "file", L("Model, or a folder of them", "Modelo, o una carpeta de ellos"),
              L("A .gr2, or a folder: every .gr2 below it.", "Un .gr2, o una carpeta: cada .gr2 que contenga."),
              required=True, filters=(("Granny model", "*.gr2"),)),
          Arg("granny_install", "--granny-install", "folder", L("Game folder (for granny2.dll)",
                                                                "Carpeta del juego (para granny2.dll)"),
              L("Its granny2.dll is used, never copied or changed.",
                "Se usa su granny2.dll, que nunca se copia ni se modifica."), required=True, setting="game"),
          Arg("helper", "--helper", "file", L("Helper program", "Programa auxiliar"),
              L("granny_recompress.exe, built by \"Build the recompression helper\". Empty: the one built there.",
                "granny_recompress.exe, hecho con \"Construir el auxiliar de recompresión\". Vacío: el que se "
                "construyó ahí."),
              filters=(("Program", "*.exe"),), work=os.path.join("..", "recompress_helper", "granny_recompress.exe")),
          Arg("rewrite", "--rewrite", "bool", L("Also write it again from its own tree", "También escribirlo de nuevo desde su árbol"),
              L("The copy a unit transplant starts from: the runtime must read it as the original, its CRC valid.",
                "La copia de la que parte un trasplante de unidad: el motor debe leerla como el original, con su CRC válido.")),
          Arg("save", "--save", "save", L("Keep the rewritten copy", "Guardar la copia reescrita"),
              L("One model only: its rewritten copy, kept when the runtime reads it alike. Save it under a folder laid "
                "out as the copy (art/units/...) and deploy that folder for the in-game test.",
                "Un solo modelo: su copia reescrita, guardada si el motor la lee igual. Guárdala en una carpeta con la "
                "estructura de la copia (art/units/...) y despliega esa carpeta para la prueba en el juego."),
              filters=(("Granny model", "*.gr2"),)),
          Arg("limit", "--limit", "int", L("At most this many models", "Como mucho tantos modelos"),
              L("Of a folder, the first ones by name. Empty: all.", "De una carpeta, los primeros por nombre. Vacío: todos.")),
          Arg("verbose", "-v", "bool", L("One line per model", "Una línea por modelo"),
              L("Every model with what the runtime read, not only those that differ.",
                "Cada modelo con lo que leyó el motor, no solo los que difieren."))],
         needs=("game",), minutes=2),
    Tool("hc_survey", "tools/hc_survey.py", "survey",
         L("Home-city models survey", "Estudio de los modelos de las metrópolis"),
         L("Inventories the home-city models of a game copy or a mod (basis, bone scale, stored texture names and "
           "what uses each) and plans moving one home city's models into a folder of their own. Only reads the "
           "copy; the reports name the mod's files: keep them private.",
           "Inventaría los modelos de las metrópolis de una copia del juego o de un mod (base, escala de huesos, "
           "nombres de textura guardados y qué usa cada uno) y planifica mover los de una metrópoli a una carpeta "
           "propia. Solo lee la copia; los informes nombran archivos del mod: guárdalos en privado."),
         [Arg("game", "--game", "folder", L("Game copy", "Copia del juego"),
              L("Read only.", "Solo se lee."), required=True, setting="game"),
          out_dir(help=L("The reports: models.csv, textures.csv, refs.csv, summary.md, report.json, and a plan per "
                         "home city asked. Must be outside the game copy.",
                         "Los informes: models.csv, textures.csv, refs.csv, summary.md, report.json, y un plan por "
                         "cada metrópoli pedida. Debe estar fuera de la copia del juego.")),
          Arg("target", "--target", "text", L("Target tree", "Árbol de destino"),
              L("Where each home city's files should end, below art: <target>\\<civ>\\ (e.g. WoL\\homecity).",
                "Dónde deben acabar los archivos de cada metrópoli, bajo art: <destino>\\<civ>\\ (p. ej. "
                "WoL\\homecity)."), required=True, placeholder="WoL\\homecity"),
          Arg("plan", "--plan", "text", L("Plan for these home cities", "Plan para estas metrópolis"),
              L("A civ or file stem per plan, separated by spaces: plan_<name>.md lists its moves, texture renames "
                "and line changes.",
                "Una civ o nombre de archivo por plan, separados por espacios: plan_<nombre>.md lista sus "
                "movimientos, renombres de texturas y cambios de líneas."), repeat=True),
          cache_dir(),
          Arg("granny", "--granny", "file", L("Granny bridge", "Puente Granny"),
              L("The external .exe that expands compressed models the cache does not hold; needs a work folder.",
                "El .exe externo que expande los modelos comprimidos que la caché no tiene; necesita una carpeta "
                "de trabajo."), setting="granny", filters=(("Program", "*.exe"),)),
          Arg("work", "--work", "outdir", L("Bridge work folder", "Carpeta de trabajo del puente"),
              L("Where the bridge writes the expanded models, outside the game copy. Empty: the work folder.",
                "Dónde el puente escribe los modelos expandidos, fuera de la copia del juego. Vacío: la carpeta "
                "de trabajo."), work="bridge")],
         needs=("game",), outputs=("out",), minutes=5),
    Tool("reencode_textures", "tools/reencode_textures.py", "textures",
         L("Re-encode textures for older cards", "Recodificar texturas para tarjetas antiguas"),
         L("Each .ddt in a folder or list re-encoded by the rules (the format its header and pixels call for, "
           "halved above a size limit, a full mip chain) and compared with its original: one that strays too far "
           "is kept as it was. Writes the results and a report, never in place.",
           "Cada .ddt de una carpeta o lista recodificado según las reglas (el formato que piden su cabecera y sus "
           "píxeles, reducido a la mitad por encima de un límite, una cadena de mips completa) y comparado con su "
           "original: el que se aleja demasiado se queda como estaba. Escribe los resultados y un informe, nunca "
           "encima."),
         [Arg("input", "--in", "folder", L("Textures", "Texturas"),
              L("A folder of .ddt, or a list file of paths (the select step writes one).",
                "Una carpeta de .ddt, o un archivo con una lista de rutas (el paso de selección escribe una)."),
              required=True),
          out_dir(help=L("The re-encoded textures at their relative paths, report.json and report.csv.",
                         "Las texturas recodificadas en sus rutas relativas, report.json y report.csv.")),
          Arg("root", "--root", "folder", L("Folder the list is relative to", "Carpeta a la que se refiere la lista"),
              L("Only for a list file: its paths are relative to this folder.",
                "Solo para una lista: sus rutas son relativas a esta carpeta.")),
          Arg("limit", "--limit", "text", L("Size limit", "Límite de tamaño"),
              L("WxH: a texture with a side above it is halved until both fit. Give this or a measured limit.",
                "AxA: una textura con un lado mayor se reduce a la mitad hasta que ambos quepan. Indica esto o un "
                "límite medido."), placeholder="512x512"),
          Arg("tad", "--tad", "file", L("Measured limit (tad.json)", "Límite medido (tad.json)"),
              L("The stock home-city building textures' mean, from \"Measure the stock home-city textures\": the "
                "limit is twice it.",
                "La media de las texturas de edificios de las metrópolis originales, de \"Medir las texturas de "
                "las metrópolis originales\": el límite es el doble."), filters=JSON),
          Arg("smallest", "--smallest", "int", L("Smallest mip", "Mip más pequeño"),
              L("The chain goes down to this many pixels on the short side. Default 4, as the stock game.",
                "La cadena baja hasta estos píxeles en el lado corto. Por defecto 4, como el juego original.")),
          Arg("max_mean", "--max-mean", "float", L("Largest mean difference", "Diferencia media máxima"),
              L("Per channel, 0 to 255; above it the texture is kept as it was. Default 6.",
                "Por canal, de 0 a 255; por encima la textura se queda como estaba. Por defecto 6.")),
          Arg("max_block", "--max-block", "float", L("Largest block difference", "Diferencia máxima de bloque"),
              L("The worst 4 x 4 block's mean difference; above it the texture is kept. Default 32.",
                "La diferencia media del peor bloque de 4 x 4; por encima la textura se queda. Por defecto 32.")),
          Arg("sheets", "--sheets", "outdir", L("Comparison sheets", "Hojas de comparación"),
              L("A folder: one picture per texture (original, new, difference) and an index.html.",
                "Una carpeta: una imagen por textura (original, nueva, diferencia) y un index.html.")),
          Arg("fast", "--fast", "bool", L("Faster encoder", "Codificador más rápido"),
              L("The plain DXT encoder instead of the least-squares one: quicker, a little further from the "
                "original.",
                "El codificador DXT simple en vez del de mínimos cuadrados: más rápido, algo más lejos del "
                "original."))],
         fixed=["run"], outputs=("out", "sheets"), minutes=5),
    Tool("reencode_tad", "tools/reencode_textures.py", "textures",
         L("Measure the stock home-city textures", "Medir las texturas de las metrópolis originales"),
         L("The mean width and height of the stock game's home-city building textures, the limit the re-encoding "
           "can follow. Only reads the copy.",
           "El ancho y alto medios de las texturas de edificios de las metrópolis del juego original, el límite "
           "que puede seguir la recodificación. Solo lee la copia."),
         [Arg("game", "--game", "folder", L("Game copy", "Copia del juego"), L("Read only.", "Solo se lee."),
              required=True, setting="game"),
          Arg("out", "--out", "save", L("Measure to write", "Medida a escribir"),
              L("A JSON file. Empty: tad.json in the work folder.",
                "Un archivo JSON. Vacío: tad.json en la carpeta de trabajo."), filters=JSON, work="tad.json"),
          cache_dir(),
          Arg("granny", "--granny", "file", L("Granny bridge", "Puente Granny"),
              L("Expands compressed models the cache does not hold; needs a work folder.",
                "Expande los modelos comprimidos que la caché no tiene; necesita una carpeta de trabajo."),
              setting="granny", filters=(("Program", "*.exe"),)),
          Arg("work", "--work", "outdir", L("Bridge work folder", "Carpeta de trabajo del puente"),
              L("Outside the game copy. Empty: the work folder.", "Fuera de la copia del juego. Vacío: la carpeta "
                "de trabajo."), work="bridge")],
         fixed=["tad"], needs=("game",), outputs=("out",), minutes=5),
    Tool("reencode_select", "tools/reencode_textures.py", "textures",
         L("Choose the textures to re-encode", "Elegir las texturas a recodificar"),
         L("Lists a copy's own home-city building textures that only home-city buildings use (the ones safe to "
           "re-encode), and the others with why. Only reads the copy.",
           "Lista las texturas propias de edificios de metrópoli que solo usan esos edificios (las que se pueden "
           "recodificar sin riesgo), y las demás con el motivo. Solo lee la copia."),
         [Arg("game", "--game", "folder", L("Game copy", "Copia del juego"), L("Read only.", "Solo se lee."),
              required=True, setting="game"),
          Arg("out", "--out", "save", L("List to write", "Lista a escribir"),
              L("A text file of paths, for the re-encoding. Empty: select.txt in the work folder.",
                "Un archivo de texto con rutas, para la recodificación. Vacío: select.txt en la carpeta de "
                "trabajo."), filters=(("Text", "*.txt"),), work="select.txt"),
          cache_dir(),
          Arg("granny", "--granny", "file", L("Granny bridge", "Puente Granny"),
              L("Expands compressed models the cache does not hold; needs a work folder.",
                "Expande los modelos comprimidos que la caché no tiene; necesita una carpeta de trabajo."),
              setting="granny", filters=(("Program", "*.exe"),)),
          Arg("work", "--work", "outdir", L("Bridge work folder", "Carpeta de trabajo del puente"),
              L("Outside the game copy. Empty: the work folder.", "Fuera de la copia del juego. Vacío: la carpeta "
                "de trabajo."), work="bridge")],
         fixed=["select"], needs=("game",), outputs=("out",), minutes=5),
    Tool("hc_move_stage", "tools/hc_move.py", "art",
         L("Move a home city's models: prepare", "Mover los modelos de una metrópoli: preparar"),
         L("Writes, outside the game copy, a stage folder where one home city's own models (and the textures and "
           "anim files that go with them) sit in a folder of their own, with every reference edited and the "
           "originals zipped. Nothing in the copy is written.",
           "Escribe, fuera de la copia del juego, una carpeta de preparación donde los modelos propios de una "
           "metrópoli (y sus texturas y archivos de animación) quedan en una carpeta propia, con cada referencia "
           "editada y los originales en un zip. No se escribe nada en la copia."),
         [Arg("game", "--game", "folder", L("Game copy", "Copia del juego"), L("Read only.", "Solo se lee."),
              required=True, setting="game"),
          Arg("civ", "--civ", "text", L("Civ", "Civilización"),
              L("The home city to move, by its civ or file stem; _tables moves what only the shared tables name.",
                "La metrópoli a mover, por su civ o nombre de archivo; _tables mueve lo que solo nombran las "
                "tablas compartidas."), required=True),
          Arg("target", "--target", "text", L("Target tree", "Árbol de destino"),
              L("Below art, as the survey plans it (e.g. WoL\\homecity).",
                "Bajo art, como lo planifica el estudio (p. ej. WoL\\homecity)."), required=True,
              placeholder="WoL\\homecity"),
          out_dir(help=L("The stage: files\\ at their game paths, originals.zip, moved-files.txt, stage.json, "
                         "report.md.",
                         "La preparación: files\\ en sus rutas del juego, originals.zip, moved-files.txt, "
                         "stage.json, report.md.")),
          Arg("granny", "--granny", "file", L("Granny bridge", "Puente Granny"),
              L("Rebuilds each moved model so its stored texture names follow the textures.",
                "Reconstruye cada modelo movido para que sus nombres de textura sigan a las texturas."),
              required=True, setting="granny", filters=(("Program", "*.exe"),)),
          Arg("form", "--form", "choice", L("Form", "Forma"),
              L("A: art\\<target>, named with ..\\ from the home-city files (accepted in game). B: "
                "art\\homecity\\<Mod>.",
                "A: art\\<destino>, nombrado con ..\\ desde los archivos de la metrópoli (aceptado en el juego). "
                "B: art\\homecity\\<Mod>."), choices=("A", "B"), default="A"),
          Arg("shared", "--shared", "text", L("Shared folder", "Carpeta compartida"),
              L("Where models several civs' home cities use go. Default _shared.",
                "Dónde van los modelos que usan las metrópolis de varias civs. Por defecto _shared."),
              placeholder="_shared"),
          cache_dir(),
          Arg("work", "--work", "outdir", L("Bridge work folder", "Carpeta de trabajo del puente"),
              L("Outside the game copy. Empty: the work folder.", "Fuera de la copia del juego. Vacío: la carpeta "
                "de trabajo."), work="bridge"),
          Arg("suffix", "--suffix", "bool", L("Header digits in texture names", "Dígitos de cabecera en los nombres"),
              L("Renames each moved .ddt that only .tga/.png/.jpg names reach to <name>.(u,a,f,m).ddt, the game's "
                "way to read a stored name's header (in game 2026-11-17).",
                "Renombra cada .ddt movido al que solo llegan nombres .tga/.png/.jpg a <nombre>.(u,a,f,m).ddt, la "
                "forma del juego de leer la cabecera de un nombre guardado (en el juego, 2026-11-17).")),
          Arg("reencoded", "--reencoded", "file", L("Re-encoded textures (report.json)",
                                                    "Texturas recodificadas (report.json)"),
              L("A moved .ddt that is still the file it was made from ships as its re-encoded copy.",
                "Un .ddt movido que sigue siendo el archivo del que salió se lleva como su copia recodificada."),
              filters=JSON)],
         fixed=["stage"], needs=("game", "granny"), outputs=("out",), minutes=10),
    Tool("hc_move_install", "tools/hc_move.py", "art",
         L("Move a home city's models: install", "Mover los modelos de una metrópoli: instalar"),
         L("Copies a stage into the test copy, after checking every file it replaces is the one it was made from; "
           "keeps a backup.",
           "Copia una preparación en la copia de prueba, tras comprobar que cada archivo que sustituye es el "
           "original; guarda una copia de seguridad."),
         [Arg("bed", "--bed", "folder", L("Test copy", "Copia de prueba"),
              L("A copy of the game for testing (never the Steam folder: it is refused).",
                "Una copia del juego para pruebas (nunca la carpeta de Steam: se rechaza)."),
              required=True, setting="test_copy"),
          Arg("stage", "--stage", "folder", L("Stage folder", "Carpeta de preparación"),
              L("What \"prepare\" wrote.", "Lo que escribió \"preparar\"."), required=True)],
         fixed=["install"], needs=("test_copy",), writes="copy",
         confirm=L("This changes the test copy of the game: the stage is copied in and the moved originals deleted. "
                   "A backup is kept and Undo restores it.",
                   "Esto modifica la copia de prueba del juego: se copia la preparación y se borran los originales "
                   "movidos. Se guarda una copia de seguridad y Deshacer la restaura.")),
    Tool("hc_move_undo", "tools/hc_move.py", "art",
         L("Move a home city's models: undo", "Mover los modelos de una metrópoli: deshacer"),
         L("Puts the last install back, checking every file by its hash.",
           "Deshace la última instalación, comprobando cada archivo por su huella."),
         [Arg("bed", "--bed", "folder", L("Test copy", "Copia de prueba"),
              L("A copy of the game for testing (never the Steam folder: it is refused).",
                "Una copia del juego para pruebas (nunca la carpeta de Steam: se rechaza)."),
              required=True, setting="test_copy")],
         fixed=["undo"], needs=("test_copy",), writes="copy",
         confirm=L("This restores the test copy as it was before the last home-city move.",
                   "Esto restaura la copia de prueba como estaba antes del último movimiento de metrópoli.")),
    Tool("recompress_helper", "tools/recompress_models.py", "art",
         L("Build the recompression helper", "Construir el auxiliar de recompresión"),
         L("Compiles the small 32-bit program that hosts the game's granny2.dll (tools/granny_recompress.c), with "
           "Visual Studio's C++ tools or zig. Needed once, before compressing models again.",
           "Compila el pequeño programa de 32 bits que carga el granny2.dll del juego (tools/granny_recompress.c), "
           "con las herramientas C++ de Visual Studio o con zig. Hace falta una vez, antes de volver a comprimir."),
         [Arg("out", None, "save", L("Program to write", "Programa a escribir"),
              L("Empty: granny_recompress.exe in the work folder, where the compression form looks for it.",
                "Vacío: granny_recompress.exe en la carpeta de trabajo, donde lo busca el formulario de compresión."),
              filters=(("Program", "*.exe"),), work="granny_recompress.exe")],
         fixed=["--build-helper"], outputs=("out",)),
    Tool("uncompress_check", "tools/uncompress_models.py", "art",
         L("Check the uncompressed models", "Comprobar los modelos sin comprimir"),
         L("Reads the manifest back: every copy present and unchanged.",
           "Relee el manifiesto: cada copia presente y sin cambios."),
         [Arg("copy", None, "folder", L("Game copy", "Copia del juego"), required=True, setting="test_copy")],
         fixed=["--check"], writes="nothing"),
    Tool("uncompress_undo", "tools/uncompress_models.py", "art",
         L("Remove the uncompressed models", "Quitar los modelos sin comprimir"),
         L("Removes exactly the copies it wrote whose content is unchanged.",
           "Quita exactamente las copias que escribió y que no han cambiado."),
         [Arg("copy", None, "folder", L("Game copy", "Copia del juego"), required=True, setting="test_copy")],
         fixed=["--undo"], writes="copy",
         confirm=L("This removes the uncompressed copies from the game copy.",
                   "Esto quita las copias sin comprimir de la copia del juego.")),

    # -- developer tools ---------------------------------------------------------------------
    Tool("spec_sheets", "tools/spec_sheets.py", "dev",
         L("Technical sheets of the presets", "Fichas técnicas de los presets"),
         L("The technical sheet of every preset, and their index.", "La ficha técnica de cada preset y su índice."),
         [out_dir(),
          Arg("proto", "--proto", "file", L("Game proto", "Proto del juego"), filters=XML),
          Arg("only", "--only", "text", L("Only these presets", "Solo estos presets"), rest=True)],
         outputs=("out",), dev=True),
    Tool("sweep", "scripts/sweep.py", "dev",
         L("Parameter sweep", "Barrido de parámetros"),
         L("Random option sets through the game-ready checks.",
           "Conjuntos de opciones al azar pasados por las comprobaciones."),
         [Arg("count", "--count", "int", L("Count", "Cantidad"), default=200),
          Arg("seeds", "--seeds", "text", L("Seeds", "Semillas")),
          Arg("style", "--style", "choice", L("Style", "Estilo"), choices=("",) + STYLES)],
         engine="blender", needs=("blender",), writes="nothing", dev=True),
    Tool("gallery", "tools/gallery.py", "dev",
         L("Gallery of presets", "Galería de presets"),
         L("A labelled grid of rendered presets (the README's galleries).",
           "Una cuadrícula de presets renderizados (las galerías del README)."),
         [Arg("out", "--out", "save", L("Picture", "Imagen"), required=True, filters=(("JPEG", "*.jpg"),)),
          Arg("style", "--style", "choice", L("Style", "Estilo"), choices=("",) + STYLES),
          Arg("cols", "--cols", "int", L("Columns", "Columnas"), default=6),
          Arg("cell", "--cell", "text", L("Cell", "Celda"), default="480x360"),
          Arg("presets", None, "text", L("Presets", "Presets"), rest=True)],
         engine="blender", needs=("blender",), outputs=("out",), dev=True),
    Tool("ai_sweep", "tools/ai_sweep.py", "dev",
         L("AI repaint sweep", "Barrido del repintado IA"),
         L("Repaints presets at several strengths and seeds and measures each result.",
           "Repinta presets con varias fuerzas y semillas y mide cada resultado."),
         [out_dir(),
          Arg("presets", "--presets", "text", L("Presets", "Presets"), placeholder="COLONIAL_HOUSE,TIMBER_HOUSE"),
          Arg("strengths", "--strengths", "text", L("Strengths", "Fuerzas"), placeholder="0.3,0.45,0.6"),
          Arg("seeds", "--seeds", "text", L("Seeds", "Semillas"), placeholder="1,2"),
          Arg("regions", "--regions", "text", L("Regions", "Regiones"), placeholder="front,roof"),
          Arg("size", "--size", "int", L("Size", "Tamaño"), default=512),
          comfy_url()],
         needs=("comfy",), outputs=("out",), dev=True),
    Tool("style_fit", "tools/style_check.py", "dev",
         L("Fit the painter to the mod", "Ajustar el pintor al mod"),
         L("The grain band per material role that brings it to the mod's median.",
           "La banda de grano por material que lo acerca a la mediana del mod."),
         [Arg("style", "--style", "choice", L("Style", "Estilo"), choices=STYLES, default="AFRICAN"),
          Arg("presets", None, "text", L("Presets", "Presets"), rest=True)],
         fixed=["--fit"], needs=("profile",), writes="nothing", dev=True),
    Tool("shape_summary", "tools/shape_survey.py", "dev",
         L("Shape table into a profile", "Tabla de formas en un perfil"),
         L("Writes the per-class shape table of a shape survey into a building profile (rewrites that file).",
           "Escribe la tabla de formas por clase de un estudio de formas en un perfil de edificios (reescribe ese "
           "archivo)."),
         [Arg("summary", "--summary", "file", L("Shape survey result", "Resultado del estudio de formas"),
              required=True, filters=JSON),
          Arg("profile", "--profile", "file", L("Profile to update", "Perfil a actualizar"), required=True,
              filters=JSON)],
         writes="in_place", dev=True,
         confirm=L("This rewrites the profile file in place.", "Esto reescribe el archivo de perfil.")),
    Tool("fetch_materials", "tools/fetch_materials.py", "dev",
         L("Download the material swatches", "Descargar las muestras de material"),
         L("Downloads the CC0 swatches, checks each licence and prepares them in the add-on's folder.",
           "Descarga las muestras CC0, comprueba cada licencia y las prepara en la carpeta del complemento."),
         [Arg("names", None, "text", L("Only these", "Solo estas"), rest=True),
          Arg("cache", "--cache", "folder", L("Download cache", "Caché de descargas"))],
         needs=("network",), writes="repo", dev=True),
    Tool("build_zip", "tools/build_zip.py", "dev",
         L("Build the add-on zips", "Crear los zip del complemento"),
         L("The installable Blender add-on zips, into dist/.", "Los zip instalables del complemento de Blender, en "
                                                               "dist/."),
         [], writes="repo", dev=True),
]
TOOLS.insert(next(i for i, t in enumerate(TOOLS) if t.id == "game_export") + 1, Tool(
    "game_export_noblender", "scripts/game_export_noblender.py", "buildings",
    L("Export a preset for the game, without Blender (experimental)",
      "Exportar un preset al juego, sin Blender (experimental)"),
    L("The same bundle without Blender: the mesh, icons and checks made by this program. Whether it looks the "
      "same in game is still to verify.",
      "El mismo paquete sin Blender: la malla, los iconos y las comprobaciones los hace este programa. Falta "
      "verificar en el juego que se vea igual."),
    [*next(t for t in TOOLS if t.id == "game_export").args,
     Arg("compare", "--compare", "folder", L("Compare with (a Blender bundle)", "Comparar con (un paquete de Blender)"),
         L("A bundle of the same building made with Blender: each file is compared and the differences listed.",
           "Un paquete del mismo edificio hecho con Blender: se compara cada archivo y se listan las diferencias."))],
    outputs=("out",)))

BY_ID = {t.id: t for t in TOOLS}


def _fill_help():
    """An option declared without help takes its text from studio/catalog_help.py."""
    from .catalog_help import HELP
    for t in TOOLS:
        for a in t.args:
            if not a.help["en"] and a.key in HELP.get(t.id, {}):
                a.help = L(*HELP[t.id][a.key])


_fill_help()


# -- requirements ---------------------------------------------------------------------------

def requirements(st):
    """Which needs are met now."""
    s = st.settings
    out = {"blender": st.bridge.available, "granny": bool(s.get("granny")) and os.path.isfile(s.get("granny")),
           "game": bool(s.get("game")) and os.path.isdir(s.get("game")),
           "test_copy": bool(s.get("test_copy")) and os.path.isdir(s.get("test_copy")),
           "network": True}
    import importlib.util
    out["fonttools"] = importlib.util.find_spec("fontTools") is not None
    out["comfy"] = comfy_alive(s.get("comfy_url"))
    try:
        from . import use_core
        use_core()
        from core import profile
        out["profile"] = profile.art("textures") is not None
    except Exception:
        out["profile"] = False
    return out


def comfy_alive(url):
    if not url:
        return False
    try:
        from core import comfy
        return bool(comfy.Client(url, timeout=0.5).alive())
    except Exception:
        return False


def to_json(st):
    return {"areas": AREAS, "needs": NEEDS, "writes": WRITES, "tools": [t.public() for t in TOOLS],
            "requirements": requirements(st)}


# -- command lines --------------------------------------------------------------------------

def values_key(tool_id, values):
    return hashlib.sha256(json.dumps([tool_id, values], sort_keys=True).encode()).hexdigest()


def _bad(v, kind):
    if kind == "int":
        int(str(v).strip())
    elif kind == "float":
        float(str(v).strip())
    elif kind == "color":
        s = str(v).strip().lstrip("#")
        if len(s) != 6 or any(c not in "0123456789abcdefABCDEF" for c in s):
            raise ValueError
        return s.upper()
    return v


def build_args(tool, values):
    """The command line options of a tool from a form's values (validated)."""
    known = {a.key for a in tool.args}
    unknown = set(values) - known
    if unknown:
        raise ToolError("unknown options: " + ", ".join(sorted(unknown)))
    pos, flags, rest = [], [], []
    for a in tool.args:
        v = values.get(a.key)
        if isinstance(v, str):
            v = v.strip()
        empty = v is None or v == "" or v == [] or v is False
        if empty:
            if a.required:
                raise ToolError(f"{a.label['en']} is needed")
            continue
        if a.kind == "bool":
            flags.append(a.flag)
            continue
        if a.kind in ("int", "float", "color"):
            try:
                v = _bad(v, a.kind)
            except (TypeError, ValueError):
                raise ToolError(f"{a.label['en']}: not a valid {a.kind}") from None
        if a.kind == "choice":
            allowed = [c[0] if isinstance(c, tuple) else c for c in a.choices]
            if v not in allowed:
                raise ToolError(f"{a.label['en']}: not one of the choices")
        items = v if isinstance(v, list) else [v]
        if a.kind in ("files", "folders") and isinstance(v, str):
            items = [v]
        elif a.kind == "text" and a.repeat and isinstance(v, str):
            items = v.split()                   # several words, each after its own flag
        items = [str(x) for x in items]
        if a.rest:
            words = [w for x in items for w in x.split()]
            rest += ([a.flag] if a.flag else []) + words
        elif a.flag is None:
            if a.kind == "choice":
                pos += [x for x in items if x]
            else:
                pos += items
        elif a.repeat:
            for x in items:
                flags += [a.flag, x]
        elif a.kind in ("files", "folders"):
            flags += [a.flag] + items
        else:
            flags += [a.flag, items[0]]
    return pos, flags, rest


def command(st, tool_id, values, apply=False):
    """(command, title, outputs, cwd, trial key) for running a tool with these values; the trial
    key is set when this run is a tool's trial (the server keeps its job to allow the commit)."""
    tool = BY_ID.get(tool_id)
    if tool is None:
        raise ToolError(f"no tool {tool_id}")
    values = dict(values)
    for a in tool.args:                     # an output the form left empty: in the work folder
        if a.work is not None and not values.get(a.key):
            values[a.key] = os.path.normpath(os.path.join(st.work_dir(tool.id), a.work)) if a.work else st.work_dir(tool.id)
    pos, flags, rest = build_args(tool, values)
    args = tool.fixed + pos + flags
    trial = None
    if tool.trial is not None:
        key = values_key(tool_id, values)
        if apply:
            ok = st.trials.get(key)
            job = st.jobs.get(ok) if ok else None
            if job is None or job.status != "done" or job.code != 0:
                raise ToolError("run the trial with these values first; Apply is allowed once it has passed")
            args += tool.commit
        else:
            args += tool.trial
            trial = key
    elif apply:
        raise ToolError("this tool has no trial: run it directly")
    args += rest
    for a in tool.args:                     # never write into the game or a Steam library
        if a.kind in ("outdir", "save") and values.get(a.key):
            try:
                st.settings.check_output(str(values[a.key]))
            except Exception as e:          # deploy.RefusedPath
                raise ToolError(str(e)) from None
    script = os.path.join(ROOT, tool.script)
    if tool.engine == "blender":
        try:
            cmd = st.bridge.command(script, args)
        except RuntimeError as e:
            raise ToolError(str(e)) from None
    else:
        cmd = python_command() + [script] + args
    outputs = [str(values[k]) for k in tool.outputs if values.get(k) and isinstance(values[k], str)]
    title = tool.title["en"] + (" (trial)" if trial else "")
    return cmd, title, outputs, ROOT, trial


if __name__ == "__main__":                   # a listing, for a quick look
    for t in TOOLS:
        print(f"{t.id:22} {t.area:10} {t.script}")
    sys.exit(0)
