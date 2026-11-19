# Game formats

What `aoe3_blender_tools/aoe3game/` reads and writes, and how each fact was established. Facts
are marked **measured** (on the game's and a mod's files, or by the Granny runtime the game
loads), **in game** (seen in the game), or **to verify**.

## Models (.gr2)

Granny 2, file versions 6 and 7 (**measured**: both ship; the runtime is 2.5.0.10).

| Offset | Content |
|---|---|
| 0x00 | magic, 16 bytes `b867b0caf86db10f84728c7e5e19001e` |
| 0x10 | u32 end of the section array |
| 0x14 | u32 header format (0), 8 bytes reserved |
| 0x20 | file header: version, total size, CRC, section array offset (relative to 0x20), section count, root type (section, offset), root object (section, offset), type tag, 4 extra tags; version 7 adds 4 words (header 0x38 or 0x48 bytes) |
| then | 44-byte section records: compression (0 none, 1 Oodle0, 2 Oodle1), data offset, data size, expanded size, alignment, first 16-bit stop, first 8-bit stop, relocation offset and count, marshalling offset and count |

- The CRC is zlib's CRC-32 of every byte from 0x20 + header size to the end (**measured**).
- Pointers are 32-bit and exist only as relocations: (offset in the section, target section,
  target offset), 12 bytes each. A slot without one is null.
- The data tree describes its own types: 32-byte member records (kind, name, referenced type,
  array width, 3 extra words, 1 ignored word) ended by kind 0. Kinds: 1 inline, 2 reference,
  3 reference to array, 4 array of references, 5 variant reference, 7 reference to variant
  array, 8 string, 9 transform (68 bytes), 10 real32, 11 to 20 integers.
- Almost every model stores Oodle1-compressed sections. The reader refuses them; the survey
  reads them after an external tool that loads the game's own Granny runtime has rewritten them
  uncompressed (that runtime is never shipped or called by this repository).

**The reader is proven**: its tree dump is identical, line for line, to the dump the Granny
runtime makes of the same file, on 31 models (14 stock, 17 from a mod; versions 6 and 7).

**The writer** (`gr2_write.static_model`) produces a version 6 file with one uncompressed
section, laid out like the game's own single-section building models: header, relocations,
then 32-bit data, 16-bit arrays and 8-bit data (strings), whose starts are the first16 and
first8 fields. Checks passed (**measured**):

1. the Granny runtime reads it, its own CRC check says valid, and its tree dump equals ours;
2. every path of its tree exists in the game's and the mod's models;
3. the runtime's rebuild of it reports it identical;
4. **in game**: the scenario editor loads and draws it, and in a skirmish it stands in the world
   at the right size, lit like the stock objects, textured the right way up, with the
   civilization flag on its `bone_flag_civ` bone; the player colour, the construction stages and
   the rubble work too (see game-test.md).

What a static building model holds (as the stock files):

- `ArtToolInfo`: the stock buildings' basis, "ESPostExport": 0.615157485 units per metre,
  right (-1, 0, 0), up (0, 1, 0), back (0, 0, 1). A Blender point (x, y, z) in metres is stored
  as (-x, z, -y) x 0.615157485.
- One vertex array of 32 bytes: Position f3, Normal f3, TextureCoordinates0 f2 (886 of the
  measured building models; 1,398 add a Tangent, 44 bytes).
- Indices16 when the mesh has at most 65,535 vertices, else Indices (32-bit; 124 of 621
  measured building models use them).
- Triangles counter-clockwise around their normal in the stored coordinates (754 of 754 on a
  stock house); the writer orders each triangle that way.
- Texture coordinates: V counts from the top row of the texture (**measured**: on a stock house,
  102 roof corners land on the roof drawing as stored, 0 if V were flipped). Blender's V counts
  from the bottom, so the writer stores 1 - V.
- Skeleton "bone_main" with the mesh's bone and one bone per attach point (`bone_flag_civ` for
  the flag, `bone_chimney` for smoke), children of the root.
- Materials as the mod's shortest working ones: a diffuse map, a bump map (the stock flat normal
  texture), and the shader `bumpspec_mask_alphatest` with `lighting\specpower16`, or
  `bumpspec_mask_pixelxform` with `pixelxformColor = playerColor` for player colour.
