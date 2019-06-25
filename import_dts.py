import bpy
import os
from bpy_extras.io_utils import unpack_list
from bpy_extras import node_shader_utils

from .DtsShape import DtsShape
from .DtsTypes import *
from .write_report import write_debug_report
from .util import default_materials, resolve_texture, get_rgb_colors, fail, \
    ob_location_curves, ob_scale_curves, ob_rotation_curves, ob_rotation_data, evaluate_all

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

def file_base_name(filepath):
    return os.path.basename(filepath).rsplit(".", 1)[0]

def import_material(dmat, filepath):
    bmat = bpy.data.materials.new(dedup_name(bpy.data.materials, dmat.name))

    wrap = node_shader_utils.PrincipledBSDFWrapper(bmat, is_readonly=False)

    texname = resolve_texture(filepath, dmat.name)
    teximg = None

    if dmat.flags & Material.SWrap and dmat.flags & Material.TWrap:
        texture_extension = "REPEAT" # The default, as well
    elif dmat.flags & Material.SWrap or dmat.flags & Material.TWrap:
        texture_extension = "REPEAT" # Not trivially supported by Blender
    else:
        texture_extension = "EXTEND"

    if texname is not None:
        try:
            teximg = bpy.data.images.load(texname)
        except:
            print("Cannot load image", texname)
            teximg = None

        wrap.base_color_texture.image = teximg
        wrap.base_color_texture.texcoords = "UV"
        wrap.base_color_texture.extension = texture_extension

        # Try to figure out a diffuse color for solid shading
        if teximg.size[0] <= 16 and teximg.size[1] <= 16:
            pixels = grouper(teximg.pixels, teximg.channels)
            color = pixels.__next__()

            for other in pixels:
                if other != color:
                    break
            else:
                if teximg.channels == 3 or teximg.channels == 4:
                    bmat.diffuse_color = (color[0], color[1], color[2], 1.0)
    elif dmat.name.lower() in default_materials:
        wrap.base_color = default_materials[dmat.name.lower()]
        pass

    if dmat.flags & Material.Translucent:
        if teximg is not None and teximg.channels == 4:
            wrap.alpha_texture.image = teximg
            wrap.alpha_texture.texcoords = "UV"

    return bmat

