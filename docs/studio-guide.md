# AoE3 Mod Studio: a guide for testers

Thank you for trying it. It takes about 15 minutes. What helps most is not that everything works,
but knowing **where you got stuck, what you did not understand, and what you expected to find**:
note it as you go.

## Opening it

1. Unzip `AoE3ModStudio-<version>-win32.zip` anywhere (the Desktop will do). Nothing else to
   install: no Python.
2. Open `AoE3ModStudio\AoE3ModStudio.exe`.
3. Windows may say **"Windows protected your PC"** (SmartScreen): the program is not signed.
   Choose **More info**, then **Run anyway**.
4. A window of its own opens (with Edge or Chrome; otherwise a tab of your browser). To close the
   program, close its window.

With **Blender 4.2 or newer** installed, the program finds it and exports with it. Without Blender
the game export still works, the **experimental** way (the "Without Blender" box): if you try it
so, say so in your notes. GLB, FBX and OBJ do need Blender.

## The tour

**1. Welcome (2 min).** On the first start a guide asks for your folders: the game's (only read)
and, if you have one, a copy of the game for testing. Each is checked as you choose it. "Later"
skips it.

**2. A building (5 min).** In **Buildings**:

- Pick a preset (an African house, say) and move its options: the 3D model changes at once.
- Try the buttons over the view: Person (for the scale), Obstruction, Low poly, Damaged.
- Look at the Texture tab and at the technical sheet, bottom right.
- **Check**, then **Export for the game** (with Blender, or "Without Blender").
- With a test copy: **Deploy**. It says what the copy already has and offers Add, Update or
  Replace. Then **Undo**.

**3. A texture (3 min).** In **Textures and units → Make a tileable texture**:

- Choose a photograph of a wall, a roof or wood.
- Move the square and look at the texture tiled 3 by 3.
- Keep it with a name and a licence ("my own photo").

**4. A flag (3 min, needs the game's folder).** In **Art utilities → Design a civ flag**:

- Press "Find them" for the flag folders, choose a picture of a flag, compare it with one of the
  game's.
- Write it: it goes to the work folder, never into the game.

**5. A look inside a file (2 min).** In **Survey and inspection → Look inside a game file**, open a
`.bar` of the game (in `art`) and look at a texture inside it.

## What to note

- **Where you got stuck or hesitated**, and what you did then.
- **Words you did not understand.**
- **Something you expected and did not find.**
- **Errors**: **Settings → Show the log** shows what happened; copy those lines.
- **Your computer**: Windows version, whether you have Blender and which.

Send it however you like: a message, a screenshot, an issue on GitHub.

## What the program never does

- Write into the game's folder or a Steam folder.
- Deploy without asking.
- Send anything to the Internet: everything happens on your computer.
