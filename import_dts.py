import bpy

import mathutils

from .DtsShape import DtsShape
from .DtsTypes import *
from .write_report import write_debug_report

# TODO: Load from the detail level down, not by-object/node

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
        with open(filepath + ".pass.dts", "wb") as fd:
            shape.save(fd)

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
            bnode.location = mathutils.Vector(shape.default_translations[i].tuple())

            bnode.rotation_mode = "QUATERNION"
            bnode.rotation_quaternion = mathutils.Quaternion((
                -shape.default_rotations[i].w,
                shape.default_rotations[i].x,
                shape.default_rotations[i].y,
                shape.default_rotations[i].z
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
        bmesh.from_pydata(tuple(v.tuple() for v in mesh.verts), (), faces)
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
