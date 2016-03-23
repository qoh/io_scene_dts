import mathutils, bpy
from mathutils import Matrix, Euler
from math import sqrt, pi
from operator import attrgetter
from itertools import groupby

from .DsqFile import DsqFile
from .DtsTypes import *

def fail(operator, message):
    print("Error:", message)
    operator.report({"ERROR"}, message)
    return {"FINISHED"}

def rotation_from_ob(ob):
    if ob.rotation_mode == "QUATERNION":
        r = ob.rotation_quaternion
    elif ob.rotation_mode == "AXIS_ANGLE":
        print("Warning: '{}' uses unsupported axis angle rotation".format(ob.name))
        r = ob.rotation_quaternion # ob.rotation_axis_angle
    else:
        r = ob.rotation_euler.to_quaternion()
    return DtsQuat(r[1], r[2], r[3], -r[0])

def export_all_nodes(node_ob, dsq, obs):
    for ob in obs:
        if ob.type == "ARMATURE" or ob.type == "EMPTY":
            node_ob[ob.name] = ob
            dsq.nodes.append(ob.name)
            export_all_nodes(node_ob, dsq, ob.children)

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
    return ob.matrix_world * co

def transform_normal(ob, normal):
    return (ob.matrix_world.to_3x3() * normal).normalized()

def save(operator, context, filepath,
         debug_report=True):
    print("Exporting scene to DTS")

    scene = context.scene
    dsq = DsqFile()

    # Create a DTS node for every armature/empty in the scene
    node_ob = {}
    export_all_nodes(node_ob, dsq, filter(lambda o: not o.parent, scene.objects))

    # Figure out if we should create our own root node
    if "NodeOrder" in bpy.data.texts:
        order = bpy.data.texts["NodeOrder"].as_string().split("\n")
        order_key = {name: i for i, name in enumerate(order)}

        try:
            dsq.nodes = list(sorted(dsq.nodes, key=lambda n: order_key[n]))
        except KeyError as e:
            return fail(operator, "Node '{}' is missing from the 'NodeOrder' text block. This means that you may have added nodes to a skeleton when you shouldn't have, or that you forgot to remove the 'NodeOrder' text block. It is automatically created by the \"Import node order\" option when importing a DTS file. Perhaps you forgot to press Ctrl+N after you imported?".format(e.args[0]))

        shape_node_names = set(dsq.nodes)
        missing_nodes = tuple(filter(lambda n: n not in dsq.nodes, order))

        if missing_nodes:
            return fail(operator, "The following nodes were found in the 'NodeOrder' text block but do not exist in the shape. This means that you may have removed nodes from a skeleton when you shouldn't have, or that you forgot to remove the 'NodeOrder' text block:\n{}".format(", ".join(missing_nodes)))

    node_index = {node_ob[name]: i for i, name in enumerate(dsq.nodes)}
    animated_nodes = []

    for node in dsq.nodes:
        ob = node_ob[node]
        data = ob.animation_data
        if data and data.action and len(data.action.fcurves):
            animated_nodes.append(ob)

    for bobj in scene.objects:
        if bobj.type != "MESH":
            continue

        if bobj.users_group and bobj.users_group[0].name == "__ignore__":
            continue

        if not bobj.parent:
            if not auto_root_index:
                if "NodeOrder" in bpy.data.texts and "__auto_root__" not in order_key:
                    return fail(operator, "The mesh '{}' does not have a parent. Normally, the exporter would create a temporary parent for you to fix this, but you have a specified NodeOrder (may be created by previously importing a DTS file and not pressing Ctrl+N after you're done with it), which does not have the '__auto_root__' entry (name used for the automatic parent).".format(bobj.name))

                dsq.nodes.append("__auto_root__")

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
        seq.name = name
        seq.flags = Sequence.AlignedScale

        if name in sequence_flags:
            for part in sequence_flags[name]:
                flag, *data = part.split(" ", 1)
                if data: data = data[0]

                if flag == "cyclic":
                    seq.flags |= Sequence.Cyclic
                elif flag == "blend":
                    seq.flags |= Sequence.Blend
                    seq.priority = int(data)
                else:
                    print("Warning: Unknown flag '{}' (used by sequence '{}')".format(flag, name))

            sequence_missing.remove(name)
        elif sequence_flags_strict:
            return fail(operator, "Missing 'Sequences' line for sequence '{}'".format(name))

        frame_start = markers["start"].frame
        frame_end = markers["end"].frame

        frame_range = frame_end - frame_start + 1
        frame_step = 1 # TODO: GCD of keyframe spacings

        seq.toolBegin = frame_start
        seq.duration = frame_range * (context.scene.render.fps_base / context.scene.render.fps)

        seq.numKeyframes = int(math.ceil(float(frame_range) / frame_step))
        seq.firstGroundFrame = len(dsq.ground_translations)
        seq.baseRotation = len(dsq.rotations)
        seq.baseTranslation = len(dsq.translations)
        seq.baseScale = len(dsq.aligned_scales)
        seq.baseObjectState = 0
        seq.baseDecalState = 0
        seq.firstTrigger = len(dsq.triggers)

        seq.rotationMatters = [False] * len(dsq.nodes)
        seq.translationMatters = [False] * len(dsq.nodes)
        seq.scaleMatters = [False] * len(dsq.nodes)
        seq.decalMatters = [False] * len(dsq.nodes)
        seq.iflMatters = [False] * len(dsq.nodes)
        seq.visMatters = [False] * len(dsq.nodes)
        seq.frameMatters = [False] * len(dsq.nodes)
        seq.matFrameMatters = [False] * len(dsq.nodes)

        dsq.sequences.append(seq)

        seq_curves_rotation = []
        seq_curves_translation = []
        seq_curves_scale = []

        for ob in animated_nodes:
            index = node_index[ob]
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

        frame_indices = []
        frame_current = frame_start

        while frame_current <= frame_end:
            frame_indices.append(frame_current)

            if frame_current == frame_end:
                break

            frame_current = min(frame_end, frame_current + frame_step)

        for (curves, mode) in seq_curves_rotation:
            for frame in frame_indices:
                if mode == "QUATERNION":
                    r = evaluate_all(curves, frame)
                elif mode == "XYZ":
                    r = Euler(evaluate_all(curves, frame), "XYZ").to_quaternion()
                else:
                    assert false, "unknown rotation_mode after finding matters"
                dsq.rotations.append(DtsQuat(r[1], r[2], r[3], -r[0]))

        for curves in seq_curves_translation:
            for frame in frame_indices:
                dsq.translations.append(Vector(evaluate_all(curves, frame)))

        for curves in seq_curves_scale:
            for frame in frame_indices:
                dsq.aligned_scales.append(Vector(evaluate_all(curves, frame)))

    for name in sequence_missing:
        print("Warning: Sequence '{}' exists in flags file, but no markers were found".format(name))

    with open(filepath, "wb") as fd:
        dsq.write(fd)

    with open(filepath + ".txt", "w") as fd:
        dsq.write_dump(fd)

    return {"FINISHED"}
