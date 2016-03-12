import bpy
from math import ceil

from .DsqFile import DsqFile
from .DtsTypes import Sequence

def fail(operator, message):
  print("Error: " + message)
  operator.report({"ERROR"}, message)
  return {"FINISHED"}

def get_free_name(name, taken):
  if name not in taken:
    return name

  suffix = 1

  while True:
    name_try = name + "." + str(suffix)

    if name_try not in taken:
      return name_try

    suffix += 1

def action_get_or_new(ob):
  if not ob.animation_data:
    ob.animation_data_create()

  if ob.animation_data.action:
    return ob.animation_data.action

  action = bpy.data.actions.new(ob.name + "Action")
  ob.animation_data.action = action

  return action

def ob_curves_array(ob, data_path, array_count):
  action = action_get_or_new(ob)
  curves = [None] * array_count

  for curve in action.fcurves:
    if curve.data_path != data_path or curve.array_index < 0 or curve.array_index >= array_count:
      continue
    
    if curves[curve.array_index]:
      pass # TODO: warn if more than one curve for an array slot

    curves[curve.array_index] = curve

  for index, curve in enumerate(curves):
    if curve is None:
      curves[index] = action.fcurves.new(data_path, index)

  return curves

def ob_location_curves(ob):
  return ob_curves_array(ob, "location", 3)

def ob_scale_curves(ob):
  return ob_curves_array(ob, "scale", 3)

def ob_rotation_curves(ob):
  if ob.rotation_mode == "QUATERNION":
    data_path = "rotation_quaternion"
    array_count = 4
  elif ob.rotation_mode == "XYZ":
    data_path = "rotation_euler"
    array_count = 3
  else:
    assert false, "unhandled rotation mode '{}' on '{}'".format(ob.rotation_mode, ob.name)

  return ob.rotation_mode, ob_curves_array(ob, data_path, array_count)

# action.fcurves.new(data_path, array_index)
# action.fcurves[].keyframe_points.add(number)
# action.fcurves[].keyframe_points[].interpolation = "LINEAR"
# action.fcurves[].keyframe_points[].co

