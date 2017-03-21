import bpy
import os
from bpy_extras.io_utils import unpack_list

from .DtsShape import DtsShape
from .DtsTypes import *
from .write_report import write_debug_report
from .util import default_materials, resolve_texture, get_rgb_colors, fail, \
    ob_location_curves, ob_scale_curves, ob_rotation_curves, evaluate_all

import operator
from itertools import zip_longest, count
from functools import reduce
from random import random

def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)

def dedup_name(group, name):
    if name not in group:
        return name

    for suffix in count(2):
        new_name = name + "#" + str(suffix)

        if new_name not in group:
            return new_name

def import_material(color_source, dmat, filepath):
    bmat = bpy.data.materials.new(dedup_name(bpy.data.materials, dmat.name))
    bmat.diffuse_intensity = 1

    texname = resolve_texture(filepath, dmat.name)

    if texname is not None:
        try:
            teximg = bpy.data.images.load(texname)
        except:
            print("Cannot load image", texname)

        texslot = bmat.texture_slots.add()
        texslot.use_map_alpha = True
        tex = texslot.texture = bpy.data.textures.new(dmat.name, "IMAGE")
        tex.image = teximg

        # Try to figure out a diffuse color for solid shading
        if teximg.size[0] <= 16 and teximg.size[1] <= 16:
            if teximg.use_alpha:
                pixels = grouper(teximg.pixels, 4)
            else:
                pixels = grouper(teximg.pixels, 3)

            color = pixels.__next__()

            for other in pixels:
                if other != color:
                    break
            else:
                bmat.diffuse_color = color[:3]
    elif dmat.name.lower() in default_materials:
        bmat.diffuse_color = default_materials[dmat.name.lower()]
    else: # give it a random color
        bmat.diffuse_color = color_source.__next__()

    if dmat.flags & Material.SelfIlluminating:
        bmat.use_shadeless = True
    if dmat.flags & Material.Translucent:
        bmat.use_transparency = True
    
    if dmat.flags & Material.Additive:
        bmat.torque_props.blend_mode = "ADDITIVE"
    elif dmat.flags & Material.Subtractive:
        bmat.torque_props.blend_mode = "SUBTRACTIVE"
    else:
        bmat.torque_props.blend_mode = "NONE"

    if dmat.flags & Material.SWrap:
        bmat.torque_props.s_wrap = True
    if dmat.flags & Material.TWrap:
        bmat.torque_props.t_wraps = True
    if dmat.flags & Material.IFLMaterial:
        bmat.torque_props.use_ifl = True

    # TODO: MipMapZeroBorder, IFLFrame, DetailMap, BumpMap, ReflectanceMap
    # AuxilaryMask?

    return bmat

class index_pass:
    def __getitem__(self, item):
        return item

def create_bmesh(dmesh, materials, shape):
    me = bpy.data.meshes.new("Mesh")

    faces = []
    material_indices = {}

    indices_pass = index_pass()

    for prim in dmesh.primitives:
        if prim.type & Primitive.Indexed:
            indices = dmesh.indices
        else:
            indices = indices_pass

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
        poly.use_smooth = True # DTS geometry is always smooth shaded
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

def file_base_name(filepath):
    return os.path.basename(filepath).rsplit(".", 1)[0]

