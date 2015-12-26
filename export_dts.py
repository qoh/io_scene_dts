import bpy, bmesh
from math import sqrt
from operator import attrgetter
from itertools import groupby

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

def create_blank_material():
    return Material(name="blank", flags=Material.SWrap | Material.TWrap | Material.NeverEnvMap, reflectanceMap=0)

def export_material(mat, shape):
    print("Exporting material", mat.name)

    material_index = len(shape.materials)
    flags = 0

    if mat.use_transparency:
        flags |= Material.Translucent
    if mat.use_shadeless:
        flags |= Material.SelfIlluminating
    if mat.get("additive"):
        flags |= Material.Additive
    if mat.get("subtractive"):
        flags |= Material.Subtractive
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

def get_parent_armature(ob):
    parent = ob.parent
    while parent:
        if parent.type == "ARMATURE":
            return parent
        parent = parent.parent

def get_deep_children(search, obs):
    for ob in obs:
        if ob.type == search:
            yield ob
        else:
            yield from get_deep_children(search, ob.children)

def explore_armatures(lookup, shape, obs, parent=-1):
    for ob in obs:
        if ob.type == "ARMATURE":
            print("Exporting armature", ob.name)

            node = Node(shape.name(ob.name), parent)
            node.translation = Point(*ob.location)

            # Try to find a quaternion representation of the armature rotation
            # TODO: Handle more than quaternion & euler
            if ob.rotation_mode == "QUATERNION":
                rot = ob.rotation_quaternion
            else:
                rot = ob.rotation_euler.to_quaternion()

            # Weird representation difference -wxyz -> xyzw
            node.rotation = Quaternion(rot[1], rot[2], rot[3], -rot[0])

            shape.nodes.append(node)
            lookup[ob] = next_parent = node
        else:
            next_parent = parent

        explore_armatures(lookup, shape, ob.children, next_parent)

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

    armature_nodes = {}
    scene_lods = {}
    scene_objects = {}
    pending_attachments = {}

    shape.smallest_detail_level = None

    scene_meshes = filter(lambda bobj: bobj.type == "MESH", scene.objects)
    scene_armatures = filter(lambda bobj: bobj.type == "ARMATURE", scene.objects)

    lookup = {}

    root_scene = tuple(filter(lambda ob: not ob.parent, scene.objects))

    # Create a DTS node for every armature in the scene
    explore_armatures(lookup, shape, root_scene)

    root_nodes = tuple(filter(lambda n: n.parent == -1, shape.nodes))
    root_objects = tuple(filter(lambda n: get_parent_armature(n) is None, get_deep_children("MESH", root_scene)))

    print("# of root nodes", len(root_nodes))
    print("# of root objects", len(root_objects))

    # Figure out if we should create our own root node
    if len(root_nodes) > 1 or root_objects:
        print("Auto root is needed")

        if "NodeOrder" in bpy.data.texts:
            return fail(operator, "Auto root with specified NodeOrder")

        auto_root = Node(shape.name("__auto_root__"))
        auto_root.translation = Point()
        auto_root.rotation = Quaternion()
        shape.nodes.insert(0, auto_root)

        for dangling_node in root_nodes:
            dangling_node.parent = auto_root
    elif "NodeOrder" in bpy.data.texts:
        order = bpy.data.texts["NodeOrder"].as_string().split("\n")
        key = {name: i for i, name in enumerate(order)}

        shape.nodes = list(sorted(shape.nodes, key=lambda n: key[n.name]))

    node_indices = {}

    for index, node in enumerate(shape.nodes):
        if not isinstance(node.parent, int):
            node.parent = shape.nodes.index(node.parent)
        node_indices[node] = index
        shape.default_translations.append(node.translation)
        shape.default_rotations.append(node.rotation)

    lookup = {ob: node_indices[node] for ob, node in lookup.items()}

    # Now that we have all the nodes, attach our fabled objects to them
    for bobj in scene_meshes:
        # TODO: do something about the mesh translation/rotation as well
        parent = get_parent_armature(bobj)
        # parent = bobj.parent

        if parent:
            attach_node = lookup[parent]
        else:
            attach_node = 0 # 0 should be __auto_root__ if dangling
                            # perhaps a good idea to assert here?

        if bobj.users_group:
            if len(bobj.users_group) >= 2:
                print("Warning: Mesh {} is in multiple groups".format(bobj.name))

            lod_name = bobj.users_group[0].name
        else:
            lod_name = "detail32" # setting?

        if lod_name not in scene_lods:
            match = re_lod_size.search(lod_name)

            if match:
                lod_size = int(match.group(1))
            else:
                print("Warning: LOD {} does not end with a size, assuming size 32".format(lod_name))
                lod_size = 32 # setting?

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

    # Try to sort the detail levels? Maybe that fixes things?
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

        if object.numMeshes == 0:
            print("Nothing to be done for object {}".format(shape.names[object.name]))

        for i in range(object.numMeshes):
            lod = shape.detail_levels[i]
            lod_name = shape.names[lod.name]

            if lod_name in lods:
                print("Adding mesh for object {} in LOD {}".format(shape.names[object.name], lod_name))
                bobj = lods[lod_name]

                #########################
                ### Welcome to complexity

                if force_flatshade:
                    print("  edge split")
                    # Hack in flatshading
                    scene.objects.active = bobj
                    bpy.ops.object.modifier_add(type="EDGE_SPLIT")
                    bobj.modifiers[-1].split_angle = 0

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

                got_tvert = set()

                dmesh.bounds = dmesh.calculate_bounds(Point(), Quaternion())
                dmesh.center = Point(
                    (dmesh.bounds.min.x + dmesh.bounds.max.x) / 2,
                    (dmesh.bounds.min.y + dmesh.bounds.max.y) / 2,
                    (dmesh.bounds.min.z + dmesh.bounds.max.z) / 2)
                dmesh.radius = dmesh.calculate_radius(Point(), Quaternion(), dmesh.center)

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
                    else:
                        # TODO: re-add blank materials
                        flags |= Primitive.NoMaterial

                    lod.polyCount += len(polys)

                    firstElement = len(dmesh.indices)

                    for poly in polys:
                        if mesh.uv_layers:
                            data = mesh.uv_layers[0].data

                            for vert_index, loop_index in zip(poly.vertices, poly.loop_indices):
                                # if vert_index in got_tvert:
                                #     print("Warning: Multiple tverts for", vert_index)

                                uv = data[loop_index].uv
                                dmesh.tverts[vert_index] = Point2D(uv.x, 1 - uv.y)
                                # got_tvert.add(vert_index)

                        dmesh.indices.append(poly.vertices[2])
                        dmesh.indices.append(poly.vertices[1])
                        dmesh.indices.append(poly.vertices[0])

                    numElements = len(dmesh.indices) - firstElement
                    dmesh.primitives.append(Primitive(firstElement, numElements, flags))

                bpy.data.meshes.remove(mesh)

                dmesh.vertsPerFrame = len(dmesh.verts)

                ### Nobody leaves Hotel California
            else:
                print("Adding Null mesh for object {} in LOD {}".format(shape.names[object.name], lod_name))
                shape.meshes.append(Mesh(MeshType.Null))

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
        print("Writing debug report")
        write_debug_report(filepath + ".txt", shape)

    shape.verify()

    with open(filepath, "wb") as fd:
        shape.save(fd)

    return {"FINISHED"}