- Texture names: the model stores a full path; the engine uses the part after `\art\`.

**Scale** (**measured**, confirmed in game 2026-11-04): the survey measured 657 building models. 507
in the stock basis and 70 in 3ds Max inches have a size that agrees with their obstruction once
their declared units are applied. The 27 that declare 1,000 units per metre would be about 0.5 m
wide by that rule, and they are not: in game they stand at full size, their stored coordinates
scaled as if they were inches (x 0.015625: 1,280 stored units are 20 game units). A survey must not
trust that declaration. The writer uses the stock basis, so no conversion is involved.

**Bone scale** (**measured**): a bone's world frame is its parent's world frame times its local
transform, local = translate(Position) x rotate(Orientation, a quaternion x y z w) x ScaleShear (a
3 x 3, used only when bit 4 of the transform's flags is set; bit 1 position, bit 2 orientation). The
stored InverseWorldTransform is the inverse of that frame in row-vector form (translation in the
last row): their product is the identity to 1e-6 on stock and mod buildings. **Units too**
(**measured** 2026-11-19, correcting an earlier note that said otherwise, which had not followed
the parents' rotations): with the rotations followed, a skinned unit's rest pose is its bind pose
to 1e-3 in 313 of 323 skinned models drawn at random from a Wars of Liberty copy (96.9 %; 125 of
129 in a second draw). `aoe3game/gr2_skin.py` composes the frames and says per skeleton whether it
holds (`matches`); a vertex has up to four bones (`BoneIndices`, `BoneWeights` as bytes adding up
to 255; the packed stream two), and the game's animations find their bones by name. Skinning a
unit at its rest pose (world x inverse bind, weighted) gives its stored vertices back (2e-7 on the
Musketeer).

- Stock buildings: the impact bones (`boneimpactNN`) and attach bones have world axes of length 1;
  some helper bones are 0.918, and across all stock models helper bones from 0.24 to 4 are common.
- Some mods export in centimetres: the root `bone_main` carries ScaleShear 100 (flags 7) and every
  other bone a unit local scale, so every bone's world axes are 100 long. Meshes bound to these
  bones draw right (their inverse takes the 100 out again).
- The game hangs an impact effect whose particle set names an `.xml` visual (the stock
  `cannon.impacteffect`'s `<wood>`) on the impact point's bone with the bone's whole world frame,
  scale included; a plain particle set name is placed at the hit point and does not read the bone.
  On a bone of axes 100 the visual is drawn 100 times too big (**in game**).
- `tools/fix_bone_scale.py` gives such bones a local ScaleShear of 1/100 (flag bit 4 set), so their
  world axes are 1 while their world position and direction stay, and scales their inverse to
  match; mesh-bound bones are never changed. The Granny runtime reads a file patched this way and
  its CRC check passes (**measured**). **In game** (2026-11-13): a mod building of this kind, its
  damage template set to `wood`, threw the visual across the whole view when hit by cannon; with its
  models fixed by the tool the splinters, smoke and fire stay on its walls, and it stands, burns and
  collapses as before. The construction and collapse models had no bone to change.
- Measured on a large mod: 341 of 18,501 Granny files have such bones (2,558 bones: 2,307 at 100,
  140 at 60, the rest between 0.026 and 41); 74 more have one the tool must leave (a scaled root
  over its debris meshes, or a bone scaled unevenly). In the stock archives only 4 of about 12,300
  models have one (wheel links at 0.1 on a mortar, a bone at 0.012 on the low-poly war dogs), none
  of them an impact or flag bone: run the tool on a mod's own folders.

### Packed vertices

More than half of the unit models (and some props) store a mesh's vertices in a packed stream of
the game's own instead of Granny's typed vertices: the vertex array's type has a single one-byte
member named `FD`, so Granny sees a byte array. **Measured** on 3,857 such arrays (every one in a
survey cache of a mod copy with the base game's archives): all follow this layout, the triangle
indices of their meshes stay below the vertex count, and their triangles are as compact as those
of plain meshes. `gr2_mesh.packed` reads it.

| Offset | Content |
|---|---|
| 0x00 | 16 words: magic `0xFDABCD01`; size of the stream after its first 12 bytes; a value that changes from file to file (a hash?); vertex count N; rigid group count G; group table size in bytes (8 G, or 8 G + 8 in 1,791 of the 3,857); rigid block count B; rigid bytes (112 B); skinned vertex count S; skinned bytes (32 S); rigid vertex count R = 4 B; a bone count; then zeros to 0x40 |
| 0x40 | the group table: per group u16 block count, u16 first vertex, u32 bone (an index into the mesh's bone bindings: **measured**, below). The groups cover the R rigid vertices in order |
| then | B blocks of four rigid vertices, 112 bytes each: x[4], y[4], z[4] (float32), four 4-byte words (normals, **to verify**), four 4-byte words (tangents, **to verify**), then u, v (float32) of each vertex |
| then | S skinned vertices, 32 bytes each: x, y, z (float32); 4 bytes, two weights then two bone indices (u8; the weights add up to 255: **measured**, below); a 4-byte normal and a 4-byte tangent (**to verify**); u, v (float32) |

- N = R + S: the rigid vertices come first, the skinned ones after, and the triangles index the
  whole range, the padding of a group's last block included (it is not used).
- The positions are in model space, like a plain `Position` (**measured**: a point on a seam
  between a rigid and a skinned part has the same coordinates in both sections, and the
  triangles join them without moving them to a bone). The UVs follow Granny's usual convention.
- The reader takes the positions, the UVs and the skin (the normals are left to Blender):
  `gr2_mesh.packed_skin` gives each vertex two bone indices and their weights. **Measured** on a
  rider of WoL (39 bones): each rigid group's bone index names, in the mesh's bone bindings, the bone
  whose height matches its vertices (pelvis at the hips, calves at the shins, the head on top), so
  the group table's bone **is** an index into the bindings; the skinned vertices' two weights add up
  to 255 and their indices name neighbouring bones (thigh and calf, upper arm and forearm).
- Plain meshes give the same from their `BoneIndices` and `BoneWeights` (the two heaviest).

### Attachments at rest

A hat, a poncho or a weapon is a model of its own that the anim file hangs on a bone of the unit
(`<attach a="hat" frombone="bone_hat" tobone="HEAD"/>`). `gr2_mesh.attach` places one as the game
shows it standing; what it does was checked against the game (2026-11-14, three hats and a
lance on four WoL units, seen in game in a test copy):

- each bone's rest matrix is the inverse of its `InverseWorldTransform`;
- both files are first brought to one space by their own `ArtToolInfo` (axes and units per metre):
  hats written in inches with Z up sit on units written in game units with Y up;
- `tobone` is matched as the game's names are written: `HEAD` is `Bip01 Head`, `SPINE1` is
  `Bip01 Spine1` (any case, last words);
- most accessories have a single bone and no `frombone` (`bone_hat` is not in them): that bone
  is laid on the body's, **without its scale** (a hat whose only bone is scaled by 0.095 shows at
  its own size in game: inferred from where WoL's marine hats sit, not measured in the engine);
- **to verify:** a file whose units per metre disagree with its numbers (one hat says 1000 with
  numbers like the inch-written ones) would come out a hundredth of its size; how the engine
  treats it is not known, so such accessories were avoided.

### A model's own texture path

A unit copy usually shows its new texture through `<replacetexture>` in its anim file. **Observed**
(WoL's Laguna, 2026-11-14): a copy of a WoL rider kept the original's texture in that scenario,
while the same copy showed its new texture on a test map and in another mission; the cause is not
known (a guess: the original texture already bound in that scenario). What works there: a copy of
the model (uncompressed) whose stored texture paths (`Textures[].FromFileName`) name the new
texture, at the same length so nothing else in the file moves, with the CRC recomputed
(`retexture.py --own-texture`). The game resolves the stored path below `art\` (the artist's
drive and folders before it are ignored).

### Moving a home city's models (`tools/hc_move.py`)

**In game** (2026-11-17, a mod's home city of 32 models and the one that shares four of them,
before and after, from the same six views; the screenshots differ by 0.1 to 0.6 levels out of 255
on average where the move works, by 50 to 190 where it does not):

- **A stored texture name drops only its last extension.** `...\art\x\name.jpg`,
  `...\art\x\name.tga` and `...\art\x\name.ddt` all reach `art\x\name.ddt`, and a model whose stored
  names follow its moved textures draws as before. A name written `name.(0,4,8,8).tga` (the
  `(usage,alpha,format,mips)` suffix of a source texture's file name) makes the game look for
  `name.(0,4,8,8).ddt`: the models drew black until copies of their textures with that name were
  added. So a suffix in a model's stored name needs the `.ddt` renamed with it.
- **A home city's `<visual>` may climb out of `art\homecity\`** with `..\` (a path relative to
  `art\homecity\` such as `..\Mod\homecity\Name\x.xml` loads), and a path under `art\homecity\`
  works as well.
- **A suffix in the name and on the file works.** With the `.ddt` renamed `name.(0,4,8,8).ddt`
  (its own header's digits, the file unchanged) and the stored name `name.(0,4,8,8).tga`, the models
  draw as before (2026-11-17, every home city of a mod: 22 home cities, 161 models, 240 textures).
- **Of a loose plain anim file and its loose compiled twin, the newer one is read.** A home city
  whose plain `x.xml` (2019) named one model and whose `x.xml.xmb` (2015) another drew the plain
  file's model; once both were copied to a new folder, the twin was a few milliseconds newer and
  the game drew the twin's model. A move must carry only the twin the game reads.
- **A raw 3ds Max export converted to the stock basis** (`rebake --convert`: inches to 0.615 units
  per metre, Z up to Y up, every value checked to the units ratio offline) **does not draw as the
  original in a home city.** **In game:** with the converted files still named `3D Studio MAX` in
  `ArtToolInfo.FromArtToolName`, the buildings and background stood misplaced and out of scale and
  the camera saw the wrong scene; renamed `ESPostExport` (nothing else changed), the camera and the
  layout came back, but the converted buildings and background were drawn as stretched, broken
  polygons and the sky was missing. The converted vertex positions are the originals through
  (x, y, z) -> (-x, z, -y) / 64 exactly, and the bones' rotations and scales are conjugated as
  expected. So the game picks how it reads a file by its art tool's name (it ignores the declared
  units: a file declaring 1,000 per metre is drawn as if in inches), and something else in a
  converted file (the bones' inverse world transforms or the meshes' bindings: **to verify**) is
  not read the way the conversion writes it. Until that is known, keep raw exports as they are:
  the game draws them right.
- Rebuilt models compressed again with `recompress_models.py` (each section in the original's
  format where the rebuild kept the sections' sizes, else Oodle1) drew as before, at the
  originals' total size, **except** models of type tag `0x80000010`: their recompressed copies
  pass the CRC check but the Granny runtime cannot open them (an access violation in
  `GrannyGetFileInfo`), and the game exits (code 0) as soon as it meets one. `hc_move.py` opens
  every recompressed model through the runtime and ships it uncompressed when it fails.

### Uncompressed copies

- **Why** (**measured** by sampling the stack of the game's main thread): the
  game reads a model or an animation the first time it meets one, on its main thread, and most of
  that time is the Oodle1 decoder of the compressed sections. A section stored uncompressed is read
  straight into its buffer; fixups and the byte order are separate steps, the same for any format,
  so an uncompressed file skips only the decoder.
- **Loose files override the archives** (**measured**): a `.gr2` under `art\` with the stored name
  of an archived one is the one the game opens, and the game reads it like any other.
- **The stock archives** (`Art1.bar`, `Art4.bar`, `Art5.bar`): 12,319 `.gr2` names (13,086 entries, 551 MB); 105
  names are stored in two archives with different bytes (which one the game reads is not
  measured, so the tool leaves them out), 1,776 have no compressed section, and 10,438 have one. In
  a copy of Wars of Liberty 17 of those are the mod's own loose models; the other 10,421 are 397 MB
  as stored and 1,041 MB uncompressed (2.6 times).
- **The root type reference.** The runtime's own `GrannyRecompressFile` keeps the sections, their
  bytes and their fixups, but writes the root object's type reference (header words 5 and 6, at
  0x34) as 0:0. A model whose type tag is older than the runtime's is then read with the wrong
  type, and the game exits at its main menu (exit code 0, no message). Copying the two words back
  from the original and recomputing the CRC fixes it. The bridge's `rebake --noop` rebuilds the
  file as bytes and keeps them (0 of 10,421 needed the fix), and the tool checks them anyway.
- **What `tools/uncompress_models.py` checks** before it writes a copy: the bridge reads the
  original and the copy back through the runtime and refuses any difference in their data trees,
  and the runtime says the copy's CRC is valid; then the tool compares the containers itself: the
  same header but for the total size and the CRC, every section uncompressed and stored at its
  expanded size, the same section records (expanded size, alignment, stops, fixup counts), the
  relocation and marshalling tables byte for byte, the sections the original stored uncompressed
  byte for byte, and the CRC. After writing it reads the file back (SHA-256).
- **Cost** (**measured**, 16 logical cores, the bridge run in 8 processes at a time): 10,421 models in 252 s
  (about 41 per second), 1,041 MB written. `--check` of the whole set: 4 s with the files cached.
- **In game** (**measured**, a saved late game replayed for 150 s, runs with and without the copies
  in turns): stock game, frames over 50 ms 2 → 0, longest frame 92–98 → 42 ms, load 1.1–1.9 s
  shorter; Wars of Liberty (its own cfg, three pairs), load 11.6 → 9.5 s in every pair, and the one
  frame per run that loaded a new model (72–80 ms) gone; the mod's other slow frames are not model
  loads and stay. FPS does not change. With the copies installed, 14 of 14 new game
  processes loaded that save, played and closed cleanly (a cache that served the same bytes from
  a DLL at runtime had hung the load in 11 of 22). `--only-used` with one session's file list kept
  1,263 copies, 177 MB.
- **The manifest** `uncompressed-models.jsonl` at the root of the copy is append-only while the
  tool runs (a folder is recorded before it is created, a file before it is renamed into place
  from `<name>.uncompressing`), so an interrupted run leaves nothing `--undo` cannot find; it is
  rewritten compactly at the end. A copy whose content changed since it was written is no longer
  the tool's: it is left in place and forgotten.
- Tests: `python -I tests/test_uncompress_models.py` (synthetic archives and models, a fake bridge).

### Recompressed copies

`tools/recompress_models.py` goes the other way, for a model a tool wrote uncompressed (a bone fix, a
texture path) that should ship at the size of the original.

- **The call** (**measured**): `GrannyRecompressFile(src, dst, n, map)` of the game's `granny2.dll`
  stores every section whose stored format is k (0 none, 1 Oodle0, 2 Oodle1) in format `map[k]`; it
  keeps the sections' order, records (expanded size, alignment, Oodle stops) and fixup tables. With
  the map "everything to 2" an uncompressed file comes out Oodle1; with the identity map a stock
  compressed model keeps its size. It writes the file packed (per section: pointer fixups,
  marshalling fixups, data, no padding; the bridge's rebuild pads an uncompressed section's data to
  its alignment, and both read the same) and the root type reference as 0:0, which the tool puts
  back (see above).
- **Its temporary file** (**measured**): two calls at once with the same `%TEMP%` fail (it returns
  false); the tool gives each call its own `TEMP` and folder.
- **32 bits**: the DLL is x86, so `tools/granny_recompress.c`, a small x86 program, hosts it
  (`recompress` and `crc`, `GrannyFileCRCIsValid`). `--build-helper` compiles it with Visual Studio's
  x86 compiler (found by `vswhere`) or `zig cc -target x86-windows-gnu`.
- **Which format**: with `--like <original>` each section gets the original's; else Oodle1, except a
  section whose compressed bytes would not be fewer than its expanded size (the stock exports keep
  such a section uncompressed: a section of 17,880 bytes of vertex data came out of Oodle1 at
  18,065).
- **Checks** before a file is written: the header is the input's but for the total size and the
  CRC; every section has its target format, its record and its fixups; an uncompressed section its
  bytes; the CRC is valid by the bytes and by the runtime; and the runtime expands the result back to
  exactly the bytes it expands the input to.
- **On 107 building models of Wars of Liberty** whose bones `fix_bone_scale.py` fixed (**measured**,
  2026-11-17): 16,543,100 bytes uncompressed → 6,963,269 bytes, against 6,959,543 for the mod's
  originals (+0.05 %); the formats chosen without `--like` were the originals' in all 107 (one model
  keeps one of its eight sections uncompressed, as the original does). The Oodle1 bytes are not the
  originals' (0 of 107 identical) but expand to the same data. 2.7 s with 8 calls at a time. Each
  result expanded again by the bridge (`rebake --noop`, as `uncompress_models.py` does) was the fixed
  uncompressed file byte for byte (107 of 107), and the runtime found every CRC valid.
- **In game** (**measured**, a copy of Wars of Liberty, 42 of them as loose files: the Persian
  Mahalla, Temple, Royal Court, Madrasah and Forge): the game opened 23 of them in a skirmish
  (each read at its recompressed size, by the file log of the engine-extension DLL), drew the
  buildings standing and, damaged by trigger to 60 % of their hit points, their damage models, with the Royal Court's
  flag and the Forge's smoke and flag where the uncompressed set puts them.
- Tests: `python -I tests/test_recompress_models.py` (synthetic models, a fake runtime with zlib in
  place of Oodle).

### A whole model written again (`aoe3game/gr2_edit.py`)

The start of a unit transplant: a model's whole tree (skeleton, materials, meshes, everything)
copied into the writer's terms with every type as the file declares it, then written again.
**Measured** (2026-11-19) on the 16,294 uncompressed models of a Wars of Liberty copy's cache
(15,030 of version 6, 1,264 of version 7): every one written again has a valid CRC and the same
`gr2.dump_tree` as the original. Two things it needed: an object reached from two places stays
one object; and some `ExtendedData` types name two members alike (a material's
`ESEffectName`), so the writer takes a value by member index where a name repeats (24 files
failed or differed before).

**The game's runtime as the judge** (`tools/gr2_check.py`, the helper's `info` verb): the game's
granny2.dll (2.5.0.10) loads a model as the game does (`GrannyReadEntireFile`,
`GrannyGetFileInfo`) and lists its meshes (vertices, indices, triangles, bone bindings) and
skeletons (bones, parents); the helper finds each member by name in the runtime's own type
tables, so nothing about the structures' layout is assumed (each export such as
`GrannyFileInfoType` holds a pointer to its table; `GrannyGetTotalTypeSize` measures the table,
32 bytes a record, not an object). **Measured** on 400 models of the cache: what the runtime reads
equals what `gr2.load` reads in all 400, and each one written again reads alike in the runtime with
a valid CRC. Whether the game draws and animates a written unit as the original is **to verify**
in game (test T0 in `docs/game-test.md`).

## Textures (.ddt)

| Offset | Content |
|---|---|
| 0 | `RTS3` |
| 4 | u8 usage: 1 alpha test, 2 low detail, 4 bump (6 = bump normal map) |
| 5 | u8 alpha: 0 none, 1 player colour, 4 transparent, 8 blend |
| 6 | u8 format: 1 BGRA, 4 DXT1, 7 grey, 8 DXT3, 9 DXT5 |
| 7 | u8 mip levels |
| 8 | u32 width, u32 height |
| 16 | (u32 offset, u32 size) per level, largest first; then the data |

The code meanings come from community documentation; the sizes and headers of 22,264 textures
agree with them (**measured**). Uncompressed BGRA with one level is common (1,125 textures of
512 x 512 in the mod). Rows are stored top first. Alpha: with the `alphatest` shaders a low
alpha cuts a hole (cresting, arches); with `pixelxform` it shows the player colour; textures
keep 255 where they show (88 to 100 % of the surface of the measured player-colour textures).
The writer makes DXT3 by default (the game's usual building format, a quarter of the size of
BGRA), DXT1 without alpha, or BGRA, each with mip levels down to 4 x 4. Its DXT encoder fits the
inset bounding box of each 4 x 4 block and picks the nearest of the four palette colours; on a
mod's 1024 x 1024 texture the decoded result differs from the source by 1.7 levels out of 255 on
average, and the file has the size of the game's own (**measured**).

**The closer encoder** (`refine=True` on `compress`, `compress_dxt5`, `write_dxt`, `encode_level`;
the default stays the fast one, so existing output does not change): it also starts from the ends
of each block's principal colour axis, solves the endpoints by least squares for the chosen
indices (twice), tries one 565 step either way on each channel of each endpoint, and keeps per
block whichever is closest. On a decoded DXT texture it finds the original blocks again: on a
mod's 1024 x 1024 textures, 1.9 and 0.75 levels of difference with the fast encoder against 0.00
(**measured**, about 5 s a 1024 x 1024 level). Other helpers: `chain_length(w, h, smallest)`,
`mip_chain(..., bump=True)` (each level's normals made unit length again; `write_normal_map` with
`mips=True` uses it), `area_resize`/`halve` (area average, the 2 x 2 box at exactly half),
`colour_blocks_as_dxt1` (DXT3/DXT5 colour blocks as DXT1 blocks that decode the same: endpoints
in the wrong order swapped with their indices, a one-colour block given index 0, as DXT1 reads
c0 == c1 as the 3-colour mode whose index 3 is transparent black), `level_blocks`,
`alpha_blocks`, `pack`. `fitted()` halves until the **longer** side fits (it looked at the height
only, so a 2:1 texture was never reduced).

**The game's own home-city building textures** (**measured**, `tools/reencode_textures.py tad`:
the home-city files in `Data*.bar`, each `<building><visual>`, its anim files and models, the
`.ddt` each model stores, people standing in for buildings left out): 215 textures of 98 models,
mean 454 x 395; 152 are 512 x 512, 53 are 512 x 256, 43 are 256 x 256, none is above 512. Colour
textures are DXT3 (`0,1,8,x` and `0,4,8,x`) or DXT1 with alpha 0 (`0,0,4,x`; no DXT1 declares an
alpha); bump maps are DXT5 (`6,0,9,x`, `6,4,9,x`). Their chains stop at 4 px on the short side
(512 x 512: 8 levels) or at 8 (7 levels); 32 bump maps have one level.

### Re-encoding (`tools/reencode_textures.py`)

Rules (the header's alpha value is always kept): a bump map (usage bit 4) becomes DXT5; alpha 0
becomes DXT1, or DXT3 when its alpha channel is not opaque everywhere (an `alphatest` shader may
cut holes with it); alpha 1, 4 or 8 becomes DXT3; BGRA follows the same rule; grey is kept. A side
above twice the game's mean (above) halves both sides until both fit; the chain goes down to 4 px
on the short side (a longer existing chain is kept). A level whose size does not change keeps its
blocks when they can be carried over (DXT3/DXT5 to DXT1 exactly; a DXT3/DXT5 alpha re-quantised
from its decoded values); a halved texture's level is either the original's own level of that
size or a new encoding of the area average, whichever is closer. The check compares the new top
level with the original's (area averaged when halved): the mean absolute difference per channel
must stay at or below 6 and the worst 4 x 4 block's mean at or below 32 (0-255); a sound DXT1
encoding of a detailed texture (roof tiles, thatch, stone) **measured** 2 to 6 and up to 21.
`hc_move.py --reencoded` ships the re-encoded copy of every moved texture and writes the new header
into its suffix.

**Textures re-encoded under their own name** (**in game**, 2026-11-17, a mod's 22 home cities opened
one after the other in one session): ten building textures that stay in their folders (eight of a
statue, among them two uncompressed one-level textures of 133 x 108 and 166 x 357, and two shared
roof textures) were re-encoded in place. Home cities opened later in the same session then lost
their `<replacetexture>` swaps, in scenes that never draw those textures: a room lost its wallpaper
and floor, a market its roof tiles and its grass, a background its sky. Opened first in a fresh
session, the same cities drew right; each group alone passed a short sequence; with the ten put
back, all 22 drew as before in one session, with the textures that move under a new name
re-encoded. The cause is **to verify** (a size or format the game keeps per name, the sides that
are not powers of two, or the session's texture memory). Until then: `hc_move.py --reencoded`
ships re-encoded only the textures that move, and `reencode_textures.py` keeps any texture whose
sides are not powers of two (the stock game has none: all 215 measured are).

**Player colour** (**measured** on the stock textures that use the `pixelxform` shader): about 2 %
of their pixels, in thin bands (trim strips under the windows), have alpha below 128, and those
pixels are light and nearly grey (the shader tints them). The generator's player-colour option
does the same: the string courses between storeys and the shutters are painted light grey and
get alpha 0 (about 1 % of the White House's texture). The bundle then switches the model to the
`pixelxform` shader by itself, whenever the texture's alpha drops below 255.

## Variants

Beside the main model the export writes, as the stock buildings have them:

- `<name>_lp.gr2` and its own texture `<name>_lp.ddt`: the generator's LOW detail (about 350
  triangles for the White House against 1,235), under the `lowpoly` branch of a `LowPoly` logic;
- `<name>_damaged.gr2`: the same mesh with a damaged texture (soot above some windows, slates
  missing, cracks; the alpha mask kept), under `p1` of a `Destruction` logic, the intact model
  under `p99`.

## Icons and portraits

The stock house has a 64 x 64 icon and a 128 x 128 portrait, both DXT1: the building in three
quarters view on a dark, warm background inside a bevelled frame. The export renders the
building the same way (Blender's Workbench, textured, transparent background, composed onto that
background and frame) and writes both as DXT1; the files have the stock ones' sizes (2,072 and
10,984 bytes).

## Anim files

The XML a proto names in `<AnimFile>`, relative to the art folder. The base game ships them
compiled (`.xml.xmb`, plain `X1`, inside the art archives); mods ship plain XML.

- Paths: backslashes, any case, relative to `art\`; models and textures **without** extension;
  particle, XML and damage template files with theirs.
- A building (the stock houses and the mod's buildings): `definebone` for the bones used;
  submodels for construction stages 1 to 3 that reuse the stock models
  `buildings\constructions\<NxN>_stage<k>` (N from 2 to 6) with the stock construction decal;
  a submodel for the finished building (its model, a ground decal sized in game units, its
  `Idle` anim, optionally `Death` and a `Destruction` logic for damage); and a root component
  with `logic type="Variation"` > `logic type="BuildingCompletion"` choosing the submodel by
  build progress (`p0`, `p33`, `p66`, `p100`).
- Logic types measured in the mod: LowPoly, Tech, BuildingCompletion, Destruction, Variation,
  Civ, Culture.
- **The model a unit shows standing** (`animxml.idle_model`, used by `tools/named_models.py`):
  the components the top-level `Idle` anim names (or, without one, the components in order),
  then in each logic the full-detail branch of LowPoly, the highest `pN` of Destruction and
  BuildingCompletion (intact, finished), and the first branch of the others (the first age of
  Tech, the first Variation, Civ or Culture), following `submodelref` into submodels.
  Attachments (weapons, riders, effects) are separate models placed on bones by the anims.
  A branch can be asked for by name (a culture, a civ, `colonialize`...). When the model a
  branch names is missing, the next finished, intact, full-detail model of the other branches
  is taken (measured in Wars of Liberty: an artillery depot's Iroquois age-1 model names a
  folder that is not there).
- `<replacetexture><from>` / `<to>` inside a model's `assetreference` (art paths, no extension):
  the model drawn with another texture in place of one it names; mods reskin stock models this
  way.
- A **prop** (measured on `nuggets\bear_campsite`, `objects\el_dorado`, `nuggets\abandoned_cabin`):
  no construction stages, no submodel, no BuildingCompletion; one component with the model and
  a decal (a ground texture or the selection square), one `Idle` anim; a death model and a `Death`
  anim with the collapse smoke when it can be destroyed. `animxml.prop` writes it.
- A **prop set** (measured on `buildings\props_colony\props_colony.xml` and 525 anim files with a
  Variation): one component holding `logic type="Variation"` with a `<data>` per model, and an
  `Idle` anim with an empty `<assetreference type="GrannyAnim"/>`. A set holds 5 / 9 / 20 models.
  `animxml.prop_set` writes it; `bundle.write_set` writes the models (`<name>_<n>.gr2`) on one
  texture.

## Groupings

What a map script or the scenario editor places as one: a settlement, a camp, a ruin.
`RM*/groupings/<name>.xml` of the game folder; read and written by `aoe3game/grouping.py`.
Measured on 2026-11-10 over every grouping of the original game (577 files) and of a mod's copy
(1,483): all are well-formed XML, and both read and write back to the same units, flags and tiles.

```xml
<grouping>
	<width>19</width>
	<height>12</height>
	<ignoreplacementrules>1</ignoreplacementrules>
	<selectassingleunit>0</selectassingleunit>
	<units>
		<unit variation ="109" posx ="7.7374" posz ="-7.9860" orientx ="0.7071" orienty ="0.0000" orientz ="-0.7071">PropsColony</unit>
	</units>
	<tiles>
		<tileGroup type ="NonPassableLand" subtype ="terrain\texas\river1_tex">
			<block startX ="-6" startZ ="0" endX ="-6" endZ ="0"></block>
		</tileGroup>
	</tiles>
