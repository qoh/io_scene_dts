# This file is currently unused

import bpy

def import_sequence(is_dsq, shape, seq):
    if is_dsq:
        name = shape.names[seq.nameIndex]
    else:
        name = seq.name
    
    act = bpy.data.actions.new(name)
    
    flags = ["priority {}".format(seq.priority)]
    if seq.flags & Sequence.Cyclic:
        flags.append("cyclic")
    if seq.flags & Sequence.Blend:
        flags.append("blend")
    # sequences_text.append(name + ": " + ", ".join(flags))

    if is_dsq:
        nodes = shape.nodes
        rotations = shape.rotations
    else:
        nodes = tuple(map(lambda n: shape.names[n.name], shape.nodes))
        rotations = shape.node_rotations
    
    if seq.flags & Sequence.UniformScale:
        scales = tuple(map(lambda s: (s, s, s), shape.uniform_scales))
    elif seq.flags & Sequence.AlignedScale:
        scales = shape.aligned_scales
    elif seq.flags & Sequence.ArbitraryScale:
        print("Warning: Arbitrary scale animation not implemented")
        break
    else:
        print("Warning: Invalid scale flags found in sequence")
        break
    
    nodes_translation = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(nodes, seq.translationMatters))))
    nodes_rotation = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(nodes, seq.rotationMatters))))
    nodes_scale = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(nodes, seq.scaleMatters))))

    for matters_index, node_name in enumerate(nodes_translation):
        data_path = 'pose.bones["{}"].location'.format(node_name)
        fcus = tuple(map(lambda array_index: act.fcurves.new(data_path, array_index), range(3)))
        for frame_index in range(seq.numKeyframes):
            array = translations[seq.baseTranslation + matters_index * seq.numKeyframes + frame_index]
            for array_index, fcu in enumerate(fcus):
                fcu.keyframe_points.add(1)
                key = fcu.keyframe_points[-1]
                key.interpolation = "LINEAR"
                key.co = (1 + frame_index, array[array_index])

    for matters_index, node_name in enumerate(nodes_rotation):
        data_path = 'pose.bones["{}"].rotation_quaternion'.format(node_name)
        fcus = tuple(map(lambda array_index: act.fcurves.new(data_path, array_index), range(4)))
        for frame_index in range(seq.numKeyframes):
            array = rotations[seq.baseRotation + matters_index * seq.numKeyframes + frame_index]
            for array_index, fcu in enumerate(fcus):
                fcu.keyframe_points.add(1)
                key = fcu.keyframe_points[-1]
                key.interpolation = "LINEAR"
                key.co = (1 + frame_index, array[array_index])
    
    for matters_index, node_name in enumerate(nodes_scale):
        data_path = 'pose.bones["{}"].scale'.format(node_name)
        fcus = tuple(map(lambda array_index: act.fcurves.new(data_path, array_index), range(3)))
        for frame_index in range(seq.numKeyframes):
            array = scales[seq.baseScale + matters_index * seq.numKeyframes + frame_index]
            for array_index, fcu in enumerate(fcus):
                fcu.keyframe_points.add(1)
                key = fcu.keyframe_points[-1]
                key.interpolation = "LINEAR"
                key.co = (1 + frame_index, array[array_index])

    # if seq.flags & Sequence.Blend:
    #     if reference_frame is None:
    #     return fail(operator, "Missing 'reference' marker for blend animation '{}'".format(name))
    #     ref_vec = Vector(evaluate_all(curves, reference_frame))
    #     vec = ref_vec + vec
    # if seq.flags & Sequence.Blend:
    #     if reference_frame is None:
    #     return fail(operator, "Missing 'reference' marker for blend animation '{}'".format(name))
    #     ref_rot = Quaternion(evaluate_all(curves, reference_frame))
    #     rot = ref_rot * rot
