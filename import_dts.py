import bpy

import mathutils

from .DtsShape import DtsShape
from .DtsTypes import *

# TODO: Load from the detail level down, not by-object/node

def write_debug_report(filepath, shape):
    with open(filepath, "w") as fd:
        def p(line):
            fd.write(line + "\n")
        def gn(i):
            return shape.names[i]
        def ln(table, first, count):
            def each(i):
                entry = table[i]
                if hasattr(entry, "name"):
                    return str(i) + " -> " + gn(entry.name)
                else:
                    return str(i)
            return ", ".join(map(each, range(first, first + count)))

        p("smallest_size = " + str(shape.smallest_size))
        p("smallest_detail_level = " + str(shape.smallest_detail_level))
        p("radius = " + str(shape.radius))
        p("radius_tube = " + str(shape.radius_tube))
        p("center = " + str(shape.center))
        p("bounds = " + str(shape.bounds))
        # p("Decals (deprecated): " + str(len(shape.decals)))
        # p("IFL materials: " + str(len(shape.iflmaterials)))
        # p("Materials: " + str(len(shape.materials)))
        p("Ground frames: " + str(len(shape.ground_translations)))
        # p("Decal states (deprecated): " + str(len(shape.decalstates)))
        p("Triggers: " + str(len(shape.triggers)))
        p("Sequences: " + str(len(shape.sequences)))

        p("Default translations:")
        for each in shape.default_translations:
            p("  " + str(each))
        for each in shape.default_rotations:
            p("  " + str(each))

        p("Object states (" + str(len(shape.objectstates)) + "):")
        for i, state in enumerate(shape.objectstates):
            p("  " + str(i))
            p("    vis = " + str(state.vis))
            p("    frame = " + str(state.frame))
            p("    matFrame = " + str(state.matFrame))

        p("IFL materials (" + str(len(shape.iflmaterials)) + "):")
        for ifl in shape.iflmaterials:
            p("  IflMat " + gn(ifl.name))
            p("    slot = " + str(ifl.slot))
            p("    firstFrame = " + str(ifl.firstFrame))
            p("    numFrames = " + str(ifl.numFrames))
            p("    time = " + str(ifl.time))

        p("Materials (" + str(len(shape.materials)) + "):")
        for i, mat in enumerate(shape.materials):
            p("  " + str(i) + " " + mat.name)
            flagNames = ("SWrap", "TWrap", "Translucent", "Additive", "Subtractive", "SelfIlluminating", "NeverEnvMap", "NoMipMap", "MipMapZeroBorder", "IFLMaterial", "IFLFrame", "DetailMap", "BumpMap", "ReflectanceMap", "AuxiliaryMask")
            flags = ""
            for name in flagNames:
                if mat.flags & getattr(Material, name):
                    flags += " " + name
            p("    flags = " + str(mat.flags) + flags)
            p("    reflectanceMap = " + str(mat.reflectanceMap))
            p("    reflectance = " + str(mat.reflectance))
            p("    bumpMap = " + str(mat.bumpMap))
            p("    detailMap = " + str(mat.detailMap))
            p("    detailScale = " + str(mat.detailScale))

        p("Detail levels (" + str(len(shape.detail_levels)) + "):")
        for i, lod in enumerate(shape.detail_levels):
            p("  LOD " + str(i) + " " + gn(lod.name))
            # p("    name = " + gn(lod.name))
            p("    subshape = " + str(lod.subshape))
            p("    objectDetail = " + str(lod.objectDetail))
            p("    size = " + str(lod.size))
            p("    polyCount = " + str(lod.polyCount))
            # p("    avgError (unused) = " + str(lod.avgError))
            # p("    maxError (unused) = " + str(lod.maxError))

        p("Subshapes (" + str(len(shape.subshapes)) + "):")
        for i, sub in enumerate(shape.subshapes):
            p("  Subshape " + str(i))
            # p("    firstNode = " + str(sub.firstNode))
            # p("    firstObject = " + str(sub.firstObject))
            # p("    firstDecal (deprecated) = " + str(sub.firstDecal))
            # p("    numNodes = " + str(sub.numNodes))
            # p("    numObjects = " + str(sub.numObjects))
            # p("    numDecals (deprecated) = " + str(sub.numDecals))
            # p("      nodes = " + ln(shape.nodes, sub.firstNode, sub.numNodes))
            # p("      objects = " + ln(shape.objects, sub.firstObject, sub.numObjects))
            p("    nodes = " + ln(shape.nodes, sub.firstNode, sub.numNodes))
            p("    objects = " + ln(shape.objects, sub.firstObject, sub.numObjects))
            # p("      decals (deprecated) = " + ln(shape.decals, sub.firstDecal, sub.numDecals))

        p("Nodes (" + str(len(shape.nodes)) + "):")
        for i, node in enumerate(shape.nodes):
            if node.parent == -1:
                p("  " + str(i) + " " + gn(node.name))
            else:
                p("  " + str(i) + " " + gn(node.name) + "  ->  " + str(node.parent) + " " + gn(shape.nodes[node.parent].name))
            # p("  Node " + str(i))
            # p("    name = " + gn(node.name))
            # if node.parent == -1:
            #     p("    parent = -1 (NONE)")
            # else:
            #     p("    parent = " + str(node.parent) + " (" + gn(shape.nodes[node.parent].name) + ")")
            # p("    firstObject (deprecated) = " + str(node.firstObject))
            # p("    child (deprecated) = " + str(node.child))
            # p("    sibling (deprecated) = " + str(node.sibling))

        p("Objects (" + str(len(shape.objects)) + "):")
        for i, obj in enumerate(shape.objects):
            p("  " + str(i) + " " + gn(obj.name))
            # p("    name = " + gn(obj.name))
            # p("    numMeshes = " + str(obj.numMeshes))
            # p("    firstMesh = " + str(obj.firstMesh))
            if obj.node == -1:
                p("    node = -1 (none)")
            else:
                p("    node = " + str(obj.node) + " (" + gn(shape.nodes[obj.node].name) + ")")
            # p("    sibling (deprecated) = " + str(obj.sibling))
            # p("    firstDecal (deprecated) = " + str(obj.firstDecal))
            # p("      meshes = " + ln(shape.meshes, obj.firstMesh, obj.numMeshes))
            p("    meshes = " + ln(shape.meshes, obj.firstMesh, obj.numMeshes))

        p("Meshes (" + str(len(shape.meshes)) + "):")
        for i, mesh in enumerate(shape.meshes):
            p("  Mesh " + str(i))
            p("    type = " + mesh.type.name + " (" + str(mesh.type.value) + ")")
            p("    bounds = " + str(mesh.bounds))
            p("    center = " + str(mesh.center))
            p("    radius = " + str(mesh.radius))
            p("    numFrames = " + str(mesh.numFrames))
            p("    matFrames = " + str(mesh.matFrames))
            p("    vertsPerFrame = " + str(mesh.vertsPerFrame))
            p("    parent (unused?) = " + str(mesh.parent))
            p("    flags = " + str(mesh.flags))
            p("    indices = " + ",".join(map(str, mesh.indices)))
            p("    mindices = " + ",".join(map(str, mesh.mindices)))
            p("    + Primitives (" + str(len(mesh.primitives)) + "):")
            for prim in mesh.primitives:
                flags = ""
                if prim.type & Primitive.Triangles:
                    flags += " Triangles"
                if prim.type & Primitive.Strip:
                    flags += " Strip"
                if prim.type & Primitive.Fan:
                    flags += " Fan"
                if flags == "":
                    flags += " NoExplicitType->Triangles"
                if prim.type & Primitive.Indexed:
                    flags += " Indexed"
                if prim.type & Primitive.NoMaterial:
                    flags += " NoMaterial"
                mat = prim.type & Primitive.MaterialMask
                flags += " MaterialMask:" + str(mat)
                p("      " + str(prim.firstElement) + "->" + str(prim.firstElement + prim.numElements - 1) + " " + str(prim.type) + flags)
            p("    + Vertices (" + str(len(mesh.verts)) + "):")
            for i in range(len(mesh.verts)):
                p("      vert" + str(i) + " " + str(mesh.verts[i]) + " normal " + str(mesh.normals[i]) + " encoded " + str(mesh.enormals[i]))
            p("    + Texture coords (" + str(len(mesh.tverts)) + "):")
            for i in range(len(mesh.tverts)):
                p("      tvert" + str(i) + " " + str(mesh.tverts[i]))

        p("Names (" + str(len(shape.names)) + "):")
        for i, name in enumerate(shape.names):
            p("  " + str(i) + " = " + name)

