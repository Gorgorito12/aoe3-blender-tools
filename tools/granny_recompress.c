/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * granny_recompress: a 32-bit host for some calls of the game's own Granny runtime (granny2.dll),
 * which a 64-bit Python cannot load. tools/recompress_models.py runs it; nothing else needs it.
 *
 *   granny_recompress <granny2.dll> recompress <in.gr2> <out.gr2> <for 0> [<for 1> [<for 2>]]
 *   granny_recompress <granny2.dll> crc <file.gr2>
 *   granny_recompress <granny2.dll> info <file.gr2>
 *
 * recompress calls GrannyRecompressFile(in, out, n, map): the runtime rewrites the file with every
 * section whose stored format is k (0 none, 1 Oodle0, 2 Oodle1) stored in format map[k], keeping
 * the sections' order, records and fixups. crc calls GrannyFileCRCIsValid. info loads the file as
 * the game does (GrannyReadEntireFile, GrannyGetFileInfo) and prints, a line each, tab-separated:
 *   version <the runtime's version>
 *   mesh <name> <vertices> <indices> <triangles> <rigid 0/1>, then binding <bone name> per binding
 *   skeleton <name> <bones>, then bone <name> <parent index> per bone
 * It finds each member by its name in the runtime's own type tables (each export, such as
 * GrannyFileInfoType, holds a pointer to its table), so nothing about the structures' layout is
 * assumed. types <export> lists one of those tables.
 * Exit status: 0 done (crc: valid), 1 the runtime refused (crc: not valid), 2 usage, 3 the DLL or
 * its export was not found, 4 (info) a member was not found in the runtime's types.
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

/* a member record of a Granny type table (granny_data_type_definition, 32 bytes on x86) */
typedef struct member { int type; const char *name; const struct member *ref; int width; int extra[4]; } member;
typedef void *(__stdcall *PtrFn)(void *);
typedef int (__stdcall *IntFn)(const void *);
typedef const char *(__stdcall *StrFn)(void);
static int type_size(const member *t);

static int member_size(const member *m)
{
    int w = m->width > 0 ? m->width : 1;
    switch (m->type) {
    case 1: return type_size(m->ref) * w;                 /* inline */
    case 2: case 8: return 4;                             /* reference, string */
    case 3: case 4: case 5: return 8;                     /* array, array of references, variant */
    case 7: return 12;                                    /* variant array */
    case 9: return 68 * w;                                /* transform */
    case 10: case 19: case 20: return 4 * w;
    case 11: case 12: case 13: case 14: return w;
    case 15: case 16: case 17: case 18: return 2 * w;
    }
    return -1;
}

/* an object's size: the sum of its members' (the runtime's GrannyGetTotalTypeSize measures the
   type table itself, 32 bytes a record) */
static int type_size(const member *t)
{
    int n = 0, s;
    for (; t && t->type; ++t) {
        if ((s = member_size(t)) < 0)
            return -1;
        n += s;
    }
    return n;
}

/* the offset of a member found by name in a type table, and its record; NULL when absent */
static const member *field(const member *t, const char *name, int *off)
{
    int o = 0, s;
    for (; t && t->type; ++t) {
        if (t->name && strcmp(t->name, name) == 0) {
            *off = o;
            return t;
        }
        if ((s = member_size(t)) < 0)
            return NULL;
        o += s;
    }
    return NULL;
}

#define AT(p, off, T) (*(T *)((char *)(p) + (off)))

static const char *text(const char *s) { return s ? s : ""; }

