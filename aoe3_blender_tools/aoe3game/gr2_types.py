# SPDX-License-Identifier: GPL-3.0-or-later
"""The Granny 2.5 data tree types a static model needs, as the game's own 1-section building
files lay them out (member names, kinds and widths read off those files; no file content).

Each Spec is a list of (kind, name, referenced spec name or None, array width). The writer
serializes these definitions into the file, since a Granny file describes its own types.
"""
from .gr2 import (ARRAY_OF_REFS, INLINE, INT16, INT32, REAL32, REF_TO_ARRAY,
                  REF_TO_VARIANT_ARRAY, REFERENCE, STRING, TRANSFORM, UINT8, VARIANT_REF)


class Spec:
    def __init__(self, name, members):
        self.name = name
        self.members = members      # [(kind, name, ref, width)], ref resolved to a Spec

    def __repr__(self):
        return f"Spec({self.name})"


_RAW = {
    "FileInfo": [
        (REFERENCE, "ArtToolInfo", "ArtToolInfo", 0),
        (REFERENCE, "ExporterInfo", "ExporterInfo", 0),
        (STRING, "FromFileName", None, 0),
        (ARRAY_OF_REFS, "Textures", "Texture", 0),
        (ARRAY_OF_REFS, "Materials", "Material", 0),
        (ARRAY_OF_REFS, "Skeletons", "Skeleton", 0),
        (ARRAY_OF_REFS, "VertexDatas", "VertexData", 0),
        (ARRAY_OF_REFS, "TriTopologies", "TriTopology", 0),
        (ARRAY_OF_REFS, "Meshes", "Mesh", 0),
        (ARRAY_OF_REFS, "Models", "Model", 0),
        (ARRAY_OF_REFS, "TrackGroups", "TrackGroup", 0),
        (ARRAY_OF_REFS, "Animations", "Animation", 0),
        (VARIANT_REF, "ExtendedData", None, 0),
    ],
    "ArtToolInfo": [
        (STRING, "FromArtToolName", None, 0),
        (INT32, "ArtToolMajorRevision", None, 0),
        (INT32, "ArtToolMinorRevision", None, 0),
        (REAL32, "UnitsPerMeter", None, 0),
        (REAL32, "Origin", None, 3),
        (REAL32, "RightVector", None, 3),
        (REAL32, "UpVector", None, 3),
        (REAL32, "BackVector", None, 3),
    ],
    "ExporterInfo": [
        (STRING, "ExporterName", None, 0),
        (INT32, "ExporterMajorRevision", None, 0),
        (INT32, "ExporterMinorRevision", None, 0),
        (INT32, "ExporterCustomization", None, 0),
        (INT32, "ExporterBuildNumber", None, 0),
    ],
    "Texture": [
        (STRING, "FromFileName", None, 0),
        (INT32, "TextureType", None, 0),
        (INT32, "Width", None, 0),
        (INT32, "Height", None, 0),
        (INT32, "Encoding", None, 0),
        (INT32, "SubFormat", None, 0),
        (INLINE, "Layout", "PixelLayout", 0),
        (REF_TO_ARRAY, "Images", "TextureImage", 0),
        (VARIANT_REF, "ExtendedData", None, 0),
    ],
    "PixelLayout": [
        (INT32, "BytesPerPixel", None, 0),
        (INT32, "ShiftForComponent", None, 4),
        (INT32, "BitsForComponent", None, 4),
    ],
    "TextureImage": [(REF_TO_ARRAY, "MIPLevels", "TextureMIPLevel", 0)],
    "TextureMIPLevel": [
        (INT32, "Stride", None, 0),
        (REF_TO_ARRAY, "Pixels", "UInt8", 0),
    ],
    "UInt8": [(UINT8, "UInt8", None, 0)],
    "Material": [
        (STRING, "Name", None, 0),
        (REF_TO_ARRAY, "Maps", "MaterialMap", 0),
        (REFERENCE, "Texture", "Texture", 0),
        (VARIANT_REF, "ExtendedData", None, 0),
    ],
    "MaterialMap": [
        (STRING, "Usage", None, 0),
        (REFERENCE, "Map", "Material", 0),
    ],
    "Skeleton": [
        (STRING, "Name", None, 0),
        (REF_TO_ARRAY, "Bones", "Bone", 0),
    ],
    "Bone": [
        (STRING, "Name", None, 0),
        (INT32, "ParentIndex", None, 0),
        (TRANSFORM, "Transform", None, 0),
        (REAL32, "InverseWorldTransform", None, 16),
        (REFERENCE, "LightInfo", "LightInfo", 0),
        (REFERENCE, "CameraInfo", "CameraInfo", 0),
        (VARIANT_REF, "ExtendedData", None, 0),
    ],
    "LightInfo": [(VARIANT_REF, "ExtendedData", None, 0)],
    "CameraInfo": [(VARIANT_REF, "ExtendedData", None, 0)],
    "VertexData": [
        (REF_TO_VARIANT_ARRAY, "Vertices", None, 0),
        (REF_TO_ARRAY, "VertexAnnotationSets", "VertexAnnotationSet", 0),
    ],
    "VertexAnnotationSet": [
        (STRING, "Name", None, 0),
        (REF_TO_VARIANT_ARRAY, "VertexAnnotations", None, 0),
        (REF_TO_ARRAY, "VertexAnnotationIndices", "Int32", 0),
    ],
    "Int32": [(INT32, "Int32", None, 0)],
    "TriTopology": [
        (REF_TO_ARRAY, "Groups", "TriMaterialGroup", 0),
        (REF_TO_ARRAY, "Indices", "Int32", 0),
        (REF_TO_ARRAY, "Indices16", "Int16", 0),
        (REF_TO_ARRAY, "VertexToVertexMap", "Int32", 0),
        (REF_TO_ARRAY, "VertexToTriangleMap", "Int32", 0),
        (REF_TO_ARRAY, "SideToNeighborMap", "Int32", 0),
        (REF_TO_ARRAY, "BonesForTriangle", "Int32", 0),
        (REF_TO_ARRAY, "TriangleToBoneIndices", "Int32", 0),
        (REF_TO_ARRAY, "TriAnnotationSets", "TriAnnotationSet", 0),
    ],
    "TriMaterialGroup": [
        (INT32, "MaterialIndex", None, 0),
        (INT32, "TriFirst", None, 0),
        (INT32, "TriCount", None, 0),
    ],
    "Int16": [(INT16, "Int16", None, 0)],
    "TriAnnotationSet": [
        (STRING, "Name", None, 0),
        (REF_TO_VARIANT_ARRAY, "TriAnnotations", None, 0),
        (REF_TO_ARRAY, "TriAnnotationIndices", "Int32", 0),
    ],
    "Mesh": [
        (STRING, "Name", None, 0),
        (REFERENCE, "PrimaryVertexData", "VertexData", 0),
        (REF_TO_ARRAY, "MorphTargets", "MorphTarget", 0),
        (REFERENCE, "PrimaryTopology", "TriTopology", 0),
        (REF_TO_ARRAY, "MaterialBindings", "MaterialBinding", 0),
        (REF_TO_ARRAY, "BoneBindings", "BoneBinding", 0),
        (VARIANT_REF, "ExtendedData", None, 0),
    ],
    "MorphTarget": [
        (STRING, "ScalarName", None, 0),
        (REFERENCE, "VertexData", "VertexData", 0),
    ],
    "MaterialBinding": [(REFERENCE, "Material", "Material", 0)],
    "BoneBinding": [
        (STRING, "BoneName", None, 0),
        (REAL32, "OBBMin", None, 3),
        (REAL32, "OBBMax", None, 3),
        (REF_TO_ARRAY, "TriangleIndices", "Int32", 0),
    ],
    "Model": [
        (STRING, "Name", None, 0),
        (REFERENCE, "Skeleton", "Skeleton", 0),
        (TRANSFORM, "InitialPlacement", None, 0),
        (REF_TO_ARRAY, "MeshBindings", "ModelMeshBinding", 0),
    ],
    "ModelMeshBinding": [(REFERENCE, "Mesh", "Mesh", 0)],
    "TrackGroup": [
        (STRING, "Name", None, 0),
        (REF_TO_ARRAY, "VectorTracks", "VectorTrack", 0),
        (REF_TO_ARRAY, "TransformTracks", "TransformTrack", 0),
        (REF_TO_ARRAY, "TransformLODErrors", "Real32", 0),
        (REF_TO_ARRAY, "TextTracks", "TextTrack", 0),
        (TRANSFORM, "InitialPlacement", None, 0),
        (INT32, "AccumulationFlags", None, 0),
        (REAL32, "LoopTranslation", None, 3),
        (REFERENCE, "PeriodicLoop", "PeriodicLoop", 0),
        (REFERENCE, "RootMotion", "TransformTrack", 0),
        (VARIANT_REF, "ExtendedData", None, 0),
    ],
    "VectorTrack": [
        (STRING, "Name", None, 0),
        (INT32, "Dimension", None, 0),
        (INLINE, "ValueCurve", "Curve", 0),
    ],
    "Curve": [
        (INT32, "Degree", None, 0),
        (REF_TO_ARRAY, "Knots", "Real32", 0),
        (REF_TO_ARRAY, "Controls", "Real32", 0),
    ],
    "Real32": [(REAL32, "Real32", None, 0)],
    "TransformTrack": [
        (STRING, "Name", None, 0),
        (INLINE, "PositionCurve", "Curve", 0),
        (INLINE, "OrientationCurve", "Curve", 0),
        (INLINE, "ScaleShearCurve", "Curve", 0),
    ],
    "TextTrack": [
        (STRING, "Name", None, 0),
        (REF_TO_ARRAY, "Entries", "TextTrackEntry", 0),
    ],
    "TextTrackEntry": [
        (REAL32, "TimeStamp", None, 0),
        (STRING, "Text", None, 0),
    ],
    "PeriodicLoop": [
        (REAL32, "Radius", None, 0),
        (REAL32, "dAngle", None, 0),
        (REAL32, "dZ", None, 0),
        (REAL32, "BasisX", None, 3),
        (REAL32, "BasisY", None, 3),
        (REAL32, "Axis", None, 3),
    ],
    "Animation": [
        (STRING, "Name", None, 0),
        (REAL32, "Duration", None, 0),
        (REAL32, "TimeStep", None, 0),
        (ARRAY_OF_REFS, "TrackGroups", "TrackGroup", 0),
    ],
    # Variant types (named by the objects that use them).
    "VertexPNT": [                  # 32 bytes, as the game's static buildings
        (REAL32, "Position", None, 3),
        (REAL32, "Normal", None, 3),
        (REAL32, "TextureCoordinates0", None, 2),
    ],
    "ShaderParams": [               # the shortest material extension found in shipped models
        (STRING, "ESEffectName", None, 0),
        (STRING, "ESEffectParamName1", None, 0),
        (STRING, "ESEffectParamValue1", None, 0),
        (INT32, "ESEffectParamLookup1", None, 0),
    ],
    "ShaderParamsColour": [         # the same with the player colour transform
        (STRING, "ESEffectName", None, 0),
        (STRING, "ESEffectParamName1", None, 0),
        (STRING, "ESEffectParamValue1", None, 0),
        (INT32, "ESEffectParamLookup1", None, 0),
        (STRING, "ESEffectParamName2", None, 0),
        (STRING, "ESEffectParamValue2", None, 0),
        (INT32, "ESEffectParamLookup2", None, 0),
    ],
    "UserProperties": [(STRING, "UserDefinedProperties", None, 0)],
}


def schema():
    """Fresh Spec objects, references resolved (a new set per file keeps files independent)."""
    specs = {name: Spec(name, None) for name in _RAW}
    for name, members in _RAW.items():
        specs[name].members = [(k, n, specs[r] if r else None, w) for k, n, r, w in members]
    return specs