from random import random

default_materials = {
    "black": (0, 0, 0),
    "black25": (191, 191, 191),
    "black50": (128, 128, 128),
    "black75": (64, 64, 64),
    "blank": (255, 255, 255),
    "blue": (0, 0, 255),
    "darkRed": (128, 0, 0),
    "gray25": (64, 64, 64),
    "gray50": (128, 128, 128),
    "gray75": (191, 191, 191),
    "green": (26, 128, 64),
    "lightBlue": (10, 186, 245),
    "lightYellow": (249, 249, 99),
    "palegreen": (125, 136, 104),
    "red": (213, 0, 0),
    "white": (255, 255, 255),
    "yellow": (255, 255, 0)
}

for name, color in default_materials.items():
    default_materials[name] = (color[0] / 255, color[1] / 255, color[2] / 255)

def import_material(dmat):
    bmat = bpy.data.materials.new(dmat.name)

    if False:
        pass # did we find a texture?
    elif dmat.name in default_materials:
        bmat.diffuse_color = default_materials[dmat.name]
    else: # give it a random color
        bmat.diffuse_color = (random(), random(), random())

    if dmat.flags & Material.Translucent:
        bmat.use_transparency = True
    if dmat.flags & Material.SelfIlluminating:
        bmat.use_shadeless = True
    if dmat.flags & Material.Additive:
        bmat["additive"] = True
    if dmat.flags & Material.Subtractive:
        bmat["subtractive"] = True
    if not (dmat.flags & Material.SWrap):
        bmat["noSWrap"] = True
    if not (dmat.flags & Material.TWrap):
        bmat["noTWrap"] = True

    return bmat