#class Material:
#        SWrap            = 0x00000001 - check
#        TWrap            = 0x00000002 - check
#        Translucent      = 0x00000004 - check
#        Additive         = 0x00000008 - check?
#        Subtractive      = 0x00000010 - check?
#        SelfIlluminating = 0x00000020 - check
#        NeverEnvMap      = 0x00000040
#        NoMipMap         = 0x00000080
#        MipMapZeroBorder = 0x00000100
#        IFLMaterial      = 0x08000000
#        IFLFrame         = 0x10000000
#        DetailMap        = 0x20000000
#        BumpMap          = 0x40000000
#        ReflectanceMap   = 0x80000000
#        AuxiliaryMask    = 0xE0000000
def import_material(dmat, filepath):
    mat = bpy.data.materials.new(dedup_name(bpy.data.materials, dmat.name))
    mat.use_nodes = True

    node_tree = mat.node_tree
    nodes = node_tree.nodes
    links = node_tree.links

    node_out = nodes["Material Output"]
    node_principled = nodes["Principled BSDF"]

    image = None
    image_path = resolve_texture(filepath, dmat.name)

    if image_path is not None:
        try:
            image = bpy.data.images.load(image_path)
        except:
            print("Failed to load image", image_path)

    if dmat.flags & Material.SWrap and dmat.flags & Material.TWrap:
        texture_extension = "REPEAT" # The default, as well
    elif dmat.flags & Material.SWrap or dmat.flags & Material.TWrap:
        print("Warning: DTS material '{}' uses single axis texture extension, which is not supported by Blender".format(dmat.name))
        texture_extension = "REPEAT" # Not trivially supported by Blender
    else:
        texture_extension = "EXTEND"

    node_texture = nodes.new("ShaderNodeTexImage")
    node_texture.label = "Source Texture"
    node_texture.image = image
    node_texture.extension = texture_extension
    node_texture.location = (-600, 300)
    node_mix_texture = nodes.new("ShaderNodeMixRGB")
    node_mix_texture.label = "Colorshift"
    node_mix_texture.location = (-200, 300)
    node_mix_texture.inputs["Color1"].default_value = (1, 1, 1, 1)
    links.new(node_texture.outputs["Color"], node_mix_texture.inputs["Color2"])
    links.new(node_texture.outputs["Alpha"], node_mix_texture.inputs["Fac"])
    color_socket = node_mix_texture.outputs["Color"]

    if dmat.flags & Material.Translucent:
        if dmat.flags & Material.Additive:
            mat.torque_props.blend_mode = "ADDITIVE"
            mat.blend_method = "ADDITIVE"
            node_rgb_to_bw = nodes.new("ShaderNodeRGBToBW")
            links.new(node_texture.outputs["Color"], node_rgb_to_bw.inputs["Color"])
            alpha_output = node_rgb_to_bw.outputs["Val"]
        elif dmat.flags & Material.Subtractive:
            mat.torque_props.blend_mode = "SUBTRACTIVE"
            mat.blend_method = "ADDITIVE" # TODO: Figure out how to do subtractive in Blender
            node_rgb_to_bw = nodes.new("ShaderNodeRGBToBW")
            node_math = nodes.new("ShaderNodeMath")
            node_math.operation = "SUBTRACT"
            node_math.inputs[0].default_value = 1.0
            links.new(node_texture.outputs["Color"], node_rgb_to_bw.inputs["Color"])
            links.new(node_rgb_to_bw.outputs["Val"], node_math.inputs[1])
            alpha_output = node_math.outputs["Value"]
        else:
            mat.torque_props.blend_mode = "TRANSLUCENT"
            mat.blend_method = "BLEND"
            alpha_output = node_texture.outputs["Alpha"]

        mat.shadow_method = "NONE"
        links.new(alpha_output, node_principled.inputs["Alpha"])
    else:
        mat.torque_props.blend_mode = "OPAQUE"

    if dmat.flags & Material.SelfIlluminating:
        links.new(color_socket, node_principled.inputs["Emission"])
    else:
        links.new(color_socket, node_principled.inputs["Base Color"])

    #####
    if dmat.flags & Material.IFLMaterial:
        mat.torque_props.use_ifl = True

    # TODO: MipMapZeroBorder, IFLFrame, DetailMap, BumpMap, ReflectanceMap
    # AuxilaryMask?
    #####

    return mat

class index_pass:
    def __getitem__(self, item):
        return item

def create_bmesh(dmesh, materials, shape):
    me = bpy.data.meshes.new("")

    faces = []
    material_indices = {}

    indices_pass = index_pass()
    print(f"Imported mesh #primitives={len(dmesh.primitives)} #indices={len(dmesh.indices)} #verts={len(dmesh.verts)}")

    for prim in dmesh.primitives:
        if prim.type & Primitive.Indexed:
            indices = dmesh.indices
        else:
            indices = indices_pass

        dmat = None
        print(f"Imported mesh primitive firstElement={prim.firstElement} numElements={prim.numElements}")

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

    uvs = me.uv_layers.new()

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

def insert_reference(frame, shape_nodes):
    for node in shape_nodes:
        ob = node.bl_ob

        curves = ob_location_curves(ob)
        for curve in curves:
            curve.keyframe_points.add(1)
            key = curve.keyframe_points[-1]
            key.interpolation = "LINEAR"
            key.co = (frame, ob.location[curve.array_index])

        curves = ob_scale_curves(ob)
        for curve in curves:
            curve.keyframe_points.add(1)
            key = curve.keyframe_points[-1]
            key.interpolation = "LINEAR"
            key.co = (frame, ob.scale[curve.array_index])

        _, curves = ob_rotation_curves(ob)
        rot = ob_rotation_data(ob)
        for curve in curves:
            curve.keyframe_points.add(1)
            key = curve.keyframe_points[-1]
            key.interpolation = "LINEAR"
            key.co = (frame, rot[curve.array_index])

