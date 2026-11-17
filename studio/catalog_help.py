# SPDX-License-Identifier: GPL-3.0-or-later
"""The help of every form option that studio/catalog.py declares without one: what it does,
its unit and its default, in English and Spanish, read from each script's own docs and code.
catalog.py fills an option's empty help from here; tests/test_studio.py fails on an option
left without help in either language."""

HELP = {
    'ai_sweep': {
        'presets': (
            "Comma-separated presets to repaint. Empty: COLONIAL_HOUSE, COLONIAL_TRADING_HOUSE, TIMBER_HOUSE, TIMBER_INN and WHITE_HOUSE.",
            "Presets a repintar, separados por comas. Vacío: COLONIAL_HOUSE, COLONIAL_TRADING_HOUSE, TIMBER_HOUSE, TIMBER_INN y WHITE_HOUSE."),
        'regions': (
            "Comma-separated texture regions to repaint (front, roof...). Empty: every region that has a prompt.",
            "Regiones de la textura a repintar, separadas por comas (front, roof...). Vacío: todas las regiones con descripción."),
        'seeds': (
            "Comma-separated seeds to try at each strength. Empty: 1 and 2.",
            "Semillas, separadas por comas, que se prueban con cada fuerza. Vacío: 1 y 2."),
        'size': (
            "Side of each preset's painted texture, in pixels, before it is repainted.",
            "Lado de la textura pintada de cada preset, en píxeles, antes de repintarla."),
        'strengths': (
            "Comma-separated repaint strengths from 0 to 1 (how much the AI may change). Empty: 0.3, 0.45 and 0.6.",
            "Fuerzas de repintado de 0 a 1, separadas por comas (cuánto puede cambiar la IA). Vacío: 0.3, 0.45 y 0.6."),
        'url': (
            "Address of the local ComfyUI; default http://127.0.0.1:8188.",
            "Dirección del ComfyUI local; por defecto http://127.0.0.1:8188."),
    },
    'art_survey': {
        'bar': (
            "Also reads the .bar archives below the folders, in memory; nothing is extracted.",
            "También lee los archivos .bar que haya dentro de las carpetas, en memoria; no se extrae nada."),
        'folders': (
            "The game folder or mod folders to survey; every loose file below them is read.",
            "La carpeta del juego o las carpetas del mod que se estudian; se lee cada archivo suelto que haya dentro."),
        'label': (
            "A name for the report. Empty: the first folder's name.",
            "Un nombre para el informe. Vacío: el nombre de la primera carpeta."),
        'profile_out': (
            "Writes a building profile JSON with measurements only, naming no file of the mod.",
            "Escribe un perfil de edificios en JSON solo con medidas, sin nombrar ningún archivo del mod."),
        'proto': (
            "The game's unit list (protoy.xml): each building is joined to its anim file, models, decal, construction stages and obstruction.",
            "La lista de unidades del juego (protoy.xml): cada edificio se une a su archivo de animación, modelos, calcomanía, fases de construcción y obstrucción."),
        'reference': (
            "Another survey's report.json (the base game's, say): references found there are marked as reused, and the report says which files are new.",
            "El report.json de otro estudio (por ejemplo, del juego base): las referencias que estén en él se marcan como reutilizadas y el informe dice qué archivos son nuevos."),
    },
    'bar_extract': {
        'archive': (
            "The game archive (.bar) to extract from.",
            "El archivo del juego (.bar) del que extraer."),
        'filter': (
            "Extracts only files whose stored path contains this text (not case-sensitive, either slash). Empty: every file.",
            "Extrae solo los archivos cuya ruta guardada contiene este texto (sin distinguir mayúsculas, con cualquier barra). Vacío: todos."),
    },
    'bar_list': {
        'archive': (
            "The .bar archive whose files are listed with their sizes.",
            "El archivo .bar cuyos archivos se listan con sus tamaños."),
        'filter': (
            "Lists only stored paths containing this text, ignoring case; either slash works. Empty: every file.",
            "Lista solo las rutas que contienen este texto, sin distinguir mayúsculas; sirve cualquier barra. Vacío: todos los archivos."),
    },
    'check': {
        'budget': (
            "Triangle count above which a warning is given, used when there is no measured budget for the building's footprint class. Default 6000.",
            "Número de triángulos por encima del cual se avisa, usado cuando no hay presupuesto medido para la clase de huella del edificio. Por defecto 6000."),
        'detail': (
            "Builds the building at this detail level, LOW or MEDIUM. Empty: the detail level the preset or options already have.",
            "Construye el edificio con este nivel de detalle, LOW o MEDIUM. Vacío: el nivel que ya tienen el preset o las opciones."),
        'no_profile': (
            "Ignores the calibration profile, so the building is held to the fixed triangle budget above instead of the one measured for its footprint class.",
            "Ignora el perfil de calibración, así que el edificio se compara con el presupuesto fijo de arriba y no con el medido para su clase de huella."),
        'preset': (
            "The building to build and check, from the list of presets. Used only when no building's options file is given.",
            "El edificio que se construye y comprueba, de la lista de presets. Solo se usa si no das un archivo de opciones de edificio."),
    },
    'deploy': {
        'bundle': (
            "Bundle folders written by the game export (each holds a bundle.json). Several are deployed together, each with its own id and strings.",
            "Carpetas de paquetes escritas por la exportación al juego (cada una con su bundle.json). Varias se despliegan juntas, cada una con su id y sus textos."),
        'install': (
            "The test copy of the game the bundles go into. A folder inside a Steam library is refused; backups are kept for Undo.",
            "La copia de prueba del juego donde se instalan los paquetes. Se rechaza una carpeta dentro de una biblioteca de Steam; se guardan copias de seguridad para Deshacer."),
    },
    'deploy_grouping': {
        'grouping': (
            "Grouping XML files (settlements) copied into every RM*/groupings folder of the copy; a file they replace is backed up for Undo.",
            "Archivos XML de grouping (asentamientos) copiados en cada carpeta RM*/groupings de la copia; el archivo que sustituyen se respalda para Deshacer."),
        'install': (
            "The test copy of the game to change. A folder inside a Steam library is refused.",
            "La copia de prueba del juego que se modifica. Se rechaza una carpeta dentro de una biblioteca de Steam."),
    },
    'deploy_undo': {
        'install': (
            "The test copy to restore: what was deployed is taken out and the backed-up files are put back, as its manifest lists them.",
            "La copia de prueba a restaurar: se quita lo desplegado y se devuelven los archivos respaldados, según los lista su manifiesto."),
    },
    'deploy_validate': {
        'install': (
            "The test copy whose own validators (validate_proto.py, validate_techtree.py, validate_stringtable.py at its root) are run.",
            "La copia de prueba cuyos validadores propios (validate_proto.py, validate_techtree.py, validate_stringtable.py en su raíz) se ejecutan."),
    },
    'fetch_materials': {
        'cache': (
            "Folder where the downloaded archives are kept and reused. Empty: ~/.cache/aoe3bt-materials.",
            "Carpeta donde se guardan y reutilizan los archivos descargados. Vacío: ~/.cache/aoe3bt-materials."),
        'names': (
            "The swatches to download, separated by spaces: plaster, ashlar, stone_rough, clay, timber, thatch, mud. Empty, or no name of that list: every swatch.",
            "Las muestras que se descargan, separadas por espacios: plaster, ashlar, stone_rough, clay, timber, thatch, mud. Vacío, o ningún nombre de esa lista: todas las muestras."),
    },
    'fix_bone_scale': {
        'bones': (
            "A regular expression that narrows the bones fixed by name (not case-sensitive). Empty: every bone no mesh is bound to that is off scale.",
            "Una expresión regular que limita por nombre los huesos que se arreglan (sin distinguir mayúsculas). Vacío: cada hueso sin malla y fuera de escala."),
        'factor': (
            "A bone is fixed when its scale is at least this many times off unit length. Default: 10 (fixes 100 and 0.01, not 0.24 to 4).",
            "Un hueso se arregla si su escala se aleja de la unidad al menos esta cantidad de veces. Por defecto: 10 (arregla 100 y 0.01, no 0.24 a 4)."),
        'inputs': (
            "Granny models (.gr2), or folders searched for every .gr2 below them.",
            "Modelos Granny (.gr2), o carpetas en las que se busca cada .gr2 que contengan."),
        'verbose': (
            "Also lists the bones kept and the files left unchanged.",
            "También lista los huesos conservados y los archivos que no cambian."),
    },
    'fix_hitpointbar': {
        'art': (
            "The game's or mod's art folder, where the tag files are found (loose first, then its .bar archives). Empty: the folder named art above the first input.",
            "La carpeta art del juego o del mod, donde se buscan los archivos de etiquetas (sueltos primero, luego sus .bar). Vacío: la carpeta llamada art por encima de la primera entrada."),
        'inputs': (
            "Anim files (.xml or .xmb) or folders searched for them. Can be left empty when a proto is given.",
            "Archivos de animación (.xml o .xmb) o carpetas donde buscarlos. Puede quedar vacío si se indica un proto."),
        'proto': (
            "A protoy.xml or .xmb: every unit in it (or only those in Units) is checked through its anim file, loose or archived.",
            "Un protoy.xml o .xmb: se revisa cada unidad que contiene (o solo las de Unidades) a través de su archivo de animación, suelto o archivado."),
        'units': (
            "Comma-separated proto unit names to check, used with a proto. Empty: every unit of the proto.",
            "Nombres de unidades del proto, separados por comas, a revisar; se usa con un proto. Vacío: todas las unidades del proto."),
    },
    'gallery': {
        'cell': (
            "Size of each preset's picture, width x height in pixels. Default: 480x360.",
            "Tamaño de la imagen de cada preset, ancho x alto en píxeles. Por defecto: 480x360."),
        'cols': (
            "How many pictures per row of the grid. Default: 6.",
            "Cuántas imágenes por fila de la cuadrícula. Por defecto: 6."),
        'out': (
            "The JPEG picture to write with the grid of rendered presets.",
            "La imagen JPEG que se escribe con la cuadrícula de presets renderizados."),
        'presets': (
            "Preset names separated by spaces, in grid order. Empty: every preset of the chosen style.",
            "Nombres de presets separados por espacios, en el orden de la cuadrícula. Vacío: cada preset del estilo elegido."),
        'style': (
            "Renders every preset of this style. Used only when no presets are listed.",
            "Renderiza cada preset de este estilo. Solo se usa si no se indican presets."),
    },
    'game_export': {
        'ai_seed': (
            "Seed of the AI repaint: another number gives another result. Used only with an AI repaint strength; default 1.",
            "Semilla del repintado IA: otro número da otro resultado. Solo se usa con una fuerza de repintado IA; por defecto 1."),
        'ai_url': (
            "Address of the local ComfyUI the AI repaint uses; default http://127.0.0.1:8188.",
            "Dirección del ComfyUI local que usa el repintado IA; por defecto http://127.0.0.1:8188."),
        'detail': (
            "LOW: flat walls with painted windows; MEDIUM: recessed windows and doors, finer trim. Empty: the preset's own detail.",
            "LOW: muros planos con ventanas pintadas; MEDIUM: ventanas y puertas empotradas, molduras más finas. Vacío: el detalle propio del preset."),
        'display': (
            "The name players see in the game. Empty: the unit's name.",
            "El nombre que ven los jugadores en el juego. Vacío: el nombre de la unidad."),
        'folder': (
            "The art subfolder, inside the mod folder, the files go under. Empty: buildings, or objects for a prop (a generated treasure goes to nuggets).",
            "La subcarpeta de arte, dentro de la carpeta del mod, donde van los archivos. Vacío: buildings, u objects para un prop (un tesoro generado va a nuggets)."),
        'kind': (
            "BUILDING gets construction stages, rubble and a placement file; PROP is a map object with only an Idle animation. Empty: BUILDING, or PROP for a prop preset.",
            "BUILDING lleva fases de construcción, escombros y archivo de colocación; PROP es un objeto del mapa con solo animación Idle. Vacío: BUILDING, o PROP para un preset de prop."),
        'materials': (
            "Lays CC0 photo swatches under the painting, giving walls and roofs a real material grain.",
            "Coloca muestras fotográficas CC0 bajo la pintura, para dar a muros y tejados un grano de material real."),
        'name': (
            "The unit's name in the game, also used for its files and art folder (in lowercase). Empty: the preset's name.",
            "El nombre de la unidad en el juego, que también nombra sus archivos y su carpeta de arte (en minúsculas). Vacío: el nombre del preset."),
        'no_damaged': (
            "Leaves out the damaged model that replaces the intact one once the building has lost hit points. A prop never has one.",
            "Omite el modelo dañado que sustituye al intacto cuando el edificio pierde puntos de vida. Un prop nunca lo tiene."),
        'no_icons': (
            "Skips rendering the icon and portrait, so no _icon.ddt or _portrait.ddt is written.",
            "No renderiza el icono ni el retrato, así que no se escriben _icon.ddt ni _portrait.ddt."),
        'no_lowpoly': (
            "Leaves out the low-poly model the game draws at its low model detail setting.",
            "Omite el modelo de pocos polígonos que el juego dibuja con el ajuste de detalle de modelos bajo."),
        'no_profile': (
            "Ignores any calibration profile and sizes the obstruction, decal, stages and rubble with built-in fixed ratios.",
            "Ignora cualquier perfil de calibración y calcula la obstrucción, la calcomanía, las fases y los escombros con proporciones fijas internas."),
        'no_v_flip': (
            "Writes the texture coordinates as Blender stores them, instead of flipping V (1 − v) as is done by default for the game.",
            "Escribe las coordenadas de textura como las guarda Blender, en lugar de invertir V (1 − v) como se hace por defecto para el juego."),
        'player_colour': (
            "Paints the parts that show the owner's colour (texture alpha 0 there) and uses the game's player-colour shader. Needs DXT3 or BGRA.",
            "Pinta las partes que muestran el color del dueño (alfa 0 en la textura) y usa el shader de color del jugador. Necesita DXT3 o BGRA."),
        'preset': (
            "The building or prop to generate and export, with its own options unless the fields below change them.",
            "El edificio o prop que se genera y exporta, con sus propias opciones salvo las que cambien los campos de abajo."),
        'profile': (
            "A calibration profile (.json) that sets the obstruction, ground decal, construction stages and rubble from measured buildings. Empty: the profile shipped with the add-on.",
            "Un perfil de calibración (.json) que fija la obstrucción, la calcomanía del suelo, las fases de construcción y los escombros según edificios medidos. Vacío: el perfil incluido en el complemento."),
        'proto': (
            "The game's protoy.xml: the technical sheet (SPECS.md) then also shows the hit points and cost of its unit or template. Nothing else uses it.",
            "El protoy.xml del juego: la ficha técnica (SPECS.md) muestra entonces también los puntos de vida y el coste de su unidad o plantilla. No se usa para nada más."),
        'texture': (
            "How the .ddt texture is stored: DXT3 (the game's usual, keeps alpha), DXT1 (no alpha, so no player colour) or BGRA (uncompressed, larger).",
            "Cómo se guarda la textura .ddt: DXT3 (la habitual del juego, conserva el alfa), DXT1 (sin alfa, así que sin color del jugador) o BGRA (sin comprimir, más pesada)."),
    },
    'game_export_set': {
        'display': (
            "The name players and the scenario editor see. Empty: the set's own name.",
            "El nombre que ven los jugadores y el editor de escenarios. Vacío: el nombre propio del set."),
        'folder': (
            "The folder below the mod folder under art where the set's files go. Default: objects.",
            "La carpeta, dentro de la carpeta del mod en art, donde van los archivos del set. Por defecto: objects."),
        'no_icons': (
            "Skips rendering the icon and portrait, so the bundle has none and the proto names none.",
            "No renderiza el icono ni el retrato, así que el paquete no los incluye y el proto no los nombra."),
        'prefix': (
            "The mod's own folder under art; the files go to art/<this>/<art folder>/<set name>. Default: mod.",
            "La carpeta propia del mod dentro de art; los archivos van a art/<esta>/<carpeta de arte>/<nombre del set>. Por defecto: mod."),
        'set': (
            "Which prop set to build: GOODS (crates, barrels, sacks, pots, logs) or CAMP (tent, fire, pole, racks, drum, rock).",
            "Qué set de props construir: GOODS (cajas, barriles, sacos, vasijas, troncos) o CAMP (tienda, fuego, poste, bastidores, tambor, roca)."),
        'template': (
            "The existing unit whose proto entry the set copies. Default: PropsColony, a stock prop set.",
            "La unidad existente cuya entrada de proto copia el set. Por defecto: PropsColony, un set de props del juego."),
        'texture': (
            "Format of the .ddt texture: DXT3 (default, keeps alpha), DXT1 (no alpha, so no player colour) or BGRA (uncompressed).",
            "Formato de la textura .ddt: DXT3 (por defecto, con alfa), DXT1 (sin alfa, así que sin color del jugador) o BGRA (sin comprimir)."),
        'texture_size': (
            "Side in pixels of the one texture all the set's models share. Default: 256.",
            "Lado en píxeles de la única textura que comparten todos los modelos del set. Por defecto: 256."),
    },
    'generate': {
        'detail': (
            "LOW (flat walls, painted windows) or MEDIUM (recessed windows and doors, more triangles). Empty: the preset's own level.",
            "LOW (paredes planas, ventanas pintadas) o MEDIUM (ventanas y puertas hundidas, más triángulos). Vacío: el nivel propio del preset."),
        'materials': (
            "Lays the add-on's photo material swatches under the painted texture instead of flat colour.",
            "Pone las muestras de material fotográficas del complemento bajo la textura pintada en lugar de color plano."),
        'no_render': (
            "Writes the model, texture and exports but no preview pictures, which is much faster.",
            "Escribe el modelo, la textura y las exportaciones pero ninguna imagen de vista previa, lo que es mucho más rápido."),
        'poly': (
            "Multiplies the segments of every round body (walls, cones, domes, arches): 1.0 is the style's own, 0.6 cheaper, 1.5 finer. Empty: the preset's value.",
            "Multiplica los segmentos de cada cuerpo redondo (muros, conos, cúpulas, arcos): 1.0 es lo del estilo, 0.6 más barato, 1.5 más fino. Vacío: el valor del preset."),
        'preset': (
            "The ready-made building or prop to generate. Without an output folder it is written to examples/<name>/.",
            "El edificio o prop predefinido que se genera. Sin carpeta de salida se escribe en examples/<nombre>/."),
        'textures': (
            "A texture library folder: its textures that have a style and a role replace the add-on's swatches for that style and role.",
            "Una carpeta de biblioteca de texturas: sus texturas con estilo y papel sustituyen a las muestras del complemento de ese estilo y papel."),
    },
    'gr2_tree': {
        'mode': (
            "Tree: every value, one line each; Statistics: triangles, vertices, size, bones, textures; Types: type definitions; Shape: the structure, to compare two files.",
            "Árbol: cada valor, uno por línea; Estadísticas: triángulos, vértices, tamaño, huesos, texturas; Tipos: definiciones de tipos; Forma: la estructura, para comparar dos archivos."),
        'model': (
            "An uncompressed Granny model (.gr2). Most game models are compressed and must first be rewritten uncompressed by another tool.",
            "Un modelo Granny (.gr2) sin comprimir. La mayoría de modelos del juego están comprimidos y otra herramienta debe reescribirlos sin comprimir primero."),
    },
    'grouping_survey': {
        'folder': (
            "The game or mod folder whose groupings (RM*\\groupings\\*.xml) are measured.",
            "La carpeta del juego o del mod cuyos groupings (RM*\\groupings\\*.xml) se miden."),
        'out': (
            "A JSON report of every grouping measured. It names files and protos: keep it private. Empty: no report is written.",
            "Un informe JSON de cada grouping medido. Nombra archivos y protos: mantenlo privado. Vacío: no se escribe informe."),
        'profile_out': (
            "A numbers-only profile (like groupings.json) that the settlement composer works from. Empty: no profile is written.",
            "Un perfil solo con números (como groupings.json) con el que trabaja el compositor de asentamientos. Vacío: no se escribe perfil."),
        'proto': (
            "The game's protoy.xml, to classify each placed unit by its UnitType list. Empty: each is classified by its name alone.",
            "El protoy.xml del juego, para clasificar cada unidad colocada por su lista de UnitType. Vacío: se clasifica solo por su nombre."),
        'reference': (
            "The original game's folder: a grouping whose text is also there counts as stock, the rest as the mod's own.",
            "La carpeta del juego original: un grouping cuyo texto también está ahí cuenta como del juego, el resto como propio del mod."),
    },
    'lora_dataset': {
        'categories': (
            "Comma-separated art categories to take textures from. Empty: buildings, buildingsets, homecity, objects, nuggets and other.",
            "Categorías de arte, separadas por comas, de las que tomar texturas. Vacío: buildings, buildingsets, homecity, objects, nuggets y other."),
        'max': (
            "Stops after writing this many pieces. Default 900.",
            "Se detiene tras escribir esta cantidad de fragmentos. Por defecto 900."),
        'models': (
            "A model survey report: with it, only textures a model actually wears are used, leaving out icons, decals and other loose pictures.",
            "Un informe del estudio de modelos: con él solo se usan texturas que lleva algún modelo, dejando fuera iconos, calcomanías y otras imágenes sueltas."),
        'report': (
            "The textures.json of a texture survey. Only the mod's own diffuse textures, 512 pixels and up, are used, never the original game's.",
            "El textures.json de un estudio de texturas. Solo se usan las texturas difusas propias del mod, de 512 píxeles o más, nunca las del juego original."),
        'seed': (
            "Sets the random order of textures and pieces: the same seed gives the same dataset. Default 1.",
            "Fija el orden al azar de texturas y fragmentos: la misma semilla da el mismo dataset. Por defecto 1."),
        'side': (
            "Side of each square piece, in pixels; smaller textures are skipped, larger ones give up to four pieces. Default 512.",
            "Lado de cada fragmento cuadrado, en píxeles; las texturas más pequeñas se omiten y las mayores dan hasta cuatro fragmentos. Por defecto 512."),
        'trigger': (
            "The word each caption (.txt beside each piece) starts with, naming the style the LoRA learns. Default aoe3bt.",
            "La palabra con la que empieza cada descripción (.txt junto a cada fragmento) y que nombra el estilo que aprende el LoRA. Por defecto aoe3bt."),
    },
    'make_bar': {
        'colour': (
            "The bar's main colour as RRGGBB; its lighter and darker shades are worked out from it. Default: FF8C00, an orange.",
            "El color principal de la barra en RRGGBB; sus tonos más claros y oscuros se calculan a partir de él. Por defecto: FF8C00, un naranja."),
        'out': (
            "The 16x8 DXT1 .ddt texture to write. Empty: health_bar.ddt in the work folder.",
            "La textura .ddt de 16x8 en DXT1 que se escribe. Vacío: health_bar.ddt en la carpeta de trabajo."),
    },
    'make_flag': {
        'buttons_dir': (
            "Folder under art where the copy's flag buttons are measured and the new buttons are written. Empty: War of the Triple Alliance\\Buttons.",
            "Carpeta dentro de art donde se miden los botones de bandera de la copia y se escriben los nuevos. Vacío: War of the Triple Alliance\\Buttons."),
        'compare': (
            "Comma-separated names of existing flag sets shown beside the new one in the preview sheet.",
            "Nombres de juegos de banderas existentes, separados por comas, que se muestran junto al nuevo en la hoja de vista previa."),
        'design': (
            "A PNG of the flat flag: the whole cloth, hoist on the left. RGB or RGBA; the alpha is ignored.",
            "Un PNG de la bandera plana: la tela entera, con el asta a la izquierda. RGB o RGBA; el alfa se ignora."),
        'fit_warp': (
            "Refits, on this copy's sets, how the flag is bent onto the postgame painting's cloth, instead of using the stored fit.",
            "Reajusta, con los juegos de esta copia, cómo se dobla la bandera sobre la tela de la pintura final, en lugar de usar el ajuste guardado."),
        'flags_dir': (
            "Folder under art where the copy's flag sets are measured and the new flag and postgame flag are written. Empty: War of the Triple Alliance\\Flags.",
            "Carpeta dentro de art donde se miden las banderas de la copia y se escriben la nueva bandera y la bandera final. Vacío: War of the Triple Alliance\\Flags."),
        'name': (
            "The set's name, used in every file name (for example flag_<name>_normal.ddt and ingame_ui_postgame_flag_<name>.ddt).",
            "El nombre del juego de banderas, usado en cada nombre de archivo (por ejemplo flag_<nombre>_normal.ddt e ingame_ui_postgame_flag_<nombre>.ddt)."),
        'preview': (
            "Also writes a PNG sheet: one row per texture kind, the new set beside the compared ones, each with its alpha.",
            "Escribe además una hoja PNG: una fila por tipo de textura, el nuevo juego junto a los comparados, cada uno con su alfa."),
    },
    'make_icons': {
        'prefix': (
            "Starts the icon file names and avatar IDs: <prefix>blue.ddt, <prefix>red.ddt, <prefix>green.ddt. Default test_.",
            "Inicio de los nombres de los iconos y de los ID de avatar: <prefijo>blue.ddt, <prefijo>red.ddt, <prefijo>green.ddt. Por defecto test_."),
        'table': (
            "Another file name for the avatar table, ending in .xml. Empty: avatar_<prefix>icons.xml.",
            "Otro nombre de archivo para la tabla de avatares, terminado en .xml. Vacío: avatar_<prefijo>icons.xml."),
    },
    'make_icons_install': {
        'install': (
            "The test copy: the icons go into art\\ui\\playericons and the table into data; a file already there is kept as .orig. Steam folders are refused.",
            "La copia de prueba: los iconos van a art\\ui\\playericons y la tabla a data; un archivo ya existente se guarda como .orig. Se rechazan las carpetas de Steam."),
        'prefix': (
            "Put before each icon's file name and avatar ID (<prefix>blue.ddt, avatar_<prefix>icons.xml). Letters, digits and _ only; default test_.",
            "Se antepone al nombre de archivo y al ID de avatar de cada icono (<prefijo>blue.ddt, avatar_<prefijo>icons.xml). Solo letras, cifras y _; por defecto test_."),
    },
    'make_rings': {
        'folder': (
            "The one folder name under art/effects/ the files are meant for; it goes into the paths they name. Default: rings.",
            "El nombre de la carpeta dentro de art/effects/ a la que van los archivos; entra en las rutas que nombran. Por defecto: rings."),
    },
    'make_texture': {
        'category': (
            "What the texture is for (buildings, units, nuggets...), to choose which of the mod's textures it is compared with. Empty: buildings.",
            "Para qué es la textura (buildings, units, nuggets...), para elegir con qué texturas del mod se compara. Vacío: buildings."),
        'folder': (
            "Where the texture library is kept. Empty: Documents/aoe3-blender-tools/textures in your user folder.",
            "Dónde se guarda la biblioteca de texturas. Vacío: Documents/aoe3-blender-tools/textures en tu carpeta de usuario."),
        'image': (
            "A photo to make the texture from; alone it is only tiled and de-lit. A PNG is read directly; other formats need Blender.",
            "Una foto de la que hacer la textura; sola, solo se hace repetible y se le quita la luz. Un PNG se lee directamente; otros formatos necesitan Blender."),
        'keep_light': (
            "Keeps the picture's broad light and shade instead of dividing it out (removing it suits a photograph).",
            "Conserva la luz y sombra general de la imagen en lugar de quitarla (quitarla conviene a una fotografía)."),
        'lora': (
            "A LoRA file from ComfyUI's models/loras to draw with, such as one trained on the mod's textures; its trigger word is added to the prompt.",
            "Un archivo LoRA de models/loras de ComfyUI con el que dibujar, como uno entrenado con las texturas del mod; su palabra clave se añade a la descripción."),
        'lora_strength': (
            "How strongly the LoRA shapes the drawing. Empty: 0.8.",
            "Con cuánta fuerza el LoRA influye en el dibujo. Vacío: 0.8."),
        'material': (
            "What the texture is of (wood, stone, roof...): it is compared with the mod's own textures of that material.",
            "De qué es la textura (wood, stone, roof...): se compara con las texturas propias del mod de ese material."),
        'name': (
            "The texture's name in the library: it is saved as <name>.png, with <name>.json and a 3 by 3 preview <name>_x3.png.",
            "El nombre de la textura en la biblioteca: se guarda como <nombre>.png, con <nombre>.json y una vista 3 por 3 <nombre>_x3.png."),
        'no_fit': (
            "Leaves the grain and saturation as made instead of bringing them to the median of the mod's matching textures.",
            "Deja el grano y la saturación como salieron en lugar de acercarlos a la mediana de las texturas equivalentes del mod."),
        'no_heal': (
            "Skips the ComfyUI pass that redraws the blended band across the middle where the texture was joined to tile.",
            "Omite la pasada de ComfyUI que redibuja la franja mezclada del centro donde se unió la textura para que se repita."),
        'role': (
            "The material role it replaces in the style, such as roof or wall; used only together with a style.",
            "El papel de material que sustituye en el estilo, como roof o wall; solo se usa junto con un estilo."),
        'seed': (
            "Seed for what ComfyUI draws; another number gives another variation. Default: 1.",
            "Semilla de lo que dibuja ComfyUI; otro número da otra variación. Por defecto: 1."),
        'size': (
            "Side of the finished square texture, in pixels. Default: 256.",
            "Lado de la textura cuadrada final, en píxeles. Por defecto: 256."),
        'strength': (
            "How much ComfyUI repaints the picture, from 0 (keep it) to 1 (redraw it). Empty: 0.6.",
            "Cuánto repinta ComfyUI la imagen, de 0 (conservarla) a 1 (redibujarla). Vacío: 0.6."),
        'style': (
            "The building style that uses this texture; with a role too, the generator lays it in place of that style's swatch.",
            "El estilo de edificio que usa esta textura; junto con un papel, el generador la pone en lugar de la muestra de ese estilo."),
        'tile_m': (
            "How many metres of a building's surface one repeat of the texture covers when the generator uses it. Default: 2.",
            "Cuántos metros de la superficie de un edificio cubre una repetición de la textura cuando el generador la usa. Por defecto: 2."),
        'url': (
            "Address of the running ComfyUI server. Empty: http://127.0.0.1:8188.",
            "Dirección del servidor de ComfyUI en marcha. Vacío: http://127.0.0.1:8188."),
    },
    'model_sheets': {
        'attachments': (
            "Also draws what hangs on the standing model (hats, ponchos, weapons), each with its own texture. Riders and effects are not drawn.",
            "También dibuja lo que cuelga del modelo en reposo (sombreros, ponchos, armas), cada uno con su textura. No se dibujan jinetes ni efectos."),
        'cell': (
            "Width and height of each model's picture, in pixels. Default 220.",
            "Ancho y alto de la imagen de cada modelo, en píxeles. Por defecto 220."),
        'cols': (
            "How many cells per row of the sheet. Default 6.",
            "Cuántas celdas hay por fila en la hoja. Por defecto 6."),
        'elevation': (
            "The camera's height in degrees above the ground. Default 30; 60 to 70 is how the game's camera sees a unit.",
            "La altura de la cámara en grados sobre el suelo. Por defecto 30; de 60 a 70 es como ve la cámara del juego a una unidad."),
        'keep_scale': (
            "Draws every model at one scale, standing on the same line, so a house and a soldier compare fairly. Without it each model fills its cell.",
            "Dibuja todos los modelos a la misma escala, sobre la misma línea, para comparar bien una casa y un soldado. Sin esto, cada modelo llena su celda."),
        'models': (
            "A text file with one entry per line, caption | target; a target is a proto name, an anim file or a model.",
            "Un archivo de texto con una entrada por línea, título | objetivo; el objetivo es un nombre de proto, un archivo de animación o un modelo."),
        'out': (
            "The .png sheet to write; a .txt with the same name beside it says what each cell shows or why it is empty.",
            "La hoja .png que se escribe; a su lado un .txt con el mismo nombre dice qué muestra cada celda o por qué está vacía."),
        'overlay': (
            "A folder laid out like a game copy (art, data) whose loose files win over the game's, to see new textures or anim files before installing them.",
            "Una carpeta organizada como una copia del juego (art, data) cuyos archivos sueltos se usan antes que los del juego, para ver texturas o animaciones nuevas antes de instalarlas."),
        'prefer': (
            "Comma-separated branches of the anim files' logics to show first (a culture, civ or age tech). Empty: each logic shows its first branch.",
            "Ramas de las lógicas de los archivos de animación que se muestran primero, separadas por comas (una cultura, civ o tecnología de edad). Vacío: cada lógica muestra su primera rama."),
        'team': (
            "A player colour shown where player-coloured textures let it through. Empty: the texture's own colour.",
            "Un color de jugador que se ve donde las texturas con color de jugador lo dejan pasar. Vacío: el color propio de la textura."),
        'title': (
            "Text drawn across the top of the sheet and written at the head of its .txt. Empty: no title.",
            "Texto que se dibuja en la parte superior de la hoja y se escribe al inicio de su .txt. Vacío: sin título."),
        'views': (
            "Comma-separated camera angles in degrees, one cell each per entry: 0 is the front, 180 the back. Empty: -35, the three-quarter view.",
            "Ángulos de cámara en grados separados por comas, una celda por cada uno en cada entrada: 0 es el frente, 180 la espalda. Vacío: -35, la vista de tres cuartos."),
    },
    'model_sheets_survey': {
        'cell': (
            "Width and height of each model's picture, in pixels. Default 160.",
            "Ancho y alto de la imagen de cada modelo, en píxeles. Por defecto 160."),
        'cols': (
            "How many cells per row of each sheet. Default 8.",
            "Cuántas celdas hay por fila en cada hoja. Por defecto 8."),
        'groups': (
            "Comma-separated origin:category pairs, one sheet each. Empty: own:buildings,own:units,stock:nuggets,stock:objects.",
            "Pares origen:categoría separados por comas, una hoja por cada uno. Vacío: own:buildings,own:units,stock:nuggets,stock:objects."),
        'report': (
            "The model survey's JSON report; the sheets sample its models by origin and category.",
            "El informe JSON del estudio de modelos; las hojas toman modelos de muestra de él por origen y categoría."),
        'rows': (
            "How many rows each sheet has; a sheet shows at most columns times rows models. Default 6.",
            "Cuántas filas tiene cada hoja; una hoja muestra como máximo columnas por filas modelos. Por defecto 6."),
        'seed': (
            "Random seed that picks which models are sampled; the same seed gives the same sheets. Default 3.",
            "Semilla aleatoria que elige qué modelos se muestran; la misma semilla da las mismas hojas. Por defecto 3."),
        'textures': (
            "The texture survey's JSON report, so each model is drawn with its own texture when it was found. Empty: models without textures.",
            "El informe JSON del estudio de texturas, para dibujar cada modelo con su propia textura cuando se encontró. Vacío: modelos sin textura."),
    },
    'model_survey': {
        'folders': (
            "The game or mod folders whose Granny files (.gr2), loose or inside .bar archives, are opened and measured.",
            "Las carpetas del juego o del mod cuyos archivos Granny (.gr2), sueltos o dentro de archivos .bar, se abren y miden."),
        'from_report': (
            "A models.json from an earlier run, used instead of measuring again; only the summary and profile are made.",
            "Un models.json de una ejecución anterior, usado en lugar de volver a medir; solo se hacen el resumen y el perfil."),
        'limit': (
            "Measures at most this many files, picked evenly through the list, for a quick trial. Empty: all of them.",
            "Mide como máximo esta cantidad de archivos, repartidos por toda la lista, para una prueba rápida. Vacío: todos."),
        'only': (
            "Measures only one category, the game's folder name under art such as units, buildings or objects. Empty: all.",
            "Mide solo una categoría, el nombre de carpeta del juego dentro de art como units, buildings u objects. Vacío: todas."),
        'profile_out': (
            "Writes the measured profile as JSON: measurements only, naming no file of the mod.",
            "Escribe el perfil medido en JSON: solo medidas, sin nombrar ningún archivo del mod."),
        'reference': (
            "The original game's folders: each file is marked stock, changed or the mod's own. Empty: every origin is unknown.",
            "Las carpetas del juego original: cada archivo se marca como del juego, cambiado o propio del mod. Vacío: todo origen queda desconocido."),
        'textures': (
            "A texture survey's report, so each model's texture size is known and its texel density given in pixels per unit.",
            "El informe de un estudio de texturas, para conocer el tamaño de la textura de cada modelo y dar su densidad en píxeles por unidad."),
        'workers': (
            "How many files are measured at once, in parallel processes. Empty: the computer's processor count minus two.",
            "Cuántos archivos se miden a la vez, en procesos paralelos. Vacío: el número de procesadores del equipo menos dos."),
    },
    'named_models': {
        'list': (
            "A text file with one entry per line, caption | target, where the target is a proto name, an anim file or a model. Lines starting with # are skipped.",
            "Un archivo de texto con una entrada por línea, título | objetivo, donde el objetivo es un nombre de proto, un archivo de animación o un modelo. Se omiten las líneas que empiezan por #."),
        'overlay': (
            "A folder laid out like a game copy (art, data) whose loose files win over the game's, to check new art before installing it.",
            "Una carpeta organizada como una copia del juego (art, data) cuyos archivos sueltos tienen prioridad sobre los del juego, para revisar arte nuevo antes de instalarlo."),
        'prefer': (
            "Comma-separated branches of the anim files' logics to show first for every entry (a culture, a civ, an age's tech). Empty: each logic's first branch.",
            "Ramas de la lógica de los archivos de animación, separadas por comas, que se muestran primero en cada entrada (una cultura, una civ, una tecnología de edad). Vacío: la primera rama de cada lógica."),
    },
    'own_texture': {
        'model_in': (
            "The uncompressed .gr2 model to copy; a compressed model is refused.",
            "El modelo .gr2 sin comprimir que se copia; un modelo comprimido se rechaza."),
        'model_out': (
            "Where to write the copy of the model whose stored texture paths are renamed.",
            "Dónde se escribe la copia del modelo con las rutas de textura guardadas renombradas."),
    },
    'palette_survey': {
        'bars': (
            "The game's art .bar archives (Art*.bar) whose .ddt textures are measured; nothing is extracted or written.",
            "Los archivos .bar de arte del juego (Art*.bar) cuyas texturas .ddt se miden; no se extrae ni se escribe nada."),
        'filter': (
            "Measures only textures whose stored path contains this text (not case-sensitive); icons, portraits and bump maps are skipped. Default: buildings.",
            "Mide solo las texturas cuya ruta guardada contiene este texto (sin distinguir mayúsculas); se omiten iconos, retratos y mapas de relieve. Por defecto: buildings."),
        'limit': (
            "Stops after measuring this many textures. Default: 80.",
            "Se detiene tras medir esta cantidad de texturas. Por defecto: 80."),
    },
    'retexture': {
        'preview': (
            "Also writes a PNG sheet: the starting texture, the result, and the result with a player colour.",
            "Escribe además una hoja PNG: la textura de partida, el resultado y el resultado con un color del jugador."),
        'recipe': (
            "The recipe (.json): the starting texture, the UV atlas, the output .ddt and its format, and the paint steps per part. Paths are relative to the recipe.",
            "La receta (.json): la textura de partida, el atlas UV, el .ddt de salida y su formato, y los pasos de pintura por parte. Las rutas son relativas a la receta."),
        'url': (
            "Address of the local ComfyUI, used only by the recipe's ai steps; default http://127.0.0.1:8188.",
            "Dirección del ComfyUI local, usada solo por los pasos ai de la receta; por defecto http://127.0.0.1:8188."),
    },
    'shape_summary': {
        'profile': (
            "The building profile JSON whose shape table is replaced; the file is rewritten in place.",
            "El perfil de edificios en JSON cuya tabla de formas se sustituye; el archivo se reescribe en el sitio."),
        'summary': (
            "The result file a shape survey wrote (shapes.json), whose per-class quartiles go into the profile.",
            "El archivo de resultado que escribió un estudio de formas (shapes.json), cuyos cuartiles por clase van al perfil."),
    },
    'shape_survey': {
        'limit': (
            "Stops after measuring this many buildings. Empty: all of them.",
            "Se detiene tras medir esta cantidad de edificios. Vacío: todos."),
        'out': (
            "The JSON file of measurements per building (height, cover, parts, levels, triangles per third). Empty: shapes.json.",
            "El archivo JSON con las medidas de cada edificio (altura, cobertura, partes, niveles, triángulos por tercio). Vacío: shapes.json."),
        'raw': (
            "The raw folder of the art survey's cache, holding the uncompressed models it wrote with the Granny bridge.",
            "La carpeta raw de la caché del estudio del arte, con los modelos sin comprimir que escribió con el puente de Granny."),
        'report': (
            "The report.json of an art survey: the buildings with their models and obstruction sizes.",
            "El report.json de un estudio del arte: los edificios con sus modelos y tamaños de obstrucción."),
    },
    'spec_sheets': {
        'only': (
            "Space-separated preset names to write sheets for; the index is then not rewritten. Empty: every preset and the index.",
            "Nombres de presets separados por espacios para los que se escriben fichas; entonces no se reescribe el índice. Vacío: todos los presets y el índice."),
        'proto': (
            "The game's protoy.xml, so each sheet also shows the game's data (hit points, cost). Those numbers must go to an output folder outside the repository.",
            "El protoy.xml del juego, para que cada ficha muestre también los datos del juego (puntos de vida, coste). Esos números deben ir a una carpeta de salida fuera del repositorio."),
    },
    'style_check': {
        'category': (
            "The texture category of the profile to compare with, such as buildings (default), objects or units.",
            "La categoría de texturas del perfil con la que se compara, como buildings (por defecto), objects o units."),
        'materials': (
            "Paints every preset with its material swatches laid under the painting. Without it, each preset paints as it normally does.",
            "Pinta cada preset con sus muestras de material bajo la pintura. Sin esto, cada preset se pinta como lo hace normalmente."),
        'origin': (
            "Which textures of the profile to compare with: own (the mod's own, default) or stock (the original game's ones in the mod).",
            "Con qué texturas del perfil se compara: own (las propias del mod, por defecto) o stock (las del juego original dentro del mod)."),
        'size': (
            "Texture size in pixels at which each preset is painted before measuring. Default 1024.",
            "Tamaño de textura en píxeles con el que se pinta cada preset antes de medir. Por defecto 1024."),
    },
    'style_fit': {
        'presets': (
            "Space-separated presets painted for the fit. Empty: a built-in set of six African presets.",
            "Presets, separados por espacios, que se pintan para el ajuste. Vacío: un grupo interno de seis presets africanos."),
        'style': (
            "The style whose material swatches are fitted, role by role, to the grain of the mod's own building textures. Default AFRICAN.",
            "El estilo cuyas muestras de material se ajustan, papel por papel, al grano de las texturas de edificios propias del mod. Por defecto AFRICAN."),
    },
    'sweep': {
        'count': (
            "How many random buildings are built and checked for each seed. Default 200; each takes about a quarter of a second.",
            "Cuántos edificios al azar se construyen y comprueban por cada semilla. Por defecto 200; cada uno tarda un cuarto de segundo aproximadamente."),
        'seeds': (
            "Comma-separated random seeds; each runs its own set of buildings. Empty: 2026,7,99.",
            "Semillas aleatorias separadas por comas; cada una genera su propio grupo de edificios. Vacío: 2026,7,99."),
        'style': (
            "Builds only buildings of this style. Empty: all styles, taking turns.",
            "Construye solo edificios de este estilo. Vacío: todos los estilos, por turnos."),
    },
    'texture_library': {
        'folder': (
            "The texture library to list. Empty: the default library in Documents\\aoe3-blender-tools\\textures.",
            "La biblioteca de texturas que se lista. Vacío: la biblioteca por defecto en Documents\\aoe3-blender-tools\\textures."),
    },
    'texture_survey': {
        'folders': (
            "The mod's folders to measure: loose textures and .bar archives, read in memory; nothing is extracted.",
            "Las carpetas del mod a medir: texturas sueltas y archivos .bar, leídos en memoria; no se extrae nada."),
        'from_report': (
            "A textures.json this tool wrote before: skips the measuring and only writes the profile or the contact sheets from it.",
            "Un textures.json que esta herramienta escribió antes: se salta la medición y solo escribe con él el perfil o las hojas de contacto."),
        'limit': (
            "Measures only an evenly spread sample of this many textures, for a quick trial. Empty: all of them.",
            "Mide solo una muestra repartida de esta cantidad de texturas, para una prueba rápida. Vacío: todas."),
        'models': (
            "A model survey report: textures a model names are marked worn, and a diffuse texture no model names becomes loose.",
            "Un informe del estudio de modelos: las texturas que nombra un modelo se marcan como usadas, y una difusa que ningún modelo nombra pasa a ser suelta."),
        'profile_out': (
            "Writes the texture profile (.json): measurements only, naming no file of the mod.",
            "Escribe el perfil de texturas (.json): solo medidas, sin nombrar ningún archivo del mod."),
        'reference': (
            "The original game's folder: textures with the same bytes there are tagged stock, same path with other bytes changed, the rest own.",
            "La carpeta del juego original: las texturas con los mismos bytes allí se marcan stock, misma ruta con otros bytes changed, y el resto own."),
        'sheets': (
            "Folder for contact sheets: grids of sampled textures per group to look at. They show the mod's art, so keep them private.",
            "Carpeta para las hojas de contacto: cuadrículas de texturas de muestra por grupo para revisar. Muestran el arte del mod, así que mantenlas privadas."),
        'workers': (
            "How many processes measure at once. Empty: the number of CPU cores minus two, at least one.",
            "Cuántos procesos miden a la vez. Vacío: el número de núcleos del procesador menos dos, mínimo uno."),
    },
    'train_lora': {
        'accumulate': (
            "Steps whose results are added up before the LoRA is updated: batch 1 with 2 accumulation steps learns like batch 2 with less memory. Default 2.",
            "Pasos cuyos resultados se suman antes de actualizar el LoRA: lote 1 con 2 pasos de acumulación aprende como lote 2 con menos memoria. Por defecto 2."),
        'batch': (
            "Pictures trained together in each step. Default 1; a larger batch needs more memory.",
            "Imágenes que se entrenan juntas en cada paso. Por defecto 1; un lote mayor necesita más memoria."),
        'chunks': (
            "How many parts the run is cut into; each goes on from the last one's saved LoRA, so a stop loses one chunk only. Default 3.",
            "En cuántas partes se divide el entrenamiento; cada una sigue desde el LoRA guardado por la anterior, así que una parada solo pierde un tramo. Por defecto 3."),
        'comfy': (
            "The ComfyUI portable folder (the one holding ComfyUI\\). The finished LoRA goes into its models\\loras folder.",
            "La carpeta portable de ComfyUI (la que contiene ComfyUI\\). El LoRA terminado se guarda en su carpeta models\\loras."),
        'dataset': (
            "A dataset folder made by the LoRA dataset tool: .png pictures with their .txt captions, copied into ComfyUI's input folder for training.",
            "Una carpeta de dataset creada por la herramienta de dataset de LoRA: imágenes .png con sus descripciones .txt, que se copian a la carpeta input de ComfyUI para entrenar."),
        'limit': (
            "Trains on only the first N pictures of the dataset. Empty: every picture.",
            "Entrena solo con las primeras N imágenes del dataset. Vacío: todas las imágenes."),
        'lr': (
            "The learning rate passed to ComfyUI's trainer, written like 1e-4 (the default).",
            "La tasa de aprendizaje que se pasa al entrenador de ComfyUI, escrita como 1e-4 (el valor por defecto)."),
        'min_free': (
            "If the PC's free memory falls below this many GB, ComfyUI is interrupted and the run stops there. Default 2.5.",
            "Si la memoria libre del PC baja de estos GB, se interrumpe ComfyUI y el entrenamiento se detiene ahí. Por defecto 2.5."),
        'name': (
            "The LoRA's name: it is saved as models\\loras\\<name>.safetensors in ComfyUI. Default aoe3bt_own.",
            "El nombre del LoRA: se guarda como models\\loras\\<nombre>.safetensors en ComfyUI. Por defecto aoe3bt_own."),
        'offload': (
            "Keeps the model's weights in the PC's RAM instead of the graphics card: less GPU memory, more RAM.",
            "Mantiene los pesos del modelo en la RAM del PC en lugar de la tarjeta gráfica: menos memoria de GPU, más RAM."),
        'rank': (
            "The LoRA's rank, passed to ComfyUI's trainer. Default 16.",
            "El rango del LoRA, que se pasa al entrenador de ComfyUI. Por defecto 16."),
        'resume': (
            "A chunk's LoRA file in ComfyUI's models\\loras to go on training from; a stopped run prints its name. Empty: starts from scratch.",
            "El archivo LoRA de un tramo en models\\loras de ComfyUI desde el que seguir entrenando; un entrenamiento detenido muestra su nombre. Vacío: empieza de cero."),
        'seed': (
            "Random seed of the first chunk; each next chunk uses the following number. Default 1.",
            "Semilla aleatoria del primer tramo; cada tramo siguiente usa el número siguiente. Por defecto 1."),
        'steps': (
            "Total training steps for the whole run, split across the chunks. Default 1200; a trial of 20 steps and 1 chunk shows whether it fits in memory.",
            "Pasos de entrenamiento en total, repartidos entre los tramos. Por defecto 1200; una prueba con 20 pasos y 1 tramo muestra si cabe en memoria."),
        'url': (
            "The address where ComfyUI answers. Empty: http://127.0.0.1:8188.",
            "La dirección donde responde ComfyUI. Vacío: http://127.0.0.1:8188."),
    },
    'uncompress_check': {
        'copy': (
            "The game copy whose manifest of uncompressed models is read back: every copy present and unchanged, every archive entry unchanged.",
            "La copia del juego cuyo manifiesto de modelos sin comprimir se relee: cada copia presente y sin cambios, cada entrada del archivo sin cambios."),
    },
    'uncompress_models': {
        'copy': (
            "The game copy whose archived .gr2 models get loose uncompressed copies; the mod's own loose models are never touched. A Steam folder is refused.",
            "La copia del juego cuyos modelos .gr2 archivados reciben copias sueltas sin comprimir; los modelos sueltos propios del mod nunca se tocan. Una carpeta de Steam se rechaza."),
        'only_used': (
            "Writes only the models of a list (a text file of paths, or a game log of files read) and removes its own copies of the others.",
            "Escribe solo los modelos de una lista (un archivo de texto con rutas, o un registro del juego con los archivos leídos) y quita sus propias copias de los demás."),
        'work': (
            "Where temporary files are kept while the models are rewritten. Empty: the system's temporary folder.",
            "Dónde se guardan los archivos temporales mientras se reescriben los modelos. Vacío: la carpeta temporal del sistema."),
        'workers': (
            "How many models are rewritten at the same time. Empty: half the PC's processor cores.",
            "Cuántos modelos se reescriben a la vez. Vacío: la mitad de los núcleos del procesador del PC."),
    },
    'uncompress_undo': {
        'copy': (
            "The game copy to clean: removes only the uncompressed copies its manifest lists that are still unchanged, then empty folders and the manifest.",
            "La copia del juego a limpiar: quita solo las copias sin comprimir de su manifiesto que no han cambiado, luego las carpetas vacías y el manifiesto."),
    },
    'uv_atlas': {
        'by': (
            "How islands get their body part: bone uses the bone with most skin weight (default); position uses where they sit on the model.",
            "Cómo se asigna la parte del cuerpo a cada isla: bone usa el hueso con más peso de piel (por defecto); position usa dónde está en el modelo."),
        'overlay': (
            "A folder laid out like a game copy (art, data) whose loose files win over the game's, to see new art before installing it.",
            "Una carpeta organizada como una copia del juego (art, data) cuyos archivos sueltos se usan antes que los del juego, para ver arte nuevo antes de instalarlo."),
        'prefer': (
            "Comma-separated branches of the anim file's logics to show first (a culture, civ or age tech). Empty: each logic shows its first branch.",
            "Ramas de las lógicas del archivo de animación que se muestran primero, separadas por comas (una cultura, civ o tecnología de edad). Vacío: cada lógica muestra su primera rama."),
        'size': (
            "Size of the part masks as WxH pixels, e.g. 1024x1024, useful for an upscaled texture. Empty: the texture's own size.",
            "Tamaño de las máscaras de cada parte en píxeles AnchoxAlto, p. ej. 1024x1024, útil para una textura ampliada. Vacío: el tamaño de la propia textura."),
        'target': (
            "A proto name (e.g. Musketeer), an anim file or a .gr2 model, relative to the game's art folder; an anim file shows its standing model.",
            "Un nombre de proto (p. ej. Musketeer), un archivo de animación o un modelo .gr2, relativo a la carpeta art del juego; de un archivo de animación se usa el modelo en reposo."),
        'texture': (
            "Draws the atlas over this .ddt or .png instead of the model's own texture.",
            "Dibuja el atlas sobre este .ddt o .png en lugar de la textura propia del modelo."),
    },
    'xmb_add_unittype': {
        'file': (
            "The compiled proto (protoy .xmb) to read; it is not changed.",
            "El proto compilado (protoy .xmb) que se lee; no se modifica."),
        'out': (
            "Where the edited proto is written, with the same compression as the input.",
            "Dónde se escribe el proto editado, con la misma compresión que el original."),
    },
    'xmb_check': {
        'file': (
            "The .xmb to decode and re-encode, directly and through its XML text, confirming both come back byte for byte. Nothing is written.",
            "El .xmb a decodificar y recodificar, directamente y pasando por su texto XML, confirmando que ambos vuelven idénticos byte a byte. No se escribe nada."),
    },
    'xmb_to_xml': {
        'file': (
            "The compiled .xmb file to read, for example one extracted from a .bar archive.",
            "El archivo .xmb compilado que se lee, por ejemplo uno extraído de un archivo .bar."),
        'out': (
            "Where to write the readable XML copy; element names stay as stored (lowercase).",
            "Dónde se escribe la copia XML legible; los nombres de elementos quedan como están guardados (en minúsculas)."),
    },
    'xml_to_xmb': {
        'compress': (
            "Writes the zlib-compressed \"l33t\" form, like the stock protoy.xml.XMB; without it, plain form like stock .tactics files. Both load.",
            "Escribe la forma comprimida con zlib \"l33t\", como el protoy.xml.XMB del juego; sin esto, la forma simple como los .tactics del juego. Ambas cargan."),
        'file': (
            "The XML file to compile, such as an edited protoy.xml, a .tactics or an .impacteffect file.",
            "El archivo XML que se compila, como un protoy.xml editado, un archivo .tactics o un .impacteffect."),
        'out': (
            "The compiled .xmb file to write; the game reads it in place of the XML.",
            "El archivo .xmb compilado que se escribe; el juego lo lee en lugar del XML."),
    },
}
