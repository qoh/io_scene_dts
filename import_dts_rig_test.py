import bpy

import mathutils

from .DtsInputShape import DtsInputShape, DtsInputStream
from .DtsTypes import *

def load(operator, context, filepath):
    with open(filepath, "rb") as fd:
        shape = DtsInputShape(DtsInputStream(fd))

    # First load all the nodes into armatures
    nodes = [] # For accessing indices when parenting later

    # bpy.ops.object.mode_set(mode="OBJECT")

    for item in context.selectable_objects:  
        item.select = False

    for i, node in enumerate(shape.nodes):
        # Create an armature and an object for it
        # amt = bpy.data.armatures.new(shape.names[node.name])
        # bnode = bpy.data.objects.new(name=shape.names[node.name], object_data=amt)
        bpy.ops.object.armature_add()
        bnode = context.object
        bnode.name = shape.names[node.name]
        bnode.select = False
        bnode.location = mathutils.Vector(shape.default_translations[i])

        bnode.rotation_mode = "QUATERNION"
        bnode.rotation_quaternion = mathutils.Quaternion((
            -shape.default_rotations[i][3],
            shape.default_rotations[i][0],
            shape.default_rotations[i][1],
            shape.default_rotations[i][2]
        ))

        # context.scene.objects.link(bnode)
        nodes.append((node, bnode)) # Store pair for later

    # Now set all the parents appropriately
    for node, bnode in nodes:
        if node.parent != -1:
            bnode.parent = nodes[node.parent][1]

    # Then put objects in the armatures
    for obj in shape.objects:
        if obj.numMeshes != 1: # TODO: Really need to support non-1:1 objects! A lot of models use it.
            print("Skipping object {} with {} meshes (only 1 mesh per object is supported)".format(
                shape.names[obj.name], obj.numMeshes))
            continue

        mesh = shape.meshes[obj.firstMesh]

        if mesh.type != MeshType.Standard: # TODO: Support other types too...
            #if mesh.type != MeshType.None: # No need to warn for this, it's intended..
            print("{} is a {} mesh, skipping due to lack of support".format(
                shape.names[obj.name], mesh.type.name))
            continue

        faces = []

        # Go through all the primitives in the mesh and convert them to pydata faces
        for prim in mesh.primitives:
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

        # Now add the Mesh object and parent it to the armature if any
        bmesh = bpy.data.meshes.new(name="Mesh")
        bmesh.from_pydata(mesh.verts, [], faces)
        bmesh.update()
        bobj = bpy.data.objects.new(name=shape.names[obj.name], object_data=bmesh)
        context.scene.objects.link(bobj)
        if obj.node != -1:
            # bobj.parent = nodes[obj.node][1]
            node = nodes[obj.node][1]
            pose_bone = node.pose.bones[0]
            pose_obj = pose_bone.id_data
            matrix_final = pose_obj.matrix_world * pose_bone.matrix

            # bobj.location = node.matrix_world * node.location
            # bobj.rotation_quaternion = node.rotation_quaternion
            bobj.matrix_world = matrix_final

            bobj.select = True
            node.select = True
            context.scene.objects.active = node
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
            bobj.select = False
            node.select = False

        shown = (
            "HeadSkin", "chest", "Larm", "Lhand", "Rarm", "Rhand", "pants", "LShoe", "RShoe"
        )
        if shape.names[obj.name] not in shown:
            bobj.hide = True
            print("hiding " + shape.names[obj.name])

    return {"FINISHED"}