def read_shape(filepath, debug_report):
    shape = DtsShape()

    with open(filepath, "rb") as fd:
        shape.load(fd)

    if debug_report:
        write_debug_report(filepath + ".txt", shape)
        with open(filepath + ".pass.dts", "wb") as fd:
            shape.save(fd)

    return shape

# Create a Blender material for each DTS material
def import_materials_to_dict(filepath, shape):
    materials = {}

    for dmat in shape.materials:
        materials[dmat] = import_material(dmat, filepath)

    return materials

def assign_ifl_material_names(shape, material_map):
    for ifl in shape.iflmaterials:
        mat = material_map[shape.materials[ifl.slot]]
        assert mat.torque_props.use_ifl == True
        mat.torque_props.ifl_name = shape.names[ifl.name]

def create_bounds(bounds):
    me = bpy.data.meshes.new("")
    me.vertices.add(8)
    me.vertices[0].co = (bounds.min.x, bounds.min.y, bounds.min.z)
    me.vertices[1].co = (bounds.max.x, bounds.min.y, bounds.min.z)
    me.vertices[2].co = (bounds.max.x, bounds.max.y, bounds.min.z)
    me.vertices[3].co = (bounds.min.x, bounds.max.y, bounds.min.z)
    me.vertices[4].co = (bounds.min.x, bounds.min.y, bounds.max.z)
    me.vertices[5].co = (bounds.max.x, bounds.min.y, bounds.max.z)
    me.vertices[6].co = (bounds.max.x, bounds.max.y, bounds.max.z)
    me.vertices[7].co = (bounds.min.x, bounds.max.y, bounds.max.z)
    me.validate()
    me.update()
    ob = bpy.data.objects.new("bounds", me)
    ob.display_type = "BOUNDS"
    ob.hide_render = True
    return ob