def load(operator, context, filepath,
         reference_keyframe=True,
         import_sequences=True,
         use_armature=False,
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
    color_source = get_rgb_colors()

    for dmat in shape.materials:
        materials[dmat] = import_material(color_source, dmat, filepath)

    # Now assign IFL material properties where needed
    for ifl in shape.iflmaterials:
        mat = materials[shape.materials[ifl.slot]]
        assert mat.torque_props.use_ifl == True
        mat.torque_props.ifl_name = shape.names[ifl.name]
        mat.torque_props.ifl_first_frame = ifl.firstFrame
        mat.torque_props.ifl_num_frames = ifl.numFrames
        mat.torque_props.ifl_time = ifl.time

    # First load all the nodes into armatures
    lod_by_mesh = {}

    for lod in shape.detail_levels:
        lod_by_mesh[lod.objectDetail] = lod

    node_obs = []
    node_obs_val = {}

    if use_armature:
        root_arm = bpy.data.armatures.new(file_base_name(filepath))
        root_ob = bpy.data.objects.new(root_arm.name, root_arm)
        root_ob.show_x_ray = True

        context.scene.objects.link(root_ob)
        context.scene.objects.active = root_ob

        # Calculate armature-space matrix, head and tail for each node
        for i, node in enumerate(shape.nodes):
            node.mat = shape.default_rotations[i].to_matrix()
            node.mat = Matrix.Translation(shape.default_translations[i]) * node.mat.to_4x4()
            if node.parent != -1:
                node.mat = shape.nodes[node.parent].mat * node.mat
            # node.head = node.mat.to_translation()
            # node.tail = node.head + Vector((0, 0, 0.25))
            node.tail = node.mat.to_translation()
            node.head = node.tail - Vector((0, 0, 0.25))
        
        bpy.ops.object.mode_set(mode="EDIT")

        edit_bone_table = []
        bone_names = []

        for i, node in enumerate(shape.nodes):
            bone = root_arm.edit_bones.new(shape.names[node.name])
            # bone.use_connect = True
            bone.head = node.head
            bone.tail = node.tail

            if node.parent != -1:
                bone.parent = edit_bone_table[node.parent]
            
            bone.matrix = node.mat
            bone["nodeIndex"] = i

            edit_bone_table.append(bone)
            bone_names.append(bone.name)
        
        bpy.ops.object.mode_set(mode="OBJECT")
    else:
        if reference_keyframe:
            reference_marker = context.scene.timeline_markers.get("reference")
            if reference_marker is None:
                reference_frame = 0
                context.scene.timeline_markers.new("reference", reference_frame)
            else:
                reference_frame = reference_marker.frame
        else:
            reference_frame = None
        
        # Create an empty for every node
        for i, node in enumerate(shape.nodes):
            ob = bpy.data.objects.new(dedup_name(bpy.data.objects, shape.names[node.name]), None)
            ob["nodeIndex"] = i
            ob.empty_draw_type = "SINGLE_ARROW"
            ob.empty_draw_size = 0.5

            if node.parent != -1:
                ob.parent = node_obs[node.parent]

            ob.location = shape.default_translations[i]
            ob.rotation_mode = "QUATERNION"
            ob.rotation_quaternion = shape.default_rotations[i]

            context.scene.objects.link(ob)
            node_obs.append(ob)
            node_obs_val[node] = ob

            if reference_keyframe:
                curves = ob_location_curves(ob)
                for curve in curves:
                    curve.keyframe_points.add(1)
                    key = curve.keyframe_points[-1]
                    key.interpolation = "LINEAR"
                    key.co = (reference_frame, ob.location[curve.array_index])
                
                curves = ob_scale_curves(ob)
                for curve in curves:
                    curve.keyframe_points.add(1)
                    key = curve.keyframe_points[-1]
                    key.interpolation = "LINEAR"
                    key.co = (reference_frame, ob.scale[curve.array_index])
                
                _, curves = ob_rotation_curves(ob)
                for curve in curves:
                    curve.keyframe_points.add(1)
                    key = curve.keyframe_points[-1]
                    key.interpolation = "LINEAR"
                    key.co = (reference_frame, ob.rotation_quaternion[curve.array_index])
    
    # Try animation?
    if import_sequences:
        globalToolIndex = 10
        fps = context.scene.render.fps

        sequences_text = []

        for seq in shape.sequences:
            name = shape.names[seq.nameIndex]
            print("Importing sequence", name)

            flags = []
            flags.append("priority {}".format(seq.priority))

            if seq.flags & Sequence.Cyclic:
                flags.append("cyclic")

            if seq.flags & Sequence.Blend:
                flags.append("blend")

            if flags:
                sequences_text.append(name + ": " + ", ".join(flags))

            nodesRotation = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(shape.nodes, seq.rotationMatters))))
            nodesTranslation = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(shape.nodes, seq.translationMatters))))
            nodesScale = tuple(map(lambda p: p[0], filter(lambda p: p[1], zip(shape.nodes, seq.scaleMatters))))

            step = 1

            for mattersIndex, node in enumerate(nodesTranslation):
                ob = node_obs_val[node]
                curves = ob_location_curves(ob)

                for frameIndex in range(seq.numKeyframes):
                    vec = shape.node_translations[seq.baseTranslation + mattersIndex * seq.numKeyframes + frameIndex]
                    if seq.flags & Sequence.Blend:
                        if reference_frame is None:
                            return fail(operator, "Missing 'reference' marker for blend animation '{}'".format(name))
                        ref_vec = Vector(evaluate_all(curves, reference_frame))
                        vec = ref_vec + vec

                    for curve in curves:
                        curve.keyframe_points.add(1)
                        key = curve.keyframe_points[-1]
                        key.interpolation = "LINEAR"
                        key.co = (
                            globalToolIndex + frameIndex * step,
                            vec[curve.array_index])

            for mattersIndex, node in enumerate(nodesRotation):
                ob = node_obs_val[node]
                mode, curves = ob_rotation_curves(ob)

                for frameIndex in range(seq.numKeyframes):
                    rot = shape.node_rotations[seq.baseRotation + mattersIndex * seq.numKeyframes + frameIndex]
                    if seq.flags & Sequence.Blend:
                        if reference_frame is None:
                            return fail(operator, "Missing 'reference' marker for blend animation '{}'".format(name))
                        ref_rot = Quaternion(evaluate_all(curves, reference_frame))
                        rot = ref_rot * rot
                    if mode != "QUATERNION":
                        rot = rot.to_euler(mode)

                    for curve in curves:
                        curve.keyframe_points.add(1)
                        key = curve.keyframe_points[-1]
                        key.interpolation = "LINEAR"
                        key.co = (
                            globalToolIndex + frameIndex * step,
                            rot[curve.array_index])

            for mattersIndex, node in enumerate(nodesScale):
                ob = node_obs_val[node]
                curves = ob_scale_curves(ob)

                for frameIndex in range(seq.numKeyframes):
                    index = seq.baseScale + mattersIndex * seq.numKeyframes + frameIndex
                    vec = shape.node_translations[seq.baseTranslation + mattersIndex * seq.numKeyframes + frameIndex]

                    if seq.flags & Sequence.UniformScale:
                        s = shape.node_uniform_scales[index]
                        vec = (s, s, s)
                    elif seq.flags & Sequence.AlignedScale:
                        vec = shape.node_aligned_scales[index]
                    elif seq.flags & Sequence.ArbitraryScale:
                        print("Warning: Arbitrary scale animation not implemented")
                        break
                    else:
                        print("Warning: Invalid scale flags found in sequence")
                        break

                    for curve in curves:
                        curve.keyframe_points.add(1)
                        key = curve.keyframe_points[-1]
                        key.interpolation = "LINEAR"
                        key.co = (
                            globalToolIndex + frameIndex * step,
                            vec[curve.array_index])

            context.scene.timeline_markers.new(name + ":start", globalToolIndex)
            context.scene.timeline_markers.new(name + ":end", globalToolIndex + seq.numKeyframes * step)
            globalToolIndex += seq.numKeyframes * step + 30

        if "Sequences" in bpy.data.texts:
            sequences_buf = bpy.data.texts["Sequences"]
        else:
            sequences_buf = bpy.data.texts.new("Sequences")

        sequences_buf.from_string("\n".join(sequences_text))

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
            bobj = bpy.data.objects.new(dedup_name(bpy.data.objects, shape.names[obj.name]), bmesh)
            context.scene.objects.link(bobj)

            if obj.node != -1:
                if use_armature:
                    bobj.parent = root_ob
                    bobj.parent_bone = bone_names[obj.node]
                    bobj.parent_type = "BONE"
                    bobj.matrix_world = shape.nodes[obj.node].mat
                else:
                    bobj.parent = node_obs[obj.node]

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
