import bpy, bmesh, os
from math import sqrt, pi
from operator import attrgetter
from itertools import groupby

from .DtsShape import DtsShape
from .DtsTypes import *
from .write_report import write_debug_report
from .util import resolve_texture, default_materials

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

def undup_name(n):
    return n.split("#", 1)[0]

def linearrgb_to_srgb(c):
    if c < 0.0031308:
        if c < 0:
            return 0
        else:
            return c * 12.92
    else:
        return 1.055 * (c ** (1.0 / 2.4)) - 0.055

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

    material = Material(name=undup_name(mat.name), flags=flags)
    material.bl_mat = mat

    if "texture" in mat:
      material.name = mat["texture"]

    shape.materials.append(material)

    return material_index

def seq_float_eq(a, b):
    return all(abs(i - j) < 0.000001 for i, j in zip(a, b))

def export_all_nodes(lookup, shape, obs, parent=-1):
    for ob in obs:
        # if ob.type == "ARMATURE" or ob.type == "EMPTY":
        # Armature nodes disabled. What could go wrong?
        if ob.type == "EMPTY":
            loc, rot, scale = ob.matrix_local.decompose()

            if not seq_float_eq((1, 1, 1), scale):
                print("Warning: '{}' uses scale, which cannot be exported to DTS nodes".format(ob.name))

            if "name" in ob:
                name = ob["name"]
            else:
                name = undup_name(ob.name)

            node = Node(shape.name(name), parent)
            node.bl_ob = ob
            node.translation = loc
            node.rotation = rot
            shape.nodes.append(node)
            lookup[ob] = node

            export_all_nodes(lookup, shape, ob.children, node)

def evaluate_all(curves, frame):
    return tuple(map(lambda c: c.evaluate(frame), curves))

def array_from_fcurves(curves, data_path, array_size):
    found = False
    array = [None] * array_size

    for curve in curves:
        if curve.data_path == data_path and curve.array_index != -1:
            array[curve.array_index] = curve
            found = True

    if found:
        return tuple(array)

def fcurves_keyframe_in_range(curves, start, end):
    for curve in curves:
        for keyframe in curve.keyframe_points:
            frame = keyframe.co[0]
            if frame >= start and frame <= end:
                return True

    return False

def transform_co(ob, co):
    return ob.matrix_local * co

def transform_normal(ob, normal):
    return (ob.matrix_local.to_3x3() * normal).normalized()

