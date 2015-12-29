import bpy, bmesh
from mathutils import Vector
from math import sqrt
from operator import attrgetter
from itertools import groupby

from .DtsShape import DtsShape
from .DtsTypes import *
from .write_report import write_debug_report

import re
# re really isn't necessary. oh well.
re_lod_size = re.compile(r"(-?\d+)$")
re_lod_dup_name = re.compile(r"\.LOD\d{3}$")
common_col_name = re.compile(r"^(LOS)?[cC]ol-?\d+$")
default_bone_name = re.compile(r"^Bone(\.\d+)?$")

def fail(operator, message):
    print("Error:", message)
    operator.report({"ERROR"}, message)
    return {"FINISHED"}

def export_material(mat, shape):
    # print("Exporting material", mat.name)

    material_index = len(shape.materials)
    flags = 0

    if mat.use_shadeless:
        flags |= Material.SelfIlluminating
    if mat.use_transparency:
        flags |= Material.Translucent
        default_mode = "additive"
    else:
        default_mode = "none"

    mode = mat.get("blendMode", default_mode)
    if mode == "additive":
        flags |= Material.Additive
    elif mode == "subtractive":
        flags |= Material.Subtractive
    elif mode == "both":
        flags |= Material.Additive | Material.Subtractive
    elif mode != "none":
        print("Warning: Invalid blendMode '{}' on material '{}'".format(mode, mat.name))

    if not mat.get("noSWrap"):
        flags |= Material.SWrap
    if not mat.get("noTWrap"):
        flags |= Material.TWrap
    if not mat.get("envMap"):
        flags |= Material.NeverEnvMap
    if not mat.get("mipMap"):
        flags |= Material.NoMipMap

    if mat.get("ifl"):
        flags |= Material.IFLMaterial

        # TODO: keep IFL materials in a table by name?
        # what would duplicates do?

        ifl_index = len(shape.iflmaterials)
        ifl = IflMaterial(
            name=shape.name(mat["iflName"]),
            slot=material_index,
            firstFrame=mat.get("iflFirstFrame", 0),
            numFrames=mat.get("iflNumFrames", 0),
            time=mat.get("iflTime", 0))
        shape.iflmaterials.append(ifl)

    material = Material(name=mat.name, flags=flags)
    shape.materials.append(material)

    return material_index

def rotation_from_ob(ob):
    if ob.rotation_mode == "QUATERNION":
        r = ob.rotation_quaternion
    elif ob.rotation_mode == "AXIS_ANGLE":
        print("Warning: '{}' uses unsupported axis angle rotation".format(ob.name))
        r = ob.rotation_quaternion # ob.rotation_axis_angle
    else:
        r = ob.rotation_euler.to_quaternion()
    return Quaternion(r[1], r[2], r[3], -r[0])

def eksi_bone_zone(shape, bones, parent):
    for bone in bones:
        node = Node(shape.name(bone.name), parent)
        node.translation = bone.head
        node.rotation = Quaternion()
        shape.nodes.append(node)

def export_all_nodes(lookup, shape, obs, parent=-1):
    for ob in obs:
        if ob.type == "ARMATURE" or ob.type == "EMPTY":
            if ob.scale != Vector((1,1,1)):
                print("Warning: '{}' uses scale, which cannot be export to DTS nodes".format(ob.name))

            node = Node(shape.name(ob.name), parent)
            node.translation = ob.location
            node.rotation = rotation_from_ob(ob)
            shape.nodes.append(node)
            lookup[ob] = node

            if ob.type == "ARMATURE":
                bones = ob.data.bones
                if len(bones) >= 2:
                    print("Warning: Exporting bones in armature '{}' as nodes. Use child armatures instead.".format(ob.name))
                    eksi_bone_zone(shape, bones, node)

            export_all_nodes(lookup, shape, ob.children, node)

