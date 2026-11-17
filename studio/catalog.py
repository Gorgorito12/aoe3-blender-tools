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
    Tool("deploy", "tools/game_deploy.py", "buildings",
         L("Deploy bundles to the test copy", "Desplegar paquetes en la copia de prueba"),
         L("Installs one or more game bundles into a test copy of the game. Undo takes them out again.",
           "Instala uno o más paquetes en una copia de prueba del juego. Deshacer los quita de nuevo."),
         [Arg("install", "--install", "folder", L("Test copy", "Copia de prueba"), required=True, setting="test_copy"),
          Arg("bundle", "--bundle", "folders", L("Bundles", "Paquetes"), required=True, repeat=True),
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
              default="rings")],
         outputs=("out",)),
    Tool("make_bar", "tools/make_bar.py", "art",
         L("Health bar texture", "Textura de barra de vida"),
         L("A health-bar texture in another colour, shaded like the game's own bars.",
           "Una textura de barra de vida en otro color, sombreada como las del juego."),
         [Arg("colour", "--colour", "color", L("Colour", "Color"), default="FF8C00"),
          Arg("out", "--out", "save", L("Texture to write", "Textura a escribir"), filters=DDT, work="health_bar.ddt")],
         outputs=("out",)),
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
         [Arg("names", None, "text", L("Only these", "Solo estas")),
          Arg("cache", "--cache", "folder", L("Download cache", "Caché de descargas"))],
         needs=("network",), writes="repo", dev=True),
    Tool("build_zip", "tools/build_zip.py", "dev",
         L("Build the add-on zips", "Crear los zip del complemento"),
         L("The installable Blender add-on zips, into dist/.", "Los zip instalables del complemento de Blender, en "
                                                               "dist/."),
         [], writes="repo", dev=True),
]
BY_ID = {t.id: t for t in TOOLS}


# -- requirements ---------------------------------------------------------------------------

def requirements(st):
    """Which needs are met now."""
    s = st.settings
    out = {"blender": st.bridge.available, "granny": bool(s.get("granny")) and os.path.isfile(s.get("granny")),
           "game": bool(s.get("game")) and os.path.isdir(s.get("game")),
           "test_copy": bool(s.get("test_copy")) and os.path.isdir(s.get("test_copy")),
           "network": True}
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
            values[a.key] = os.path.join(st.work_dir(tool.id), a.work) if a.work else st.work_dir(tool.id)
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
