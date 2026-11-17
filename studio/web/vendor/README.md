# Vendored libraries

| File | Library | Version | Licence | Source |
|---|---|---|---|---|
| `three.module.min.js` | three.js | 0.160.0 | MIT (`LICENSE-three.txt`) | https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js |
| `OrbitControls.js` | three.js addon | 0.160.0 | MIT (`LICENSE-three.txt`) | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js |

`OrbitControls.js` is unchanged but for its import line, which names `./three.module.min.js`
instead of the bare `three` (the page loads no import map: its content security policy allows
scripts from the studio only).
