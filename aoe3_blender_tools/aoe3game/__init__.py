# SPDX-License-Identifier: GPL-3.0-or-later
"""Readers and writers for the game's own formats: Granny models (.gr2), textures (.ddt), anim
files, protos and string tables, plus the deployment into a test copy of the game.

Pure Python (standard library, numpy where noted). Nothing here imports Blender or the add-on's
`core`, so tools and plain tests can use it with `sys.path.insert(0, "<repo>/aoe3_blender_tools")`.
"""
