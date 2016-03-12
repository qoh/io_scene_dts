import bpy
import mathutils
import os
from bpy_extras.io_utils import unpack_list

from .DtsShape import DtsShape
from .DtsTypes import *
from .write_report import write_debug_report

import operator
from functools import reduce
from random import random

blockhead_nodes = ("HeadSkin", "chest", "Larm", "Lhand", "Rarm", "Rhand", "pants", "LShoe", "RShoe")
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

def import_material(dmat, filepath):
    bmat = bpy.data.materials.new(dmat.name)

    # Search through directories to find the material texture
    dirname = os.path.dirname(filepath)
    found_tex = False

    while True:
        texbase = os.path.join(dirname, dmat.name)

        for extension in texture_extensions:
            texname = texbase + "." + extension

            if os.path.isfile(texname):
                found_tex = True
                break

        if found_tex or os.path.ismount(dirname):
            break

        prevdir, dirname = dirname, os.path.dirname(dirname)

        if prevdir == dirname:
            break

    if found_tex:
        try:
            teximg = bpy.data.images.load(texname)
        except:
            print("Cannot load image", texname)

        texslot = bmat.texture_slots.add()
        tex = texslot.texture = bpy.data.textures.new(dmat.name, "IMAGE")
        tex.image = teximg
    elif dmat.name in default_materials:
        bmat.diffuse_color = default_materials[dmat.name]
    else: # give it a random color
        bmat.diffuse_color = (random(), random(), random())

    if dmat.flags & Material.SelfIlluminating:
        bmat.use_shadeless = True
    if dmat.flags & Material.Translucent:
        bmat.use_transparency = True

    if dmat.flags & (Material.Additive | Material.Subtractive):
        bmat["blendMode"] = "both"
    elif dmat.flags & Material.Additive:
        bmat["blendMode"] = "additive"
    elif dmat.flags & Material.Subtractive:
        bmat["blendMode"] = "subtractive"
    elif dmat.flags & Material.Translucent:
        bmat["blendMode"] = "none"

    if not (dmat.flags & Material.SWrap):
        bmat["noSWrap"] = True
    if not (dmat.flags & Material.TWrap):
        bmat["noTWrap"] = True
    if not (dmat.flags & Material.NeverEnvMap):
        bmat["envMap"] = True
    if not (dmat.flags & Material.NoMipMap):
        bmat["mipMap"] = True
    if dmat.flags & Material.IFLMaterial:
        bmat["ifl"] = True

    # TODO: MipMapZeroBorder, IFLFrame, DetailMap, BumpMap, ReflectanceMap
    # AuxilaryMask?

    return bmat

def create_bmesh(dmesh, materials, shape):
    me = bpy.data.meshes.new("Mesh")

    faces = []
    material_indices = {}

    indices = dmesh.indices

    for prim in dmesh.primitives:
        assert prim.type & Primitive.Indexed

        dmat = None

        if not (prim.type & Primitive.NoMaterial):
            dmat = shape.materials[prim.type & Primitive.MaterialMask]

            if dmat not in material_indices:
                material_indices[dmat] = len(me.materials)
                me.materials.append(materials[dmat])

        if prim.type & Primitive.Strip:
            even = True
            for i in range(prim.firstElement + 2, prim.firstElement + prim.numElements):
                if even:
                    faces.append(((indices[i], indices[i - 1], indices[i - 2]), dmat))
                else:
                    faces.append(((indices[i - 2], indices[i - 1], indices[i]), dmat))
                even = not even
        elif prim.type & Primitive.Fan:
            even = True
            for i in range(prim.firstElement + 2, prim.firstElement + prim.numElements):
                if even:
                    faces.append(((indices[i], indices[i - 1], indices[0]), dmat))
                else:
                    faces.append(((indices[0], indices[i - 1], indices[i]), dmat))
                even = not even
        else: # Default to Triangle Lists (prim.type & Primitive.Triangles)
            for i in range(prim.firstElement + 2, prim.firstElement + prim.numElements, 3):
                faces.append(((indices[i], indices[i - 1], indices[i - 2]), dmat))

    me.vertices.add(len(dmesh.verts))
    me.vertices.foreach_set("co", unpack_list(dmesh.verts))
    me.vertices.foreach_set("normal", unpack_list(dmesh.normals))

    me.polygons.add(len(faces))
    me.loops.add(len(faces) * 3)

    me.uv_textures.new()
    uvs = me.uv_layers[0]

    for i, ((verts, dmat), poly) in enumerate(zip(faces, me.polygons)):
        poly.loop_total = 3
        poly.loop_start = i * 3

        if dmat:
            poly.material_index = material_indices[dmat]

        for j, index in zip(poly.loop_indices, verts):
            me.loops[j].vertex_index = index
            uv = dmesh.tverts[index]
            uvs.data[j].uv = (uv.x, 1 - uv.y)

    me.validate()
    me.update()

    return me