def load(operator, context, filepath,
         reference_keyframe=True,
         import_sequences=True,
         use_armature=False,
         debug_report=False):
    shape = read_shape(filepath, debug_report)
    materials = import_materials_to_dict(filepath, shape)
    assign_ifl_material_names(shape, materials)

    root_collection = bpy.data.collections.new(file_base_name(filepath))
    context.scene.collection.children.link(root_collection)

    node_collection = bpy.data.collections.new("Nodes")

    # First load all the nodes into armatures
    lod_by_mesh = {}

    for lod in shape.detail_levels:
        lod_by_mesh[lod.objectDetail] = lod

    node_obs = []
    node_obs_val = {}

    if use_armature:
        root_arm = bpy.data.armatures.new("")
        root_ob = bpy.data.objects.new(file_base_name(filepath), root_arm)

        root_collection.objects.link(root_ob)

        # Calculate armature-space matrix, head and tail for each node
        for i, node in enumerate(shape.nodes):
            node.mat = shape.default_rotations[i].to_matrix()
            node.mat = Matrix.Translation(shape.default_translations[i]) @ node.mat.to_4x4()
            if node.parent != -1:
                node.mat = shape.nodes[node.parent].mat @ node.mat
            # node.head = node.mat.to_translation()
            # node.tail = node.head + Vector((0, 0, 0.25))
            # node.tail = node.mat.to_translation()
            # node.head = node.tail - Vector((0, 0, 0.25))

        context.view_layer.objects.active = root_ob
        bpy.ops.object.mode_set(mode="EDIT", toggle=False)

        edit_bone_table = []
        bone_names = []

        for i, node in enumerate(shape.nodes):
            bone = root_arm.edit_bones.new(shape.names[node.name])
            # bone.use_connect = True
            # bone.head = node.head
            # bone.tail = node.tail
            bone.head = (0, 0, -0.25)
            bone.tail = (0, 0, 0)

            if node.parent != -1:
                bone.parent = edit_bone_table[node.parent]

            bone.matrix = node.mat
            bone["nodeIndex"] = i

            edit_bone_table.append(bone)
            bone_names.append(bone.name)

        bpy.ops.object.mode_set(mode="OBJECT", toggle=False)
    else:
        if reference_keyframe:
            reference_marker = context.scene.timeline_markers.get("reference")
            if reference_marker is None:
                reference_marker = context.scene.timeline_markers.new("reference", frame=0)
            reference_frame = reference_marker.frame
        else:
            reference_frame = None

        # Create an empty for every node
        for i, node in enumerate(shape.nodes):
            ob = bpy.data.objects.new(dedup_name(bpy.data.objects, shape.names[node.name]), None)
            node.bl_ob = ob
            ob["nodeIndex"] = i
            ob.empty_display_type = "SINGLE_ARROW"
            ob.empty_display_size = 0.5

            if node.parent != -1:
                ob.parent = node_obs[node.parent]

            ob.location = shape.default_translations[i]
            ob.rotation_mode = "QUATERNION"
            ob.rotation_quaternion = shape.default_rotations[i]
            if shape.names[node.name] == "__auto_root__" and ob.rotation_quaternion.magnitude == 0:
                ob.rotation_quaternion = (1, 0, 0, 0)

            node_collection.objects.link(ob)
            node_obs.append(ob)
            node_obs_val[node] = ob

        if reference_keyframe:
            insert_reference(reference_frame, shape.nodes)

    if node_collection.objects:
        root_collection.children.link(node_collection)

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

            flags.append("duration {}".format(seq.duration))

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
                    if mode == 'AXIS_ANGLE':
                        rot = rot.to_axis_angle()
                    elif mode != 'QUATERNION':
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

            # Insert a reference frame immediately before the animation
            # insert_reference(globalToolIndex - 2, shape.nodes)

            context.scene.timeline_markers.new(name + ":start", frame=globalToolIndex)
            context.scene.timeline_markers.new(name + ":end", frame=globalToolIndex + seq.numKeyframes * step - 1)
            globalToolIndex += seq.numKeyframes * step + 30

        if "Sequences" in bpy.data.texts:
            sequences_buf = bpy.data.texts["Sequences"]
        else:
            sequences_buf = bpy.data.texts.new("Sequences")

        sequences_buf.from_string("\n".join(sequences_text))

    # Then put objects in the armatures
    for obj in shape.objects:
        if obj.node == -1:
            print('Warning: Object {} is not attached to a node, ignoring'
                  .format(shape.names[obj.name]))
            continue

        for meshIndex in range(obj.numMeshes):
            mesh = shape.meshes[obj.firstMesh + meshIndex]
            mtype = mesh.type

            if mtype == Mesh.NullType:
                continue

            if mtype != Mesh.StandardType and mtype != Mesh.SkinType:
                print('Warning: Mesh #{} of object {} is of unsupported type {}, ignoring'.format(
                    meshIndex + 1, mtype, shape.names[obj.name]))
                continue

            bmesh = create_bmesh(mesh, materials, shape)
            bobj = bpy.data.objects.new(dedup_name(bpy.data.objects, shape.names[obj.name]), bmesh)

            lod_name = shape.names[lod_by_mesh[meshIndex].name]

            lod_collection_name = "LOD " + lod_name
            lod_collection = bpy.data.collections.get(lod_collection_name)
            if lod_collection is None:
                lod_collection = bpy.data.collections.new(lod_collection_name)
                root_collection.children.link(lod_collection)

            lod_collection.objects.link(bobj)

            add_vertex_groups(mesh, bobj, shape)

            if use_armature:
                bobj.parent = root_ob
                bobj.parent_bone = bone_names[obj.node]
                bobj.parent_type = "BONE"
                bobj.matrix_world = shape.nodes[obj.node].mat

                if mtype == Mesh.SkinType:
                    modifier = bobj.modifiers.new('Armature', 'ARMATURE')
                    modifier.object = root_ob
            else:
                bobj.parent = node_obs[obj.node]

    root_collection.objects.link(create_bounds(shape.bounds))

    return {"FINISHED"}

def add_vertex_groups(mesh, ob, shape):
    for node, initial_transform in mesh.bones:
        # TODO: Handle initial_transform
        ob.vertex_groups.new(shape.names[shape.nodes[node].name])

    for vertex, bone, weight in mesh.influences:
        ob.vertex_groups[bone].add((vertex,), weight, 'REPLACE')