</grouping>
```

| | | |
|---|---|---|
| Spelling | **measured** | lower case (`posx`, `variation`, `ignoreplacementrules`) in 68,571 units of 1,339 files; camel case (`posX`, `Variation`, `ignorePlacementRules`) in 4,228 of 140. Both are read; lower case is written |
| `posx`, `posz` | **measured** | game units from the grouping's centre |
| `orientx/y/z` | **measured** | a direction on the ground: `orienty` is 0 in 99.9 % of the units |
| `variation` | **measured** | 0 to 255: picks a model of a prop set |
| `tiles` | **measured** | terrain and passability under the grouping (`tileGroup` of `block`s, and `heights`): read and written back unchanged, never generated. 4 files have none |
| Which way `posx`/`posz` run against Blender's axes, which way an orientation turns | **to verify** | `grouping.axes_grouping` writes an asymmetric test: units along +x, each turned a quarter more, one alone at +z |
| A `variation` above a set's model count | **to verify** | |
| Which `RM*` folders the mod's map scripts read | **to verify** | `tools/game_deploy.py --grouping` copies into every one of the test copy |

## Animation tags (.gr2.precomp)

Next to a Granny animation `x.gr2` the game keeps `x.gr2.precomp`: the positions of a few named
bones of the model, sampled over the animation. These are the animation's **tags**. The anim
file does not hold them: its `<tag type="Attack">` and the like are timed events, a separate
thing. Reader and writer: `aoe3game/precomp.py` (layout in its docstring).

- **Measured:** the base game's archives hold 6,211 `.gr2.precomp` files; every one parses and
  re-encodes byte for byte. The names seen are bones such as `MASTER`, `HEAD`, `NECK`, `PELVIS`,
  `ATTACHPOINT` and `HITPOINTBAR`; 2,278 files have `HITPOINTBAR`. A track holds one position
  (3 floats, model space) and one rotation per key, with the keys spread evenly over the
  animation. 6,175 files hold one block of tags, sampled on one model whose path ends the file;
  36 hold up to 10.
- **Engine:** the game's reader of the "MS" block fills the tag table of the animation (names,
  position tracks, duration), and the floating health bar is placed on the `HITPOINTBAR` track of
  the animation the unit plays, interpolated at the animation's clock. When that animation has
  no `HITPOINTBAR`, the bar goes to a height of the game's own, usually lower (inside a rider).
  So a unit whose animations do not all have the tag sees its bar jump at every change of
  animation, several times a minute when it stands, since idles are picked at random among
  variants.
- **The base game has the bug too:** its horse idles `animation_library\cavalry\horse_idle_a` to
  `_g` lack the tag while `_h`, `_i`, the walks, gallops and attacks have it (4.15 model units
  up), so every cavalry unit that uses them shows it; so do many villager and stance animations.
- **Seen in game (2026-11-13):** a loose `art\<path>.gr2.precomp` wins over the one in the
  archives (put there before the game starts). With the tag added at the idle's height to the animations
  of three units that lacked it (a light cavalry unit, an explorer, a line infantry unit), their
  bars stayed at one height through idles, a charge and a melee fight; without it, the light
  cavalry bars dropped by 12 to 14 pixels (at the default close zoom) at each change of idle,
  about once every two seconds.
- **To verify:** an animation with no `.gr2.precomp` at all (common in mods, whose own `.gr2`
  files come without one) must get its tags from the `.gr2` itself, which needs a
  `HITPOINTBAR` bone; not traced. Which block a file with several blocks gives to a given
  model is not known either.

`tools/fix_hitpointbar_tags.py` adds the missing tag: for each anim file, the median height of
the tag over the unit's Idle animations (or over all of its animations), as a constant track
with the file's number of keys; nothing else of the file changes. An animation shared by units
of different heights gets the height most of their anim files use. Its dry run over a large mod
(2,443 anim files of the units of its proto file): 533 anim files have animations without the
tag, 243 tag files to fix, 214 fixable, 29 refused (16 ties between heights, 12 files with no
tracks to take the number of keys from, 1 sampled on several models), and 390 uses of animations
with no tag file at all (367 of a loose `.gr2`, 23 of a missing one).

## Collision

A building's hitbox is three things, none of them its visible mesh:

- **Obstruction**, in the proto: `ObstructionRadiusX` and `Z`, half-sides of a rectangle. With the
  flag `SelectWithObstruction` it is also what a click selects. The stock fort's is 12 x 12 while its
  model reaches 7.3 from the centre: real models stand past their obstruction.
- **Collision shape**: `shape="<name>"` on a model reference in the anim file names
  `Data\\PHYSICS\\<name>.shp`. A plain Havok XML file (CRLF, sdk 20300): an `hkListShape` of
  `hkTransformShape`s, each around an `hkBoxShape`, in the model file's coordinates. The stock fort
  has 16 boxes. `aoe3game/collision.py` writes them, into `data\\physics\\` of the copy.
- **Physics body**: the proto's `PhysicsInfo` names `Data\\PHYSICS\\<name>.physics.xmb`, whose blueprint
  gives mass, friction and a shape of its own. Generated buildings inherit `house` from the template.

A generated building without boxes of its own points at the stock outpost's shape, 2 boxes
3.3 x 4.3 x 8.85, because it borrows that building's damage system (`bundle.DAMAGE_SKELETON`).

Seen in game (2026-11-04) with a generated shape of 17 boxes: the game loads it from
`data\\physics\\`, the building takes cannon fire, and it collapses and clears normally. What a shape
does to a shot aimed past a building is still unclear: four cannons firing at a target behind a
wing did no damage to either with these boxes; with the outpost's shape the building lost 2,000 hit
points and the target none. One run each, with the cannons in different places: repeat it before
relying on it.

## Damage

Large buildings do not change with their hit points: they break where they are hit. Measured on the
stock fort; a test building made this way worked in game.

- The anim file's `Idle` has a `<simskeleton>` with the `_damaged` model and a `<damagetemplate>`, and a
  `Destruction` logic swaps models (`p1` the damaged one, `p99` the intact one).
- The template is XML (`.dmg`, plain text or compiled `.dmg.xmb`): `<model name=...>`, then
  `<impactpoint name bone impacttype motionstopfadetime motionstopfadedelay splasheffect>` holding
  `<part mesh bone halfextents effect blueprint>`. The stock fort has 6 impact points and 24 parts.
- The damaged model is the body plus one mesh per part, each bound whole to its own bone
  (`debris_1a` to `bone_debris_1a`), its vertices in the model's coordinates, plus `boneimpactNN` bones.
- A hit near an impact point throws its parts off for good, so the building loses pieces under fire.
  Hand attacks and torches did not show it on the houses tried.

Cost: the stock fort goes from 1,589 triangles to 4,179. Our test cut a palace with boxes (faces clipped
with their UVs, 22 parts) and went from 1,610 to 3,214. It was dropped for that cost. Two things to solve
if it comes back: a hollow building shows the ground through its holes, so it needs a dark core inside;
and a part that rests on another one stays in the air when the lower one goes. Check that every part a
template names exists in its model: real mods ship templates whose models are empty, and nothing breaks.

## Impact effects

What a hit plays (particles, sounds) by the impact type of the surface it lands on. Measured on the
stock files (2026-11-13).

- **Files:** `art\effects\impacts\<weapon>.impacteffect`, compiled to `<weapon>.impacteffect.xmb`.
  The base game ships 14 of them, only compiled, plain `X1` (no `l33t` zlib), inside `Art1.bar`
  (arrow, cannon, dynamite, grenade, gun, hoop, melee, mortar, torch) and `Art5.bar` (chakram,
  crow, melee_no_weapon, sabotage, shuriken).
- **Layout:** a root `<impacteffect metercount=... meterlength=...>`, then one element per impact
  type (`wood`, `stone`, `flesh`, `rooftile`, `terraingrass`, `exitbuilding`, ...), each holding
  `particleset` and `soundset` children (several of each; `weight` and `fireexisttime` occur as
  attributes). The impact type of a surface comes from `impacttype` in a damage template (`.dmg`),
  a proto's `<ImpactType>` or a terrain type.
- **A loose file:** a compiled `.xmb` in the game's `art\effects\impacts\` is read instead of the
  archive's (seen in game with an edited `cannon.impacteffect.xmb`). An edited XML without its
  compiled twin is not enough: compile it.
- **Compile and decompile:** `python -I tools/xmbedit.py from-xml cannon.impacteffect` writes
  `cannon.impacteffect.xmb` next to it (a source saved as `cannon.impacteffect.xml` gives the same
  name); `python -I tools/xmbedit.py to-xml cannon.impacteffect.xmb` writes `cannon.impacteffect`.
  `to-xml` puts each element on the source line stored in the file, so the stored line numbers
  survive the text: for all 14 stock impact effects, `to-xml` then `from-xml` gives the original
  `.xmb` byte for byte, and `xmbedit.py check` proves it for any file.
- **Tested in game (2026-11-13):** the stock `cannon` impact effect, decompiled with `to-xml`, one
  element of an impact type of its own added (a water splash particle set, a metal sound), compiled
  with `from-xml` and put loose in `art\effects\impacts\`; a building whose `.dmg` names that type,
  hit by cannons: each hit threw the splash off its walls. A type outside the game's 15 needs the
  engine to know its name; with one of the 15 (`metal` is one no stock file uses), the data alone
  is enough.
- **Coverage of the text round trip:** over every `.xmb` in the base game's archives and the
  compiled protos and tech tree (about 6,000 files), all but 48 come back byte for byte. Of those, 47
  are anim and terrain files whose stored text keeps tabs after an element's text, before its
  children, which the XML text drops, and one repeats an attribute, which XML forbids. `check`
  reports such a file; its binary round trip still holds.

## Protos and strings

- `data\protoy.xml`: `<Unit id=... name=...>` blocks (both quote styles occur), CRLF line ends.
  A mod may ship it without the compiled twin; the engine prefers a `.xmb` that is newer than
  the XML, so a stale one would hide every edit (the deployment refuses to run then).
- New units: id = DBID, a number used by neither (the deployment takes the lowest free one from
  25,000). The entry is a copy of a template unit (the stock `House` by default) with the name,
  numbers, anim file, obstruction, rubble, placement rule and string numbers replaced, and its
  train, tech and command buttons removed.
- `data\stringtabley.xml`: UTF-16 with a byte order mark, `<String _locID='N'>`. New strings go
  before the comment block that closes the language.
- Sizes in game units: ObstructionRadiusX/Z are half sides; decals are full sides. The stock
  house: radius 2.0, decal 6.0, model 4.76 units wide.

## Calibration profile

`tools/art_survey.py --proto ... --profile-out ...` joins every unit with the Building type to
its anim file and finished model, measures the model, and groups the buildings by obstruction
footprint. `aoe3_blender_tools/profiles/buildings.json` is the profile of the target mod
(measurements and stock names only). Its largest class, 8 x 8 units (205 buildings): median
1,102 triangles, 90th percentile 2,221; obstruction 0.91 of the half side; decal 1.12 times the
side; construction stages 4x4; rubble `BuildingRubble4x4`.
