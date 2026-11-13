# SPDX-License-Identifier: GPL-3.0-or-later
"""Building styles. Each style module has:

    NAME              the key in STYLES and the value of BuildingParams.style
    clamp(p)          a copy of the parameters with values its geometry can build
    build(p, params)  the Model of the clamped `p` (`params` as given, for the notes)
    opening_tops(spec, p)  the top of each storey's openings on a facade (the damaged texture)
    paint(pr, model)  draws the texture on a `core.painter.Painter`

and builds with `core.kit.Builder`. Pure Python: no Blender import."""
from . import african, colonial, neoclassical, props, timber

STYLES = {neoclassical.NAME: neoclassical, colonial.NAME: colonial, timber.NAME: timber, african.NAME: african,
          props.NAME: props}