def load(operator, context, filepath,
         node_mode="EMPTY",
         hide_default_player=False,
         skeleton_only=False,
         debug_report=False):
    shape = DtsShape()

    with open(filepath, "rb") as fd:
        shape.load(fd)

    if debug_report:
        write_debug_report(filepath + ".txt", shape)
        with open(filepath + ".pass.dts", "wb") as fd:
            shape.save(fd)

    # Create a Blender material for each DTS material
    materials = {}

    if not skeleton_only:
        for dmat in shape.materials:
            materials[dmat] = import_material(dmat, filepath)

        # Now assign IFL material properties where needed
        for ifl in shape.iflmaterials:
            mat = materials[shape.materials[ifl.slot]]
            assert mat["ifl"] == True
            mat["iflName"] = shape.names[ifl.name]
            mat["iflFirstFrame"] = ifl.firstFrame
            mat["iflNumFrames"] = ifl.numFrames
            mat["iflTime"] = ifl.time

    # First load all the nodes into armatures
    lod_by_mesh = {}

    for lod in shape.detail_levels:
        lod_by_mesh[lod.objectDetail] = lod

    if "NodeOrder" in bpy.data.texts:
        order_buf = bpy.data.texts["NodeOrder"]
    else:
        order_buf = bpy.data.texts.new("NodeOrder")

    order_buf.from_string("\n".join(shape.names[node.name] for node in shape.nodes))

    node_obs = []
    node_obs_val = {}

    if node_mode == "EMPTY":
        for i, node in enumerate(shape.nodes):
            ob = bpy.data.objects.new(shape.names[node.name], None)
            ob.empty_draw_type = "SINGLE_ARROW"
            ob.empty_draw_size = 0.5

            if node.parent != -1:
                ob.parent = node_obs[node.parent]

            ob.location = shape.default_translations[i]
            ob.rotation_mode = "QUATERNION"
            # weird representation difference -wxyz vs xyzw
            ob.rotation_quaternion = mathutils.Quaternion((
                -shape.default_rotations[i].w,
                shape.default_rotations[i].x,
                shape.default_rotations[i].y,
                shape.default_rotations[i].z
            ))

            context.scene.objects.link(ob)
            node_obs.append(ob)
            node_obs_val[node] = ob
    elif node_mode == "ARMATURE":
        pass
    elif node_mode == "BONE":
        pass

    # Try animation?
    globalToolIndex = 10
    fps = context.scene.render.fps

    sequences_text = []

    for seq in shape.sequences:
        name = shape.names[seq.nameIndex]
        print("Importing sequence", name)

        flags = []

        if seq.flags & Sequence.Cyclic:
            flags.append("cyclic")

        if seq.flags & Sequence.Blend:
            flags.append("blend {}".format(seq.priority))

        if flags:
            sequences_text.append(name + ": " + ", ".join(flags))

        nodesRotation = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(shape.nodes, seq.rotationMatters))))
        nodesTranslation = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(shape.nodes, seq.translationMatters))))
        nodesScale = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(shape.nodes, seq.scaleMatters))))

        step = 5

        for mattersIndex, node in enumerate(nodesTranslation):
            ob = node_obs_val[node]

            for frameIndex in range(seq.numKeyframes):
                old = ob.location
                ob.location = shape.node_translations[seq.baseTranslation + mattersIndex * seq.numKeyframes + frameIndex]
                ob.keyframe_insert("location", index=-1, frame=globalToolIndex + frameIndex * step)
                ob.location = old

        for mattersIndex, node in enumerate(nodesRotation):
            ob = node_obs_val[node]

            for frameIndex in range(seq.numKeyframes):
                old = ob.rotation_quaternion
                ob.rotation_quaternion = shape.node_rotations[seq.baseRotation + mattersIndex * seq.numKeyframes + frameIndex].to_blender()
                ob.keyframe_insert("rotation_quaternion", index=-1, frame=globalToolIndex + frameIndex * step)
                ob.rotation_quaternion = old

        for mattersIndex, node in enumerate(nodesScale):
            ob = node_obs_val[node]

            for frameIndex in range(seq.numKeyframes):
                old = ob.scale
                index = seq.baseScale + mattersIndex * seq.numKeyframes + frameIndex

                if seq.UniformScale:
                    s = shape.node_uniform_scales[index]
                    ob.scale = s, s, s
                elif seq.AlignedScale:
                    ob.scale = shape.node_aligned_scales[index]
                elif seq.ArbitraryScale:
                    print("Warning: Arbitrary scale animation not implemented")
                    break
                else:
                    print("Warning: Invalid scale flags found in sequence")
                    break

                ob.keyframe_insert("scale", index=-1, frame=globalToolIndex + frameIndex * step)
                ob.scale = old

        context.scene.timeline_markers.new(name + ":start", globalToolIndex)
        context.scene.timeline_markers.new(name + ":end", globalToolIndex + seq.numKeyframes * step)
        globalToolIndex += seq.numKeyframes * step + 30

        # action = bpy.data.actions.new(name=shape.names[seq.nameIndex])
        #
        # for dim in range(3):
        #     fcu = action.fcurves.new(data_path="location", index=dim)
        #     fcu.keyframe_points.add(2)
        #     fcu.keyframe_points[0].co = 10.0, 0.0
        #     fcu.keyframe_points[1].co = 20.0, 1.0
            # for frameIndex in range(seq.numKeyframes):
            #     if seq.translationMatters[frameIndex]:
            #         ind = len(fcu.keyframe_points)
            #         fcu.keyframe_points.add(1)
            #         fcu.keyframe_points[ind] = frameIndex, shape.node_translations[seq.baseTranslation + frameIndex][dim]

        # for dim in range(4):
        #     fcu = action.fcurves.new(data_path="rotation_quaternion", index=dim)
        #     for frameIndex in range(seq.numKeyframes):
        #         if seq.rotationMatters[frameIndex]:
        #             ind = len(fcu.keyframe_points)
        #             fcu.keyframe_points.add(1)
        #             fcu.keyframe_points[ind] = frameIndex, shape.node_rotations[seq.baseRotation + frameIndex][dim]

    if "Sequences" in bpy.data.texts:
        sequences_buf = bpy.data.texts["Sequences"]
    else:
        sequences_buf = bpy.data.texts.new("Sequences")

    sequences_buf.from_string("\n".join(sequences_text))

    if not skeleton_only:
        # Then put objects in the armatures
        for obj in shape.objects:
            for meshIndex in range(obj.numMeshes):
                mesh = shape.meshes[obj.firstMesh + meshIndex]

                if mesh.type == Mesh.NullType:
                    continue

                if mesh.type != Mesh.StandardType:
                    print("{} is a {} mesh, unsupported, but trying".format(
                        shape.names[obj.name], mesh.type))
                    # continue

                bmesh = create_bmesh(mesh, materials, shape)
                bobj = bpy.data.objects.new(name=shape.names[obj.name], object_data=bmesh)
                context.scene.objects.link(bobj)

                if obj.node != -1:
                    if node_mode == "BONE":
                        bobj.location = node_obs[obj.node].head
                        bobj.parent = armature_ob
                        bobj.parent_bone = node_obs[obj.node].name
                        bobj.parent_type = "BONE"
                    else:
                        bobj.parent = node_obs[obj.node]

                if hide_default_player and shape.names[obj.name] not in blockhead_nodes:
                    bobj.hide = True

                lod_name = shape.names[lod_by_mesh[meshIndex].name]

                if lod_name not in bpy.data.groups:
                    bpy.data.groups.new(lod_name)

                bpy.data.groups[lod_name].objects.link(bobj)

    # Import a bounds mesh
    me = bpy.data.meshes.new("Mesh")
    me.vertices.add(8)
    me.vertices[0].co = (shape.bounds.min.x, shape.bounds.min.y, shape.bounds.min.z)
    me.vertices[1].co = (shape.bounds.max.x, shape.bounds.min.y, shape.bounds.min.z)
    me.vertices[2].co = (shape.bounds.max.x, shape.bounds.max.y, shape.bounds.min.z)
    me.vertices[3].co = (shape.bounds.min.x, shape.bounds.max.y, shape.bounds.min.z)
    me.vertices[4].co = (shape.bounds.min.x, shape.bounds.min.y, shape.bounds.max.z)
    me.vertices[5].co = (shape.bounds.max.x, shape.bounds.min.y, shape.bounds.max.z)
    me.vertices[6].co = (shape.bounds.max.x, shape.bounds.max.y, shape.bounds.max.z)
    me.vertices[7].co = (shape.bounds.min.x, shape.bounds.max.y, shape.bounds.max.z)
    me.validate()
    me.update()
    ob = bpy.data.objects.new("bounds", me)
    ob.draw_type = "BOUNDS"
    context.scene.objects.link(ob)

    return {"FINISHED"}
