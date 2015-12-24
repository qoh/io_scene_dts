import bpy, bmesh
from math import sqrt
from operator import attrgetter

from .DtsShape import DtsShape
from .DtsTypes import *
from .write_report import write_debug_report

import re
# re really isn't necessary. oh well.
re_lod_size = re.compile(r"(-?\d+)$")

def fail(operator, message):
    print("Error:", message)
    operator.report({"ERROR"}, message)
    return {"FINISHED"}

def save(operator, context, filepath,
         blank_material=True,
         force_flatshade=True,
         force_opaque=False,
         debug_report=True):
    scene = context.scene

    shape = DtsShape()

    poly_count = 0
    smin = [10e30, 10e30, 10e30]
    smax = [-10e30, -10e30, -10e30]

    material_lookup = {}
    blank_material_index = None

    print("Exporting scene to DTS")

    root_node = None
    root_node_index = None
    using_auto_root = False

    def get_auto_root():
        nonlocal root_node, root_node_index, using_auto_root

        if using_auto_root:
            return root_node, root_node_index

        print("Adding fallback root node...")
        if shape.nodes:
            # I feel like this won't work. The root node might have to be the first in the list.
            print("Warning: Fallback root node is not the first node created. This could go badly.")

        using_auto_root = True
        node = Node(shape.name("__auto_root__"))
        node_index = len(shape.nodes)
        shape.nodes.append(node)
        shape.default_translations.append(Point())
        shape.default_rotations.append(Quaternion())

        if root_node:
            assert root_node.parent == -1
            root_node.parent = node_index

        root_node = node
        root_node_index = node_index
        return node, node_index

    armature_nodes = {}
    scene_lods = {}
    scene_objects = {}
    pending_attachments = {}

    shape.smallest_detail_level = None

    scene_meshes = filter(lambda bobj: bobj.type == "MESH", scene.objects)
    scene_armatures = filter(lambda bobj: bobj.type == "ARMATURE", scene.objects)

    if "NodeOrder" in bpy.data.texts:
        order_list = bpy.data.texts["NodeOrder"].as_string().split("\n")
        order_dict = {name: i for i, name in enumerate(order_list)}

        scene_armatures = sorted(scene_armatures, key=lambda node: order_dict[node.name])

    # First, go through all armatures and create DTS nodes for them
    for armature in scene_armatures:
        parent = armature.parent

        if parent and parent.type != "ARMATURE":
            return fail(operator, "Armatures may only be parented to other armatures. '{}' is parented to a {}.".format(armature.name, parent.type))

        # Make DTS nodes for Blender armatures
        print("Creating DTS Node", armature.name)
        node = Node(shape.name(armature.name))
        node_index = len(shape.nodes)
        shape.nodes.append(node)
        armature_nodes[armature] = (node, node_index)

        shape.default_translations.append(Point(*armature.location))
        # Try to find a quaternion representation of the armature rotation
        # TODO: Handle more than quaternion & euler
        if armature.rotation_mode == "QUATERNION":
            rot = armature.rotation_quaternion
        else:
            rot = armature.rotation_euler.to_quaternion()
        # Weird representation difference -wxyz -> xyzw
        shape.default_rotations.append(Quaternion(rot[1], rot[2], rot[3], -rot[0]))

        # Try to parent all our children if they've already been added
        for child in armature.children:
            if child.type == "ARMATURE" and child in armature_nodes:
                assert armature_nodes[child][0].parent == 0 # This should throw if everything is correct
                armature_nodes[child][0].parent = node_index
                print("Parenting DTS Node {} to {}".format(child.name, armature.name))

        # If this node has a parent armature, try to parent our new node to it (or do so when we get to it, above)
        if parent:
            if parent in armature_nodes:
                node.parent = armature_nodes[parent][1]
                print("Parenting DTS Node {} to {}".format(armature.name, parent.name))
        # No parent; this is supposed to be a root node. Either make it the root or parent it to the auto root.
        elif root_node is None:
            root_node = node
            root_node_index = node_index
        else:
            # TODO: get rid of auto_root. it's nothing but trouble.
            node.parent = get_auto_root()[1]

    # Now that we have all the nodes, attach our fabled objects to them
    for bobj in scene_meshes:
        # TODO: do something about the mesh translation/rotation as well
        parent = bobj.parent

        if parent:
            if parent.type == "ARMATURE":
                attach_node = armature_nodes[parent][1]
            else:
                return fail(operator, "Meshes may only be parented to armatures. '{}' is parented to a {}.".format(bobj.name, parent.type))
        else:
            # shoo!
            attach_node = get_auto_root()[1]

        if bobj.users_group:
            if len(bobj.users_group) >= 2:
                print("Warning: Mesh {} is in multiple groups".format(bobj.name))

            lod_name = bobj.users_group[0].name
        else:
            lod_name = "detail32"

        if lod_name not in scene_lods:
            match = re_lod_size.search(lod_name)

            if match:
                lod_size = int(match.group(1))
            else:
                print("Warning: LOD {} does not end with a size, assuming size 32".format(lod_name))
                lod_size = 32

            if lod_size >= 0 and (shape.smallest_detail_level == None or lod_size < shape.smallest_detail_level):
                shape.smallest_detail_level = lod_size

            print("Creating LOD {} with size {}".format(lod_name, lod_size))
            scene_lods[lod_name] = DetailLevel(name=shape.name(lod_name), subshape=0, objectDetail=-1, size=lod_size, polyCount=0)
            shape.detail_levels.append(scene_lods[lod_name])

        name = bobj.name

        if name not in scene_objects:
            object = Object(shape.name(name), numMeshes=0, firstMesh=0, node=attach_node)
            object_index = len(shape.objects)
            shape.objects.append(object)
            shape.objectstates.append(ObjectState(1.0, 0, 0))
            scene_objects[name] = (object, {})

        if lod_name in scene_objects[name][1]:
            print("Warning: Multiple objects {} in LOD {}, ignoring...".format(name, lod_name))
        else:
            scene_objects[name][1][lod_name] = bobj

    # # For every object in the scene
    # for bobj in scene.objects:
    #     print(bobj.type, bobj.name)

    #     # Deal with this based on what it is
    #     # If it's something we can't handle, just skip it
    #     if bobj.type == "ARMATURE":
    #         parent = bobj.parent

    #         if parent and parent.type != "ARMATURE":
    #             return fail(operator, "Armatures may only be parented to other armatures. '{}' is parented to a {}.".format(bobj.name, parent.type))

    #         # Make DTS nodes for Blender armatures
    #         print("Creating DTS Node", bobj.name)
    #         node = Node(shape.name(bobj.name))
    #         node_index = len(shape.nodes)
    #         shape.nodes.append(node)
    #         armature_nodes[bobj] = (node, node_index)

    #         if bobj in pending_attachments:
    #             for object in pending_attachments[bobj]:
    #                 object.node = node_index
    #             del pending_attachments[bobj]

    #         shape.default_translations.append(Point(*bobj.location))
    #         # Try to find a quaternion representation of the armature rotation
    #         # TODO: Handle more than quaternion & euler
    #         if bobj.rotation_mode == "QUATERNION":
    #             rot = bobj.rotation_quaternion
    #         else:
    #             rot = bobj.rotation_euler.to_quaternion()
    #         # Weird representation difference -wxyz -> xyzw
    #         shape.default_rotations.append(Quaternion(rot[1], rot[2], rot[3], -rot[0]))

    #         # Try to parent all our children if they've already been added
    #         for child in bobj.children:
    #             if child.type == "ARMATURE" and child in armature_nodes:
    #                 assert armature_nodes[child][0].parent == 0 # This should throw if everything is correct
    #                 armature_nodes[child][0].parent = node_index
    #                 print("Parenting DTS Node {} to {}".format(child.name, bobj.name))

    #         # If this node has a parent armature, try to parent our new node to it (or do so when we get to it, above)
    #         if parent:
    #             if parent in armature_nodes:
    #                 node.parent = armature_nodes[parent][1]
    #                 print("Parenting DTS Node {} to {}".format(bobj.name, parent.name))
    #         # No parent; this is supposed to be a root node. Either make it the root or parent it to the auto root.
    #         elif root_node is None:
    #             root_node = node
    #             root_node_index = node_index
    #         else:
    #             node.parent = get_auto_root()[1]
    #     elif bobj.type == "MESH":
    #         # TODO: do something about the mesh translation/rotation as well
    #         parent = bobj.parent

    #         if parent:
    #             if parent.type == "ARMATURE":
    #                 if parent in armature_nodes:
    #                     attach_node = armature_nodes[parent][1]
    #                 else:
    #                     attach_node = -1
    #             else:
    #                 return fail(operator, "Meshes may only be parented to armatures. '{}' is parented to a {}.".format(bobj.name, parent.type))
    #         else:
    #             attach_node = get_auto_root()[1]

    #         if bobj.users_group:
    #             if len(bobj.users_group) >= 2:
    #                 print("Warning: Mesh {} is in multiple groups".format(bobj.name))

    #             lod_name = bobj.users_group[0].name
    #         else:
    #             lod_name = "detail32"

    #         if lod_name not in scene_lods:
    #             match = re_lod_size.search(lod_name)

    #             if match:
    #                 lod_size = int(match.group(1))
    #             else:
    #                 print("Warning: LOD {} does not end with a size, assuming size 32".format(lod_name))
    #                 lod_size = 32

    #             if lod_size >= 0 and (shape.smallest_detail_level == None or lod_size < shape.smallest_detail_level):
    #                 shape.smallest_detail_level = lod_size

    #             print("Creating LOD {} with size {}".format(lod_name, lod_size))
    #             scene_lods[lod_name] = DetailLevel(name=shape.name(lod_name), subshape=0, objectDetail=-1, size=lod_size, polyCount=0)
    #             shape.detail_levels.append(scene_lods[lod_name])

    #         name = bobj.name

    #         if name not in scene_objects:
    #             object = Object(shape.name(name), numMeshes=0, firstMesh=0, node=attach_node)
    #             object_index = len(shape.objects)
    #             shape.objects.append(object)
    #             shape.objectstates.append(ObjectState(1.0, 0, 0))

    #             if attach_node == -1:
    #                 if parent in pending_attachments:
    #                     pending_attachments[parent].append(object)
    #                 else:
    #                     pending_attachments[parent] = [object]

    #             scene_objects[name] = (object, {})

    #         if lod_name in scene_objects[name][1]:
    #             print("Warning: Multiple objects {} in LOD {}, ignoring...".format(name, lod_name))
    #         else:
    #             scene_objects[name][1][lod_name] = bobj
    #     else:
    #         print("Skipping {} {}".format(bobj.type, bobj.name))

    # assert not pending_attachments

    # Try to sort the detail levels? Maybe that fixes things?
    shape.detail_levels.sort(key=attrgetter("size"), reverse=True)

    print("Detail levels:")

    for i, lod in enumerate(shape.detail_levels):
        lod.objectDetail = i # this isn't the right place for this
        print(i, shape.names[lod.name])

    print("Adding meshes to objects...")

    for object, lods in scene_objects.values():
        print(shape.names[object.name])
        object.firstMesh = len(shape.meshes)
        print("firstMesh =", object.firstMesh)

        for i, lod in enumerate(reversed(shape.detail_levels)):
            if shape.names[lod.name] in lods:
                object.numMeshes = len(shape.detail_levels) - i
                print("numMeshes =", object.numMeshes)
                break
        else:
            object.numMeshes = 0
            print("numMeshes = 0")
            continue

        for i in range(object.numMeshes):
            lod = shape.detail_levels[i]
            lod_name = shape.names[lod.name]

            if lod_name in lods:
                print("Generating mesh for object {} in LOD {}".format(shape.names[object.name], lod_name))
                bobj = lods[lod_name]

                #########################
                ### Welcome to complexity

                if force_flatshade:
                    print("  edge split")
                    # Hack in flatshading
                    scene.objects.active = bobj
                    bpy.ops.object.modifier_add(type="EDGE_SPLIT")
                    bobj.modifiers[-1].split_angle = 0

                print("  bmesh triangulation")
                mesh = bobj.to_mesh(scene, force_flatshade, "PREVIEW")
                bm = bmesh.new()
                bm.from_mesh(mesh)
                bmesh.ops.triangulate(bm, faces=bm.faces)
                bm.to_mesh(mesh)
                bm.free()

                if force_flatshade:
                    # Clean up our hack
                    bpy.ops.object.modifier_remove(modifier=bobj.modifiers[-1].name)

                dmesh = Mesh()
                shape.meshes.append(dmesh)

                for vertex in mesh.vertices:
                    dmesh.verts.append(Point(*vertex.co))
                    dmesh.normals.append(Point(*vertex.normal))
                    dmesh.enormals.append(0)
                    dmesh.tverts.append(Point2D(0, 0))

                for polygon in mesh.polygons:
                    lod.polyCount += 1
                    dmesh.indices.append(polygon.vertices[2])
                    dmesh.indices.append(polygon.vertices[1])
                    dmesh.indices.append(polygon.vertices[0])

                dmesh.bounds = dmesh.calculate_bounds(Point(), Quaternion())
                dmesh.center = Point(
                    (dmesh.bounds.min.x + dmesh.bounds.max.x) / 2,
                    (dmesh.bounds.min.y + dmesh.bounds.max.y) / 2,
                    (dmesh.bounds.min.z + dmesh.bounds.max.z) / 2)
                dmesh.radius = dmesh.calculate_radius(Point(), Quaternion(), dmesh.center)

                flags = Primitive.Triangles | Primitive.Indexed

                # TODO: don't apply any materials to collision meshes
                if len(mesh.materials) > 0:
                    # TODO: per-face material exporting
                    print("  processing materials")
                    material = mesh.materials[0]
                    material_index = material_lookup.get(material)

                    if material_index == None:
                        print("    creating material for blender mat " + material.name)
                        material_index = len(shape.materials)
                        material_lookup[material] = material_index
                        mat_flags = Material.SWrap | Material.TWrap | Material.NeverEnvMap

                        if material.use_transparency and not force_opaque:
                            mat_flags |= Material.Translucent
                        if material.use_shadeless:
                            mat_flags |= Material.SelfIlluminating
                        if "additive" in material:
                            mat_flags |= Material.Additive
                        if "subtractive" in material:
                            mat_flags |= Material.Additive

                        shape.materials.append(Material(name=material.name, flags=mat_flags))

                    flags |= material_index & Primitive.MaterialMask
                else:
                    if blank_material:
                        if blank_material_index == None:
                            blank_material_index = len(shape.materials)
                            shape.materials.append(Material(name="blank", flags=Material.SWrap | Material.TWrap | Material.NeverEnvMap, reflectanceMap=0))
                        flags |= blank_material_index & Primitive.MaterialMask
                    else:
                        flags |= Primitive.NoMaterial

                bpy.data.meshes.remove(mesh)

                dmesh.primitives.append(Primitive(0, len(dmesh.indices), flags))
                dmesh.vertsPerFrame = len(dmesh.verts)

                ### Nobody leaves Hotel California
            else:
                print("Adding Null mesh for object {} in LOD {}".format(shape.names[object.name], lod_name))
                shape.meshes.append(Mesh(MeshType.Null))

    # Try to stay sane
    # for node in shape.nodes:
    #     node.firstObject = node.child = node.sibling = -1

    # for i, node in enumerate(shape.nodes):
    #     if node.parent >= 0:
    #         if shape.nodes[node.parent].child < 0:
    #             shape.nodes[node.parent].child = i
    #         else:
    #             child = shape.nodes[node.parent].child
    #             while shape.nodes[child].sibling >= 0:
    #                 child = shape.nodes[child].sibling
    #             shape.nodes[child].sibling = i

    # for i, object in enumerate(shape.objects):
    #     object.sibling = -1
    #     object.firstDecal = -1

    #     if object.node >= 0:
    #         if shape.nodes[object.node].firstObject < 0:
    #             shape.nodes[object.node].firstObject = i
    #         else:
    #             objectIndex = shape.nodes[object.node].firstObject
    #             while shape.objects[objectIndex].nextSibling >= 0:
    #                 objectIndex = shape.objects[objectIndex].nextSibling
    #             shape.objects[objectIndex].sibling = i

    print("Creating subshape with " + str(len(shape.nodes)) + " nodes and " + str(len(shape.objects)) + " objects")
    shape.subshapes.append(Subshape(firstNode=0, firstObject=0, firstDecal=0, numNodes=len(shape.nodes), numObjects=len(shape.objects), numDecals=0))

    # Figure out all the things
    print("Computing bounds")
    shape.smallest_size = None
    shape.smallest_detail_level = None

    for i, lod in enumerate(shape.detail_levels):
        if shape.smallest_size == None or (lod.size >= 0 and lod.size < shape.smallest_size):
            shape.smallest_size = lod.size
            shape.smallest_detail_level = i

    shape.bounds = Box(
        Point( 10e30,  10e30,  10e30),
        Point(-10e30, -10e30, -10e30))
    shape.radius = 0
    shape.radius_tube = 0

    for i, obj in enumerate(shape.objects):
        trans, rot = shape.get_world(obj.node)

        for j in range(0, obj.numMeshes):
            mesh = shape.meshes[obj.firstMesh + j]

            if mesh.type == MeshType.Null:
                continue

            bounds = mesh.calculate_bounds(trans, rot)

            shape.radius = max(shape.radius, mesh.calculate_radius(trans, rot, shape.center))
            shape.radius_tube = max(shape.radius_tube, mesh.calculate_radius_tube(trans, rot, shape.center))

            shape.bounds.min.x = min(shape.bounds.min.x, bounds.min.x)
            shape.bounds.min.y = min(shape.bounds.min.y, bounds.min.y)
            shape.bounds.min.z = min(shape.bounds.min.z, bounds.min.z)
            shape.bounds.max.x = max(shape.bounds.max.x, bounds.max.x)
            shape.bounds.max.y = max(shape.bounds.max.y, bounds.max.y)
            shape.bounds.max.z = max(shape.bounds.max.z, bounds.max.z)

    shape.center = Point(
        (shape.bounds.min.x + shape.bounds.max.x) / 2,
        (shape.bounds.min.y + shape.bounds.max.y) / 2,
        (shape.bounds.min.z + shape.bounds.max.z) / 2)

    if debug_report:
        write_debug_report(filepath + ".txt", shape)

    with open(filepath, "wb") as fd:
        shape.save(fd)

    return {"FINISHED"}