static int info(HMODULE dll, const char *path)
{
    PtrFn read = (PtrFn)need(dll, "_GrannyReadEntireFile@4");
    PtrFn get_info = (PtrFn)need(dll, "_GrannyGetFileInfo@4");
    PtrFn free_file = (PtrFn)need(dll, "_GrannyFreeFile@4");
    IntFn vcount = (IntFn)need(dll, "_GrannyGetMeshVertexCount@4");
    IntFn icount = (IntFn)need(dll, "_GrannyGetMeshIndexCount@4");
    IntFn tcount = (IntFn)need(dll, "_GrannyGetMeshTriangleCount@4");
    IntFn rigid = (IntFn)need(dll, "_GrannyMeshIsRigid@4");
    StrFn version = (StrFn)need(dll, "_GrannyGetVersionString@0");
    const member *const *fi_at = (const member *const *)need(dll, "GrannyFileInfoType");
    const member *fi = fi_at ? *fi_at : NULL;     /* the export holds a pointer to the table */
    const member *mm, *sm, *bm, *bb;
    int o_meshes, o_skels, o_mname, o_bind, o_bname, o_sname, o_bones, o_name, o_parent, i, j;
    void *file, *fileinfo;
    setvbuf(stdout, NULL, _IONBF, 0);                 /* every line out, even if the runtime fails */
    if (!read || !get_info || !free_file || !vcount || !icount || !tcount || !rigid || !version || !fi)
        return 3;
    printf("version\t%s\n", version());
    file = read((void *)path);
    if (!file) {
        puts("refused\tthe runtime could not read the file");
        return 1;
    }
    fileinfo = get_info(file);
    if (!fileinfo) {
        puts("refused\tthe file holds no file info");
        free_file(file);
        return 1;
    }
#define FIND(var, type, name, off) if (!((var) = field((type), (name), (off)))) { \
        printf("refused\tno member %s in the runtime's types\n", (name)); free_file(file); return 4; }
    FIND(mm, fi, "Meshes", &o_meshes)
    FIND(sm, fi, "Skeletons", &o_skels)
    FIND(bb, mm->ref, "Name", &o_mname)
    FIND(bb, mm->ref, "BoneBindings", &o_bind)
    FIND(bm, bb->ref, "BoneName", &o_bname)
    FIND(bm, sm->ref, "Name", &o_sname)
    FIND(bm, sm->ref, "Bones", &o_bones)
    {
        const member *x;
        FIND(x, bm->ref, "Name", &o_name)
        FIND(x, bm->ref, "ParentIndex", &o_parent)
    }
    for (i = 0; i < AT(fileinfo, o_meshes, int); ++i) {
        void *mesh = AT(fileinfo, o_meshes + 4, void **)[i];
        int nb = AT(mesh, o_bind, int), stride = type_size(bb->ref);
        char *binds = AT(mesh, o_bind + 4, char *);
        printf("mesh\t%s\t%d\t%d\t%d\t%d\n", text(AT(mesh, o_mname, const char *)),
               vcount(mesh), icount(mesh), tcount(mesh), rigid(mesh) & 0xFF);
        for (j = 0; j < nb; ++j)
            printf("binding\t%s\n", text(AT(binds + j * stride, o_bname, const char *)));
    }
    for (i = 0; i < AT(fileinfo, o_skels, int); ++i) {
        void *sk = AT(fileinfo, o_skels + 4, void **)[i];
        int nb = AT(sk, o_bones, int), stride = type_size(bm->ref);
        char *bones = AT(sk, o_bones + 4, char *);
        printf("skeleton\t%s\t%d\n", text(AT(sk, o_sname, const char *)), nb);
        for (j = 0; j < nb; ++j)
            printf("bone\t%s\t%d\n", text(AT(bones + j * stride, o_name, const char *)),
                   AT(bones + j * stride, o_parent, int));
    }
    free_file(file);
    return 0;
}

int main(int argc, char **argv)
{
    HMODULE dll;
    if (argc < 4) {
        fputs("usage: granny_recompress <granny2.dll> recompress <in> <out> <f0> [<f1> [<f2>]]\n"
              "       granny_recompress <granny2.dll> crc <file>\n"
              "       granny_recompress <granny2.dll> info <file>\n", stderr);
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
    if (strcmp(argv[2], "info") == 0 && argc == 4)
        return info(dll, argv[3]);
    if (strcmp(argv[2], "types") == 0 && argc == 4) {      /* one of the runtime's type tables, as it holds it */
        const member *const *at = (const member *const *)need(dll, argv[3]);
        const member *t = at ? *at : NULL;
        int k;
        if (!t)
            return 3;
        for (k = 0; k < 64 && t[k].type; ++k)
            printf("%d\t%s\t%d\t%d\n", t[k].type, text(t[k].name), t[k].width, member_size(&t[k]));
        printf("size\t%d\n", type_size(t));
        return 0;
    }
    return 2;
}