def save(operator, context, filepath,
         blank_material=True,
         debug_report=True):
    print("Exporting scene to DTS")

    scene = context.scene
    shape = DtsShape()

    blank_material_index = None
    auto_root_index = None

    # Create a DTS node for every armature/empty in the scene
    node_lookup = {}
    export_all_nodes(node_lookup, shape, filter(lambda o: not o.parent, scene.objects))

    # Figure out if we should create our own root node
    if "NodeOrder" in bpy.data.texts:
        order = bpy.data.texts["NodeOrder"].as_string().split("\n")
        order_key = {name: i for i, name in enumerate(order)}

        shape.nodes = list(sorted(shape.nodes, key=lambda n: order_key[shape.names[n.name]]))

    node_indices = {}

    for index, node in enumerate(shape.nodes):
        if not isinstance(node.parent, int):
            node.parent = shape.nodes.index(node.parent)
        node_indices[node] = index
        shape.default_translations.append(node.translation)
        shape.default_rotations.append(node.rotation)

    node_lookup = {ob: node_indices[node] for ob, node in node_lookup.items()}

    # Now that we have all the nodes, attach our fabled objects to them
    scene_lods = {}
    scene_objects = {}

    for bobj in scene.objects:
        if bobj.type != "MESH":
            continue

        if bobj.users_group:
            if len(bobj.users_group) > 1:
                print("Warning: Mesh {} is in multiple groups".format(bobj.name))

            lod_name = bobj.users_group[0].name
        elif common_col_name.match(bobj.name):
            lod_name = "collision-1"
        else:
            lod_name = "detail32"

        if lod_name == "__ignore__":
            continue

        if bobj.location != Vector((0,0,0)) or bobj.scale != Vector((1,1,1)): # TODO: rotation
            # TODO: apply transform to vertices instead maybe?
            print("Warning: Mesh '{}' uses a local transform which cannot be exported to DTS".format(bobj.name))

        if bobj.parent:
            if bobj.parent not in node_lookup:
                print("Warning: Mesh '{}' has a '{}' parent, ignoring".format(bobj.name, bobj.parent.type))
                continue

            attach_node = node_lookup[bobj.parent]
        else:
            print("Warning: Mesh '{}' has no parent".format(bobj.name))

            if not auto_root_index:
                if "NodeOrder" in bpy.data.texts and "__auto_root__" not in order_key:
                    return fail(operator, "Root meshes found, but NodeOrder has no __auto_root__")

                auto_root_index = len(shape.nodes)
                shape.nodes.append(Node(shape.name("__auto_root__")))
                shape.default_rotations.append(Quaternion())
                shape.default_translations.append(Vector())

            attach_node = auto_root_index

        if lod_name not in scene_lods:
            match = re_lod_size.search(lod_name)

            if match:
                lod_size = int(match.group(1))
            else:
                print("Warning: LOD '{}' does not end with a size, assuming size 32".format(lod_name))
                lod_size = 32 # setting?

            print("Creating LOD '{}' (size {})".format(lod_name, lod_size))
            scene_lods[lod_name] = DetailLevel(name=shape.name(lod_name), subshape=0, objectDetail=-1, size=lod_size)
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

    # Sort detail levels
    shape.detail_levels.sort(key=attrgetter("size"), reverse=True)

    for i, lod in enumerate(shape.detail_levels):
        lod.objectDetail = i # this isn't the right place for this

    print("Adding meshes to objects...")

    material_table = {}

    for object, lods in scene_objects.values():
        object.firstMesh = len(shape.meshes)

        for i, lod in enumerate(reversed(shape.detail_levels)):
            if shape.names[lod.name] in lods:
                object.numMeshes = len(shape.detail_levels) - i
                break
        else:
            object.numMeshes = 0
            continue

        # if object.numMeshes == 0:
        #     print("Nothing to be done for object {}".format(shape.names[object.name]))

        for i in range(object.numMeshes):
            lod = shape.detail_levels[i]
            lod_name = shape.names[lod.name]

            if lod_name in lods:
                print("Exporting mesh '{}' (LOD '{}')".format(shape.names[object.name], lod_name))
                bobj = lods[lod_name]

                #########################
                ### Welcome to complexity

                mesh = bobj.to_mesh(scene, False, "PREVIEW")
                bm = bmesh.new()
                bm.from_mesh(mesh)
                bmesh.ops.triangulate(bm, faces=bm.faces)
                bm.to_mesh(mesh)
                bm.free()

                # This is the danger zone
                # Data from down here may not stay around!

                dmesh = Mesh()
                shape.meshes.append(dmesh)

                for vertex in mesh.vertices:
                    dmesh.verts.append(vertex.co.copy())
                    dmesh.normals.append(vertex.normal.copy())
                    dmesh.enormals.append(0)
                    dmesh.tverts.append(Vector((0, 0)))

                got_tvert = set()

                dmesh.bounds = dmesh.calculate_bounds(Vector(), Quaternion())
                dmesh.center = Vector((
                    (dmesh.bounds.min.x + dmesh.bounds.max.x) / 2,
                    (dmesh.bounds.min.y + dmesh.bounds.max.y) / 2,
                    (dmesh.bounds.min.z + dmesh.bounds.max.z) / 2))
                dmesh.radius = dmesh.calculate_radius(Vector(), Quaternion(), dmesh.center)

                # Group all materials by their material_index
                key = attrgetter("material_index")
                grouped_polys = groupby(sorted(mesh.polygons, key=key), key=key)
                grouped_polys = tuple(map(lambda t: (t[0], tuple(t[1])), grouped_polys))

                # Create a primitive from each group
                for material_index, polys in grouped_polys:
                    flags = Primitive.Triangles | Primitive.Indexed

                    if mesh.materials:
                        bmat = mesh.materials[material_index]

                        if bmat not in material_table:
                            material_table[bmat] = export_material(bmat, shape)

                        flags |= material_table[bmat] & Primitive.MaterialMask
                    elif blank_material:
                        if blank_material_index is None:
                            blank_material_index = len(shape.materials)
                            shape.materials.append(Material(name="blank",
                                flags=Material.SWrap | Material.TWrap | Material.NeverEnvMap))

                        flags |= blank_material_index & Primitive.MaterialMask
                    else:
                        flags |= Primitive.NoMaterial

                    firstElement = len(dmesh.indices)

                    for poly in polys:
                        if mesh.uv_layers:
                            uv_layer = mesh.uv_layers[0].data
                        else:
                            uv_layer = None

                        needs_split = False
                        use_face_normal = not poly.use_smooth

                        # TODO: add UVs to needs_split consideration
                        if not poly.use_smooth:
                            for vert_index in poly.vertices:
                                if mesh.vertices[vert_index].normal != poly.normal:
                                    needs_split = True
                                    break

                        if needs_split: # TODO: verify that this works properly
                            vertices = tuple(range(len(dmesh.verts), len(dmesh.verts) + len(poly.vertices)))

                            for vert_index, loop_index in zip(poly.vertices, poly.loop_indices):
                                vert = mesh.vertices[vert_index]
                                dmesh.verts.append(vert.co.copy())
                                if use_face_normal:
                                    dmesh.normals.append(poly.normal.copy())
                                else:
                                    dmesh.normals.append(vert.normal.copy())
                                dmesh.enormals.append(0)
                                if uv_layer:
                                    uv = uv_layer[loop_index].uv
                                    dmesh.tverts.append(Vector((uv.x, 1 - uv.y)))
                                else:
                                    dmesh.tverts.append(Vector((0, 0)))
                        else:
                            vertices = poly.vertices

                            if uv_layer:
                                for vert_index, loop_index in zip(vertices, poly.loop_indices):
                                    # TODO: split on multiple UV coords
                                    uv = uv_layer[loop_index].uv
                                    dmesh.tverts[vert_index] = Vector((uv.x, 1 - uv.y))

                        dmesh.indices.append(vertices[2])
                        dmesh.indices.append(vertices[1])
                        dmesh.indices.append(vertices[0])

                    numElements = len(dmesh.indices) - firstElement
                    dmesh.primitives.append(Primitive(firstElement, numElements, flags))

                bpy.data.meshes.remove(mesh) # RIP!

                # ??? ? ?? ???? ??? ?
                dmesh.vertsPerFrame = len(dmesh.verts)

                ### Nobody leaves Hotel California
            else:
                # print("Adding Null mesh for object {} in LOD {}".format(shape.names[object.name], lod_name))
                shape.meshes.append(Mesh(MeshType.Null))

    print("Creating subshape with " + str(len(shape.nodes)) + " nodes and " + str(len(shape.objects)) + " objects")
    shape.subshapes.append(Subshape(firstNode=0, firstObject=0, firstDecal=0, numNodes=len(shape.nodes), numObjects=len(shape.objects), numDecals=0))

    # Figure out all the things
    print("Computing bounds")
    # shape.smallest_size = None
    # shape.smallest_detail_level = -1
    #
    # for i, lod in enumerate(shape.detail_levels):
    #     if lod.size >= 0 and (shape.smallest_size == None or lod.size < shape.smallest_size):
    #         shape.smallest_size = lod.size
    #         shape.smallest_detail_level = i

    shape.bounds = Box(
        Vector(( 10e30,  10e30,  10e30)),
        Vector((-10e30, -10e30, -10e30)))

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

    shape.center = Vector((
        (shape.bounds.min.x + shape.bounds.max.x) / 2,
        (shape.bounds.min.y + shape.bounds.max.y) / 2,
        (shape.bounds.min.z + shape.bounds.max.z) / 2))

    if debug_report:
        print("Writing debug report")
        write_debug_report(filepath + ".txt", shape)

    shape.verify()

    with open(filepath, "wb") as fd:
        shape.save(fd)

    return {"FINISHED"}