def load(operator, context, filepath,
         lod_as_empty=True,
         include_armatures=True,
         hide_default_player=False,
         debug_report=False):
    shape = DtsShape()

    with open(filepath, "rb") as fd:
        shape.load(fd)

    if debug_report:
        write_debug_report(filepath + ".txt", shape)

    node_lod = {}
    scene_material_table = {}

    if lod_as_empty:
        for lod in shape.detail_levels:
            print("creating lod " + shape.names[lod.name])
            empty = bpy.data.objects.new(name=shape.names[lod.name], object_data=None)
            context.scene.objects.link(empty)
            sub = shape.subshapes[lod.subshape]

            for i in range(sub.firstNode, sub.firstNode + sub.numNodes):
                print("  associating node " + str(i) + " with it")
                node_lod[i] = empty

    if include_armatures:
        # First load all the nodes into armatures
        nodes = [] # For accessing indices when parenting later

        for i, node in enumerate(shape.nodes):
            amt = bpy.data.armatures.new(shape.names[node.name])
            bnode = bpy.data.objects.new(name=shape.names[node.name], object_data=amt)
            bnode.location = mathutils.Vector(shape.default_translations[i])

            bnode.rotation_mode = "QUATERNION"
            bnode.rotation_quaternion = mathutils.Quaternion((
                -shape.default_rotations[i][3],
                shape.default_rotations[i][0],
                shape.default_rotations[i][1],
                shape.default_rotations[i][2]
            ))

            context.scene.objects.link(bnode)
            nodes.append((node, bnode, i))

        # Now set all the parents appropriately
        for node, bnode, nodei in nodes:
            if node.parent != -1:
                bnode.parent = nodes[node.parent][1]
            elif nodei in node_lod:
                bnode.parent = node_lod[nodei]
    else:
        objects = {}

    # Then put objects in the armatures
    for obj in shape.objects:
        meshes = (shape.meshes[i] for i in range(obj.firstMesh, obj.firstMesh + obj.numMeshes))
        meshes = list(filter(lambda m: m.type != MeshType.Null, meshes))

        if len(meshes) != 1: # TODO...
            print("Skipping object {} with {} meshes (only 1 mesh per object is supported)".format(
                shape.names[obj.name], obj.numMeshes))
            continue

        mesh = meshes[0]

        if mesh.type != MeshType.Standard: # TODO: Support other types too...
            #if mesh.type != MeshType.None: # No need to warn for this, it's intended..
            print("{} is a {} mesh, skipping due to lack of support".format(
                shape.names[obj.name], mesh.type.name))
            continue

        faces = []

        # Create a new mesh, update data later
        bmesh = bpy.data.meshes.new(name="Mesh")

        mesh_material_table = {}
        mesh_material_apply = {}

        # Go through all the primitives in the mesh and convert them to pydata faces
        for prim in mesh.primitives:
            material_dts = None

            if not (prim.type & Primitive.NoMaterial):
                material_dts = shape.materials[prim.type & Primitive.MaterialMask]

            apply_start = len(faces)

            if prim.type & Primitive.Strip:
                even = True
                for i in range(prim.firstElement + 2, prim.firstElement + prim.numElements):
                    if even:
                        faces.append((mesh.indices[i], mesh.indices[i - 1], mesh.indices[i - 2]))
                    else:
                        faces.append((mesh.indices[i - 2], mesh.indices[i - 1], mesh.indices[i]))
                    even = not even
            elif prim.type & Primitive.Fan:
                even = True
                for i in range(prim.firstElement + 2, prim.firstElement + prim.numElements):
                    if even:
                        faces.append((mesh.indices[i], mesh.indices[i - 1], mesh.indices[0]))
                    else:
                        faces.append((mesh.indices[0], mesh.indices[i - 1], mesh.indices[i]))
                    even = not even
            else: # Default to Triangle Lists (prim.type & Primitive.Triangles)
                for i in range(prim.firstElement + 2, prim.firstElement + prim.numElements, 3):
                    faces.append((mesh.indices[i], mesh.indices[i - 1], mesh.indices[i - 2]))

            apply_end = len(faces)

            if apply_end > apply_start and material_dts:
                material = scene_material_table.get(material_dts)

                if material == None:
                    material = import_material(material_dts)
                    scene_material_table[material_dts] = material

                material_index = mesh_material_table.get(material)

                if material_index == None:
                    material_index = len(bmesh.materials)
                    mesh_material_table[material] = material_index
                    bmesh.materials.append(material)

                for i in range(apply_start, apply_end):
                    mesh_material_apply[i] = material_index

        # Now add faces & vertices and parent it to the armature if any
        bmesh.from_pydata(mesh.verts, [], faces)
        bmesh.update()

        # Assign all the materials first
        if mesh_material_apply:
            faces_no_mat = set(range(len(bmesh.polygons)))

            for face_index, material_index in mesh_material_apply.items():
                bmesh.polygons[face_index].material_index = material_index
                faces_no_mat.remove(face_index)

            if faces_no_mat:
                index_no_mat = len(bmesh.materials)
                bmesh.materials.append(None)

                for face_index in faces_no_mat:
                    bmesh.polygons[face_index].material_index = index_no_material

        bobj = bpy.data.objects.new(name=shape.names[obj.name], object_data=bmesh)
        context.scene.objects.link(bobj)

        if obj.node != -1:
            if include_armatures:
                bobj.parent = nodes[obj.node][1]
            else:
                objects.setdefault(obj.node, []).append(bobj)

        if hide_default_player and shape.names[obj.name] not in ("HeadSkin", "chest", "Larm", "Lhand", "Rarm", "Rhand", "pants", "LShoe", "RShoe"):
            bobj.hide = True

    if not include_armatures:
        for nodeid, bobjs in objects.items():
            # Try to find a parent
            node = shape.nodes[nodeid]
            if node.parent == -1 or node.parent not in objects:
                continue
            if len(objects[node.parent]) == 1:
                for bobj in bobjs:
                    bobj.parent = objects[node.parent][0]
                continue
            # ... do something clever here

    return {"FINISHED"}
