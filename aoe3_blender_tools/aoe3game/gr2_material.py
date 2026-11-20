# SPDX-License-Identifier: GPL-3.0-or-later
"""The materials of a copied model tree (gr2_edit.copy_tree): their maps and shader, and adding a
bump map to one that has none.

A material the game draws with a `bumpspec...` shader (its ExtendedData's ESEffectName) reads its
normals and specular from the map whose Usage is "Bump"; without one, an art lead notes, its
highlights come out wrong. `add_bump` gives such a material a "Bump" map, built like its "Diffuse
Color" map (a map material holding a texture), naming the given texture.
"""
from . import gr2_write

BUMP_SHADERS = ("bumpspec",)


def maps(mat):
    """{usage in lower case: the map's material} of a material W."""
    out = {}
    for mp in mat.values.get("Maps") or []:
        if mp is not None:
            out[(mp.values.get("Usage") or "").lower()] = mp.values.get("Map")
    return out


def shader(mat):
    ed = mat.values.get("ExtendedData")
    if isinstance(ed, gr2_write.W):
        return ed.values.get("ESEffectName") or ""
    return ""


def texture_of(map_mat):
    return map_mat.values.get("Texture") if isinstance(map_mat, gr2_write.W) else None


def wants_bump(mat):
    """Does the material's shader read a bump map it does not have?"""
    m = maps(mat)
    return shader(mat).lower().startswith(BUMP_SHADERS) and "diffuse color" in m and "bump" not in m


def materials(root):
    """Every material W bound to a mesh, once."""
    out, seen = [], set()
    for mesh in root.values.get("Meshes") or []:
        for mb in mesh.values.get("MaterialBindings") or []:
            mat = mb.values.get("Material") if mb is not None else None
            if isinstance(mat, gr2_write.W) and id(mat) not in seen:
                seen.add(id(mat))
                out.append(mat)
    return out


def add_bump(root, mat, stored_name):
    """Gives `mat` a "Bump" map naming `stored_name`, made like its "Diffuse Color" map, and puts
    the new texture and map material in the file's lists."""
    diffuse = maps(mat)["diffuse color"]
    dmap = next(mp for mp in mat.values["Maps"] if (mp.values.get("Usage") or "").lower() == "diffuse color")
    dtex = texture_of(diffuse)
    if dtex is None:
        raise ValueError("the diffuse map holds no texture")
    tex = gr2_write.W(dtex.spec, **dict(dtex.values))
    tex.values["FromFileName"] = stored_name
    tex.values["Images"] = None
    bump_mat = gr2_write.W(diffuse.spec, **dict(diffuse.values))
    bump_mat.values["Name"] = (diffuse.values.get("Name") or "Map") + " bump"
    bump_mat.values["Texture"] = tex
    bump_mat.values["Maps"] = None
    mat.values["Maps"] = list(mat.values["Maps"]) + [gr2_write.W(dmap.spec, Usage="Bump", Map=bump_mat)]
    root.values["Textures"] = list(root.values.get("Textures") or []) + [tex]
    root.values["Materials"] = list(root.values.get("Materials") or []) + [bump_mat]
    return tex
