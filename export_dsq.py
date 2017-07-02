import bpy, sys
from math import sqrt, pi
from operator import attrgetter
from itertools import groupby

from .DsqFile import DsqFile
from .DtsTypes import *
from .util import fail, evaluate_all, find_reference, array_from_fcurves, \
    fcurves_keyframe_in_range, find_reference
from .shared_export import find_seqs

def save(operator, context, filepath,
         select_marker=False,
         debug_report=False):
    print("Exporting scene to DSQ")

    scene = context.scene
    dsq = DsqFile()

    # Find all the sequences to export
    sequences, sequence_flags = find_seqs(context.scene, select_marker)

    # Seek to reference frame if present before reading nodes
    reference_frame = find_reference(scene)

    if reference_frame is not None:
        print("Note: Seeking to reference frame at", reference_frame)
        scene.frame_set(reference_frame)

    # Create a DTS node for every armature/empty in the scene
    node_ob = {}
    node_transform = {}

    def traverse_node(node):
        node_ob[node.name] = node
        node_transform[node] = node.matrix_local.decompose()
        dsq.nodes.append(node.name)

        for child in node.children:
            if child.type == "EMPTY":
                traverse_node(child)

    for ob in scene.objects:
        if ob.type == "EMPTY" and not ob.parent:
            traverse_node(ob)

    reference_frame = find_reference(context.scene)

    # NodeOrder backwards compatibility
    if "NodeOrder" in bpy.data.texts:
        print("Warning: NodeOrder found, using it for backwards compatibility")
        order = bpy.data.texts["NodeOrder"].as_string().split("\n")
        order_key = {name: i for i, name in enumerate(order)}
    else:
        order_key = {}

    # Sort by node indices from the DTS
    dsq.nodes = list(sorted(dsq.nodes, key=lambda n:
        order_key.get(n, node_ob[n].get("nodeIndex", sys.maxsize))))

    node_index = {node_ob[name]: i for i, name in enumerate(dsq.nodes)}
    auto_root_index = None
    animated_nodes = []

    for node in dsq.nodes:
        ob = node_ob[node]
        data = ob.animation_data
        if data and data.action and len(data.action.fcurves):
            animated_nodes.append(ob)

    for bobj in scene.objects:
        if bobj.type != "MESH" or bobj.name.lower() == "bounds":
            continue

        if bobj.users_group and bobj.users_group[0].name == "__ignore__":
            continue

        if not bobj.parent:
            if auto_root_index is None:
                auto_root_index = len(dsq.nodes)
                dsq.nodes.append("__auto_root__")

    for name, markers in sequences.items():
        print("Exporting sequence", name)

        if "start" not in markers:
            return fail(operator, "Missing start marker for sequence '{}'".format(name))

        if "end" not in markers:
            return fail(operator, "Missing end marker for sequence '{}'".format(name))

        frame_start = markers["start"].frame
        frame_end = markers["end"].frame
        frame_range = frame_end - frame_start + 1

        seq = Sequence()
        seq.name = name
        seq.flags = Sequence.AlignedScale
        seq.priority = 1

        seq.toolBegin = frame_start
        seq.duration = frame_range * (context.scene.render.fps_base / context.scene.render.fps)

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
                elif flag == "duration":
                    seq.duration = float(data)
                else:
                    print("Warning: Unknown flag '{}' (used by sequence '{}')".format(flag, name))

        seq.numKeyframes = frame_range
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

        frame_indices = list(range(frame_start, frame_end + 1))

        # Store all animation data so we don't need to frame_set all over the place
        animation_data = {frame: {} for frame in frame_indices}

        for frame in frame_indices:
            scene.frame_set(frame)

            for ob in animated_nodes:
                animation_data[frame][ob] = ob.matrix_local.decompose()

        for ob in animated_nodes:
            index = node_index[ob]

            base_translation, base_rotation, base_scale = node_transform[ob]

            fcurves = ob.animation_data.action.fcurves

            if ob.rotation_mode == "QUATERNION":
                curves_rotation = array_from_fcurves(fcurves, "rotation_quaternion", 4)
            elif ob.rotation_mode == "XYZ":
                curves_rotation = array_from_fcurves(fcurves, "rotation_euler", 3)
            else: # TODO: Add all the other modes
                curves_rotation = None

            curves_translation = array_from_fcurves(fcurves, "location", 3)
            curves_scale = array_from_fcurves(fcurves, "scale", 3)

            # Decide what matters by presence of f-curves
            if curves_rotation and fcurves_keyframe_in_range(curves_rotation, frame_start, frame_end):
                seq.rotationMatters[index] = True

            if curves_translation and fcurves_keyframe_in_range(curves_translation, frame_start, frame_end):
                seq.translationMatters[index] = True

            if curves_scale and fcurves_keyframe_in_range(curves_scale, frame_start, frame_end):
                seq.scaleMatters[index] = True

            # Write the data where it matters
            # This assumes that animated_nodes is in the same order as shape.nodes
            for frame in frame_indices:
                translation, rotation, scale = animation_data[frame][ob]

                if seq.translationMatters[index]:
                    if seq.flags & Sequence.Blend:
                        translation -= base_translation
                    dsq.translations.append(translation)

                if seq.rotationMatters[index]:
                    if seq.flags & Sequence.Blend:
                        rotation = base_rotation.inverted() * rotation
                    dsq.rotations.append(rotation)

                if seq.scaleMatters[index]:
                    dsq.aligned_scales.append(scale)

    with open(filepath, "wb") as fd:
        dsq.write(fd)

    if debug_report:
        with open(filepath + ".txt", "w") as fd:
            dsq.write_dump(fd)

    return {"FINISHED"}
