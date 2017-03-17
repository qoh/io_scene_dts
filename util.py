import os
import bpy
from colorsys import hsv_to_rgb
from itertools import count
from fractions import Fraction

texture_extensions = ("png", "jpg")

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

for key, value in tuple(default_materials.items()):
    default_materials[key.lower()] = value

def resolve_texture(filepath, name):
    dirname = os.path.dirname(filepath)

    while True:
        texbase = os.path.join(dirname, name)

        for extension in texture_extensions:
            texname = texbase + "." + extension

            if os.path.isfile(texname):
                return texname

        if os.path.ismount(dirname):
            break

        prevdir, dirname = dirname, os.path.dirname(dirname)

        if prevdir == dirname:
            break

def fractions():
    yield 0

    for k in count():
        i = 2 ** k

        for j in range(1, i, 2):
            yield j / i

def get_hsv_colors():
    for h in fractions():
        yield (h, 0.75, 0.75)

def get_rgb_colors():
    return map(lambda hsv: hsv_to_rgb(*hsv), get_hsv_colors())

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

def find_reference(scene):
    reference_marker = scene.timeline_markers.get("reference")
    if reference_marker is not None:
        return reference_marker.frame

def fail(operator, message):
    print("Error:", message)
    operator.report({"ERROR"}, message)
    return {"FINISHED"}