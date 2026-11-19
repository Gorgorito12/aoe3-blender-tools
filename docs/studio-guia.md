# AoE3 Mod Studio: guía de prueba

Gracias por probarlo. Son unos 15 minutos. Lo que más ayuda no es que todo salga bien, sino saber
**dónde te atascaste, qué no entendiste y qué esperabas encontrar**: anótalo mientras pruebas.

## Abrirlo

1. Descomprime `AoE3ModStudio-<versión>-win32.zip` en cualquier carpeta (por ejemplo, el
   Escritorio). No hace falta instalar Python ni nada más.
2. Abre `AoE3ModStudio\AoE3ModStudio.exe`.
3. Windows puede avisar con **"Windows protegió su PC"** (SmartScreen): el programa no está
   firmado. Pulsa **Más información** y luego **Ejecutar de todas formas**.
4. Se abre una ventana propia. Si tienes Edge o Chrome, es una ventana del programa; si no, una
   pestaña de tu navegador. Para cerrarlo, cierra la ventana.

Con **Blender 4.2 o posterior** instalado, el programa lo encuentra solo y exporta con él. Sin
Blender también se puede exportar al juego, de forma **experimental** (la casilla "Sin Blender"):
si lo pruebas así, dilo en tus notas. GLB, FBX y OBJ sí necesitan Blender.

## El recorrido

**1. Bienvenida (2 min).** La primera vez se abre una guía de carpetas. Indica la carpeta de tu juego
(solo se lee) y, si tienes, una copia del juego para pruebas. Cada carpeta se comprueba al elegirla.
Si no quieres, pulsa "Más tarde".

**2. Un edificio (5 min).** En **Edificios**:

- Elige un preset (por ejemplo, una casa africana) y mueve opciones: el modelo 3D cambia al momento.
- Prueba los botones sobre la vista: Persona (para la escala), Obstrucción, Pocos polígonos,
  Dañado.
- Mira la pestaña Textura y la ficha técnica abajo a la derecha.
- **Comprobar**, y después **Exportar al juego** (con Blender, o con "Sin Blender").
- Si indicaste una copia de prueba: **Desplegar**. El programa dice qué hay ya en la copia y te
  deja Añadir, Actualizar o Sustituir. Luego **Deshacer**.

**3. Una textura (3 min).** En **Texturas y unidades → Crear una textura repetible**:

- Elige una foto tuya de una pared, un tejado o madera.
- Mueve el cuadrado y mira la textura repetida 3 × 3.
- Guárdala con un nombre y una licencia ("foto propia").

**4. Una bandera (3 min, necesita la carpeta del juego).** En **Utilidades de arte → Diseñar una
bandera**:

- Pulsa "Buscarlas" para que encuentre las carpetas de banderas, elige una imagen de una bandera y
  compárala con una del juego.
- Escríbela: va a la carpeta de trabajo, nunca al juego.

**5. Mirar un archivo (2 min).** En **Estudio e inspección → Mirar dentro de un archivo del
juego**, abre un `.bar` del juego (en `art`) y mira una textura de dentro.

## Qué anotar

- **Dónde te atascaste o dudaste**, y qué hiciste entonces.
- **Textos que no entendiste**, o que estaban en inglés.
- **Algo que esperabas encontrar y no estaba.**
- **Errores**: en **Ajustes → Ver el registro** está lo que pasó; copia esas líneas.
- **Tu equipo**: versión de Windows, si tienes Blender y cuál.

Envíalo como prefieras: mensaje, captura o issue en GitHub.

## Lo que el programa nunca hace

- Escribir en la carpeta del juego o en una carpeta de Steam.
- Desplegar sin preguntar.
- Enviar nada a Internet: todo ocurre en tu PC.