def load(operator, context, filepath):
  dsq = DsqFile()

  with open(filepath, "rb") as fd:
    dsq.read(fd)

  print("Resolving nodes...")

  found_obs = {}

  # Find all our candidate nodes
  # DSQ is case-sensitive, that's why we can't just [] lookup
  for ob in context.scene.objects:
    if ob.type in ("EMPTY", "ARMATURE"):
      name = ob.name.lower()

      if name in found_obs:
        print("Warning: Nodes with varying capitalization found ('{}', '{}'), ignoring second".format(found_obs[name].name, ob.name))
        continue

      found_obs[name] = ob

  nodes = [None] * len(dsq.nodes)
  node_missing = []

  # Now associate DSQ node indices with Blender objects
  for index, name in enumerate(dsq.nodes):
    lower = name.lower()

    if lower in found_obs:
      nodes[index] = found_obs[lower]
    else:
      node_missing.append(name)
  
  if node_missing:
    return fail(operator, "The following nodes from the DSQ file could not be found in your scene:\n" + ", ".join(node_missing))

  # Now, find all the existing sequence names so we can rename duplicates
  # Also find out where the last user-defined animation data is
  last_frame = 1
  scene_sequences = set()

  for marker in context.scene.timeline_markers:
    last_frame = max(last_frame, int(ceil(marker.frame + 10)))

    if ":" not in marker.name:
      continue

    name, what = marker.name.rsplit(":", 1)
    scene_sequences.add(name)

  for action in bpy.data.actions:
    last_frame = max(last_frame, int(ceil(action.frame_range[1] + 10)))

  if "Sequences" in bpy.data.texts:
    for line in bpy.data.texts["Sequences"].as_string().split("\n"):
      line = line.strip()

      if not line or line == "strict" or ":" not in line:
        continue

      name, flags = line.split(":", 1)
      scene_sequences.add(name)

  sequences_text = []

  # Create Blender keyframes and markers for each sequence
  for seq in dsq.sequences:
    name = get_free_name(seq.name, scene_sequences)
    print("found seq", seq.name, "to", name)

    flags = []

    if seq.flags & Sequence.Cyclic:
      flags.append("cyclic")

    if seq.flags & Sequence.Blend:
      flags.append("blend {}".format(seq.priority))

    if flags:
      sequences_text.append(name + ": " + ", ".join(flags))

    nodesRotation = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(nodes, seq.rotationMatters))))
    nodesTranslation = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(nodes, seq.translationMatters))))
    nodesScale = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(nodes, seq.scaleMatters))))

    step = 1

    for mattersIndex, ob in enumerate(nodesTranslation):
      curves = ob_location_curves(ob)

      #for frameIndex in range(seq.numKeyframes):
      #  old = ob.location
      #  ob.location = dsq.translations[seq.baseTranslation + mattersIndex * seq.numKeyframes + frameIndex]
      #  ob.keyframe_insert("location", index=-1, frame=last_frame + frameIndex * step)
      #  ob.location = old

      for frameIndex in range(seq.numKeyframes):
        vec = dsq.translations[seq.baseTranslation + mattersIndex * seq.numKeyframes + frameIndex]

        for curve in curves:
          curve.keyframe_points.add(1)
          key = curve.keyframe_points[-1]
          key.interpolation = "LINEAR"
          key.co = (last_frame + frameIndex * step, vec[curve.array_index])

    for mattersIndex, ob in enumerate(nodesRotation):
      mode, curves = ob_rotation_curves(ob)

      #for frameIndex in range(seq.numKeyframes):
      #  old = ob.rotation_quaternion
      #  ob.rotation_quaternion = dsq.rotations[seq.baseRotation + mattersIndex * seq.numKeyframes + frameIndex].to_blender()
      #  ob.keyframe_insert("rotation_quaternion", index=-1, frame=last_frame + frameIndex * step)
      #  ob.rotation_quaternion = old

      for frameIndex in range(seq.numKeyframes):
        rot = dsq.rotations[seq.baseRotation + mattersIndex * seq.numKeyframes + frameIndex].to_blender()
        if mode != "QUATERNION":
          rot = rot.to_euler(mode)

        for curve in curves:
          curve.keyframe_points.add(1)
          key = curve.keyframe_points[-1]
          key.interpolation = "LINEAR"
          key.co = (last_frame + frameIndex * step, rot[curve.array_index])

    for mattersIndex, ob in enumerate(nodesScale):
      for frameIndex in range(seq.numKeyframes):
        old = ob.scale
        index = seq.baseScale + mattersIndex * seq.numKeyframes + frameIndex

        if seq.UniformScale:
          s = dsq.uniform_scales[index]
          ob.scale = s, s, s
        elif seq.AlignedScale:
          ob.scale = dsq.aligned_scales[index]
        elif seq.ArbitraryScale:
          print("Warning: Arbitrary scale animation not implemented")
          break
        else:
          print("Warning: Invalid scale flags found in sequence")
          break

        ob.keyframe_insert("scale", index=-1, frame=last_frame + frameIndex * step)
        ob.scale = old

    context.scene.timeline_markers.new(name + ":start", last_frame)
    context.scene.timeline_markers.new(name + ":end", last_frame + seq.numKeyframes)

    last_frame += seq.numKeyframes + 10

  if "Sequences" in bpy.data.texts:
    sequences_buf = bpy.data.texts["Sequences"]
  else:
    sequences_buf = bpy.data.texts.new("Sequences")

  if not sequences_buf.as_string():
    sequences_buf.from_string("\n".join(sequences_text))
  else:
    sequences_buf.from_string(sequences_buf.as_string() + "\n" + "\n".join(sequences_text))

  return {"FINISHED"}