def save(operator, context, filepath,
         blank_material=True,
         generate_texture="disabled",
         apply_modifiers=True,
         transform_mesh=True,
         debug_report=False):
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

        try:
            shape.nodes = list(sorted(shape.nodes, key=lambda n: order_key[shape.names[n.name]]))
        except KeyError as e:
            return fail(operator, "Node '{}' is missing from the 'NodeOrder' text block. This means that you may have added nodes to a skeleton when you shouldn't have, or that you forgot to remove the 'NodeOrder' text block. It is automatically created by the \"Import node order\" option when importing a DTS file. Perhaps you forgot to press Ctrl+N after you imported?".format(e.args[0]))

        shape_node_names = set(map(lambda n: shape.names[n.name], shape.nodes))
        missing_nodes = tuple(filter(lambda n: n not in shape_node_names, order))

        if missing_nodes:
            return fail(operator, "The following nodes were found in the 'NodeOrder' text block but do not exist in the shape. This means that you may have removed nodes from a skeleton when you shouldn't have, or that you forgot to remove the 'NodeOrder' text block:\n{}".format(", ".join(missing_nodes)))

    node_indices = {}

    for index, node in enumerate(shape.nodes):
        if not isinstance(node.parent, int):
            node.parent = shape.nodes.index(node.parent)
        node_indices[node] = index
        shape.default_translations.append(node.translation)
        shape.default_rotations.append(node.rotation)

    node_lookup = {ob: node_indices[node] for ob, node in node_lookup.items()}
    animated_nodes = []

    for node in shape.nodes:
        data = node.bl_ob.animation_data
        if data and data.action and len(data.action.fcurves):
            animated_nodes.append(node.bl_ob)

    # Now that we have all the nodes, attach our fabled objects to them
    scene_lods = {}
    scene_objects = {}

    bounds_ob = None

    for bobj in scene.objects:
        if bobj.type != "MESH":
            continue

        if bobj.name.lower() == "bounds":
            if bounds_ob:
                print("Warning: Multiple 'bounds' objects found - check capitalization")
            bounds_ob = bobj
            continue

        if "name" in bobj:
            name = bobj["name"]
        else:
            name = undup_name(bobj.name)

        if bobj.users_group:
            if len(bobj.users_group) > 1:
                print("Warning: Mesh {} is in multiple groups".format(bobj.name))

            lod_name = bobj.users_group[0].name
        elif common_col_name.match(name):
            lod_name = "collision-1"
        else:
            lod_name = "detail32"

        if lod_name == "__ignore__":
            continue

        if bobj.parent:
            if bobj.parent not in node_lookup:
                return fail(operator, "The mesh '{}' has a parent of type '{}' (named '{}'). You can only parent meshes to empties, not other meshes.".format(bobj.name, bobj.parent.type, bobj.parent.name))

            attach_node = node_lookup[bobj.parent]
        else:
            print("Warning: Mesh '{}' has no parent".format(bobj.name))

            if auto_root_index is None:
                # This check has been disabled for now. What could go wrong?!
                # if "NodeOrder" in bpy.data.texts and "__auto_root__" not in order_key:
                #     return fail(operator, "The mesh '{}' does not have a parent. Normally, the exporter would create a temporary parent for you to fix this, but you have a specified NodeOrder (may be created by previously importing a DTS file and not pressing Ctrl+N after you're done with it), which does not have the '__auto_root__' entry (name used for the automatic parent).".format(bobj.name))

                auto_root_index = len(shape.nodes)
                shape.nodes.append(Node(shape.name("__auto_root__")))
                shape.default_rotations.append(Quaternion())
                shape.default_translations.append(Vector())

            attach_node = auto_root_index

        lod_name_index, lod_name = shape.name_resolve(lod_name)

        if lod_name not in scene_lods:
            match = re_lod_size.search(lod_name)

            if match:
                lod_size = int(match.group(1))
            else:
                print("Warning: LOD '{}' does not end with a size, assuming size 32".format(lod_name))
                lod_size = 32 # setting?

            print("Creating LOD '{}' (size {})".format(lod_name, lod_size))
            scene_lods[lod_name] = DetailLevel(name=lod_name_index, subshape=0, objectDetail=-1, size=lod_size)
            shape.detail_levels.append(scene_lods[lod_name])

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

                mesh = bobj.to_mesh(scene, apply_modifiers, "PREVIEW")
                bm = bmesh.new()
                bm.from_mesh(mesh)
                bmesh.ops.triangulate(bm, faces=bm.faces)
                bm.to_mesh(mesh)
                bm.free()

                # This is the danger zone
                # Data from down here may not stay around!

                dmesh = Mesh(Mesh.StandardType)
                shape.meshes.append(dmesh)

                dmesh.b_matrix_world = bobj.matrix_world

                dmesh.bounds = dmesh.calculate_bounds_mat(Matrix())
                #dmesh.center = Vector((
                #    (dmesh.bounds.min.x + dmesh.bounds.max.x) / 2,
                #    (dmesh.bounds.min.y + dmesh.bounds.max.y) / 2,
                #    (dmesh.bounds.min.z + dmesh.bounds.max.z) / 2))
                dmesh.center = Vector()
                dmesh.radius = dmesh.calculate_radius_mat(Matrix(), dmesh.center)

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

                    firstElement = len(dmesh.verts)

                    for poly in polys:
                        if mesh.uv_layers:
                            uv_layer = mesh.uv_layers[0].data
                        else:
                            uv_layer = None

                        use_face_normal = not poly.use_smooth

                        for vert_index, loop_index in zip(reversed(poly.vertices), reversed(poly.loop_indices)):
                            dmesh.indices.append(len(dmesh.indices))

                            vert = mesh.vertices[vert_index]

                            if use_face_normal:
                                normal = poly.normal
                            else:
                                normal = vert.normal

                            if transform_mesh and False:
                                dmesh.verts.append(transform_co(bobj, vert.co))
                                dmesh.normals.append(transform_normal(bobj, normal))
                            else:
                                dmesh.verts.append(vert.co.copy())
                                dmesh.normals.append(normal.copy())

                            dmesh.enormals.append(0)

                            if uv_layer:
                                uv = uv_layer[loop_index].uv
                                dmesh.tverts.append(Vector((uv.x, 1 - uv.y)))
                            else:
                                dmesh.tverts.append(Vector((0, 0)))

                    numElements = len(dmesh.verts) - firstElement
                    dmesh.primitives.append(Primitive(firstElement, numElements, flags))

                bpy.data.meshes.remove(mesh) # RIP!

                # ??? ? ?? ???? ??? ?
                dmesh.vertsPerFrame = len(dmesh.verts)

                if len(dmesh.indices) >= 65536:
                    return fail(operator, "The mesh '{}' has too many vertex indices ({} >= 65536)".format(bobj.name, len(dmesh.indices)))

                ### Nobody leaves Hotel California
            else:
                # print("Adding Null mesh for object {} in LOD {}".format(shape.names[object.name], lod_name))
                shape.meshes.append(Mesh(Mesh.NullType))

    print("Creating subshape with " + str(len(shape.nodes)) + " nodes and " + str(len(shape.objects)) + " objects")
    shape.subshapes.append(Subshape(0, 0, 0, len(shape.nodes), len(shape.objects), 0))

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

    shape.center = Vector()

    shape.radius = 0
    shape.radius_tube = 0

    for i, obj in enumerate(shape.objects):
        for j in range(0, obj.numMeshes):
            mesh = shape.meshes[obj.firstMesh + j]

            if mesh.type == Mesh.NullType:
                continue

            b_mat = mesh.b_matrix_world
            bounds = mesh.calculate_bounds_mat(b_mat)

            shape.radius = max(shape.radius, mesh.calculate_radius_mat(b_mat, shape.center))
            shape.radius_tube = max(shape.radius_tube, mesh.calculate_radius_tube_mat(b_mat, shape.center))

            shape.bounds.min.x = min(shape.bounds.min.x, bounds.min.x)
            shape.bounds.min.y = min(shape.bounds.min.y, bounds.min.y)
            shape.bounds.min.z = min(shape.bounds.min.z, bounds.min.z)
            shape.bounds.max.x = max(shape.bounds.max.x, bounds.max.x)
            shape.bounds.max.y = max(shape.bounds.max.y, bounds.max.y)
            shape.bounds.max.z = max(shape.bounds.max.z, bounds.max.z)

    # Is there a bounds mesh? Use that instead.
    if bounds_ob:
      shape.bounds = Box(Vector(bounds_ob.bound_box[0]), Vector(bounds_ob.bound_box[6]))

    shape.center = Vector((
        (shape.bounds.min.x + shape.bounds.max.x) / 2,
        (shape.bounds.min.y + shape.bounds.max.y) / 2,
        (shape.bounds.min.z + shape.bounds.max.z) / 2))

    sequences = {}

    for marker in context.scene.timeline_markers:
        if ":" not in marker.name:
            continue

        name, what = marker.name.rsplit(":", 1)

        if name not in sequences:
            sequences[name] = {}

        if what in sequences[name]:
            print("Warning: Got duplicate '{}' marker for sequence '{}' at frame {} (first was at frame {}), ignoring".format(what, name, marker.frame, sequences[name][what].frame))
            continue

        sequences[name][what] = marker

    sequence_flags_strict = False
    sequence_flags = {}
    sequence_missing = set()

    if "Sequences" in bpy.data.texts:
        for line in bpy.data.texts["Sequences"].as_string().split("\n"):
            line = line.strip()

            if not line:
                continue

            if line == "strict":
                sequence_flags_strict = True
                continue

            if ":" not in line:
                print("Invalid line in 'Sequences':", line)
                continue

            name, flags = line.split(":", 1)

            if flags.lstrip():
                flags = tuple(map(lambda f: f.strip(), flags.split(",")))
            else:
                flags = ()

            sequence_flags[name] = flags
            sequence_missing.add(name)

    for name, markers in sequences.items():
        print("Exporting sequence", name)

        if "start" not in markers:
            return fail(operator, "Missing start marker for sequence '{}'".format(name))

        if "end" not in markers:
            return fail(operator, "Missing end marker for sequence '{}'".format(name))

        seq = Sequence()
        seq.nameIndex = shape.name(name)
        seq.flags = Sequence.AlignedScale
        seq.priority = 1

        if name in sequence_flags:
            for part in sequence_flags[name]:
                flag, *data = part.split(" ", 1)
                if data: data = data[0]

                if flag == "priority":
                    seq.priority = int(data)
                elif flag == "cyclic":
                    seq.flags |= Sequence.Cyclic
                elif flag == "blend":
                    seq.flags |= Sequence.Blend
                else:
                    print("Warning: Unknown flag '{}' (used by sequence '{}')".format(flag, name))

            sequence_missing.remove(name)
        elif sequence_flags_strict:
            return fail(operator, "Missing 'Sequences' line for sequence '{}'".format(name))

        frame_start = markers["start"].frame
        frame_end = markers["end"].frame
        frame_range = frame_end - frame_start + 1

        seq.toolBegin = frame_start
        seq.duration = frame_range * (context.scene.render.fps_base / context.scene.render.fps)

        seq.numKeyframes = frame_range
        seq.firstGroundFrame = len(shape.ground_translations)
        seq.baseRotation = len(shape.node_rotations)
        seq.baseTranslation = len(shape.node_translations)
        seq.baseScale = len(shape.node_aligned_scales)
        seq.baseObjectState = len(shape.objectstates)
        seq.baseDecalState = len(shape.decalstates)
        seq.firstTrigger = len(shape.triggers)

        seq.rotationMatters = [False] * len(shape.nodes)
        seq.translationMatters = [False] * len(shape.nodes)
        seq.scaleMatters = [False] * len(shape.nodes)
        seq.decalMatters = [False] * len(shape.nodes)
        seq.iflMatters = [False] * len(shape.nodes)
        seq.visMatters = [False] * len(shape.nodes)
        seq.frameMatters = [False] * len(shape.nodes)
        seq.matFrameMatters = [False] * len(shape.nodes)

        shape.sequences.append(seq)

        seq_curves_rotation = []
        seq_curves_translation = []
        seq_curves_scale = []

        for ob in animated_nodes:
            index = node_lookup[ob]
            fcurves = ob.animation_data.action.fcurves

            if ob.rotation_mode == "QUATERNION":
                curves_rotation = array_from_fcurves(fcurves, "rotation_quaternion", 4)
            elif ob.rotation_mode == "XYZ":
                curves_rotation = array_from_fcurves(fcurves, "rotation_euler", 3)
            else:
                return fail(operator, "Animated node '{}' uses unsupported rotation_mode '{}'".format(ob.name, ob.rotation_mode))

            curves_translation = array_from_fcurves(fcurves, "location", 3)
            curves_scale = array_from_fcurves(fcurves, "scale", 3)

            if curves_rotation and fcurves_keyframe_in_range(curves_rotation, frame_start, frame_end):
                print("rotation matters for", ob.name)
                seq_curves_rotation.append((curves_rotation, ob.rotation_mode))
                seq.rotationMatters[index] = True

            if curves_translation and fcurves_keyframe_in_range(curves_translation, frame_start, frame_end):
                print("translation matters for", ob.name)
                seq_curves_translation.append(curves_translation)
                seq.translationMatters[index] = True

            if curves_scale and fcurves_keyframe_in_range(curves_scale, frame_start, frame_end):
                print("scale matters for", ob.name)
                seq_curves_scale.append(curves_scale)
                seq.scaleMatters[index] = True

        frame_indices = list(range(frame_start, frame_end + 1))

        for (curves, mode) in seq_curves_rotation:
            for frame in frame_indices:
                if mode == "QUATERNION":
                    r = Quaternion(evaluate_all(curves, frame))
                elif mode == "XYZ":
                    r = Euler(evaluate_all(curves, frame), "XYZ").to_quaternion()
                else:
                    assert false, "unknown rotation_mode after finding matters"
                shape.node_rotations.append(r)

        for curves in seq_curves_translation:
            for frame in frame_indices:
                shape.node_translations.append(Vector(evaluate_all(curves, frame)))

        for curves in seq_curves_scale:
            for frame in frame_indices:
                shape.node_aligned_scales.append(Vector(evaluate_all(curves, frame)))

    for name in sequence_missing:
        print("Warning: Sequence '{}' exists in flags file, but no markers were found".format(name))

    if debug_report:
        print("Writing debug report")
        write_debug_report(filepath + ".txt", shape)

    shape.verify()

    if generate_texture != "disabled":
        f_lookup = generate_texture in ("custom-missing", "all-missing")
        f_custom = generate_texture in ("custom-missing", "custom-always")

        for material in shape.materials:
            if not hasattr(material, "bl_mat"):
                continue

            if f_custom and material.name.lower() in default_materials:
                continue

            if f_lookup and resolve_texture(filepath, material.name) is not None:
                continue

            bl_mat = material.bl_mat
            color = bl_mat.diffuse_color * bl_mat.diffuse_intensity
            color.r = linearrgb_to_srgb(color.r)
            color.g = linearrgb_to_srgb(color.g)
            color.b = linearrgb_to_srgb(color.b)

            image = bpy.data.images.new(material.name.lower() + "_generated", 16, 16)
            image.pixels = (color.r, color.g, color.b, 1.0) * 256
            image.filepath_raw = os.path.join(os.path.dirname(filepath), material.name + ".png")
            image.file_format = "PNG"
            image.save()

    with open(filepath, "wb") as fd:
        shape.save(fd)

    return {"FINISHED"}
