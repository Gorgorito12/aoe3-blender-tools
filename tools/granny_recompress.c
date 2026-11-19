/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * granny_recompress: a 32-bit host for two calls of the game's own Granny runtime (granny2.dll),
 * which a 64-bit Python cannot load. tools/recompress_models.py runs it; nothing else needs it.
 *
 *   granny_recompress <granny2.dll> recompress <in.gr2> <out.gr2> <for 0> [<for 1> [<for 2>]]
 *   granny_recompress <granny2.dll> crc <file.gr2>
 *
 * recompress calls GrannyRecompressFile(in, out, n, map): the runtime rewrites the file with every
 * section whose stored format is k (0 none, 1 Oodle0, 2 Oodle1) stored in format map[k], keeping
 * the sections' order, records and fixups. crc calls GrannyFileCRCIsValid.
 * Exit status: 0 done (crc: valid), 1 the runtime refused (crc: not valid), 2 usage, 3 the DLL or
 * its export was not found.
 *
 * The DLL is RAD Game Tools' and is never shipped with this tool: the caller names the game's copy.
 * Build (x86 only):
 *   cl /nologo /O2 /W4 granny_recompress.c /Fe:granny_recompress.exe     (VS x86 prompt)
 *   zig cc -target x86-windows-gnu -O2 granny_recompress.c -o granny_recompress.exe
 * or `python -I tools/recompress_models.py --build-helper <out.exe>`, which finds either.
 */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if !defined(_M_IX86) && !defined(__i386__)
#error "granny2.dll is 32-bit: build this helper for x86"
#endif

typedef int (__stdcall *RecompressFn)(const char *src, const char *dst, int count, const int *map);
typedef int (__stdcall *CrcFn)(const char *name);

static FARPROC need(HMODULE dll, const char *name)
{
    FARPROC p = GetProcAddress(dll, name);
    if (!p)
        fprintf(stderr, "granny_recompress: %s not exported\n", name);
    return p;
}

int main(int argc, char **argv)
{
    HMODULE dll;
    if (argc < 4) {
        fputs("usage: granny_recompress <granny2.dll> recompress <in> <out> <f0> [<f1> [<f2>]]\n"
              "       granny_recompress <granny2.dll> crc <file>\n", stderr);
        return 2;
    }
    dll = LoadLibraryA(argv[1]);
    if (!dll) {
        fprintf(stderr, "granny_recompress: cannot load %s (error %lu)\n", argv[1], GetLastError());
        return 3;
    }
    if (strcmp(argv[2], "recompress") == 0 && argc >= 6 && argc <= 8) {
        int map[3], n = argc - 5, i;
        RecompressFn recompress = (RecompressFn)need(dll, "_GrannyRecompressFile@16");
        if (!recompress)
            return 3;
        for (i = 0; i < n; ++i) {
            char *end;
            long v = strtol(argv[5 + i], &end, 10);
            if (*end || v < 0 || v > 2)
                return 2;
            map[i] = (int)v;
        }
        return (recompress(argv[3], argv[4], n, map) & 0xFF) ? 0 : 1;   /* a bool in AL */
    }
    if (strcmp(argv[2], "crc") == 0 && argc == 4) {
        /* GrannyFileCRCIsValid takes a file name. */
        CrcFn crc = (CrcFn)need(dll, "_GrannyFileCRCIsValid@4");
        if (!crc)
            return 3;
        return (crc(argv[3]) & 0xFF) ? 0 : 1;
    }
    return 2;
}
