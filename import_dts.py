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

blockhead_nodes = ("HeadSkin", "chest", "Larm", "Lhand", "Rarm", "Rhand", "pants", "LShoe", "RShoe")

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

def get_node_head(i, node, shape):
    return node.mat.to_translation()

def get_node_tail(i, node, shape):
    # ischildfound = False
    # childbone = None
    # childbonelist = []
    # for j, other in enumerate(shape.nodes):
    #     if other.parent == i:
    #         ischildfound = True
    #         childbone = other
    #         childbonelist.append(other)
    #
    # if ischildfound:
    #     tmp_head = Vector((0, 0, 0))
    #     for other in childbonelist:
    #         tmp_head[0] += other.head[0]
    #         tmp_head[1] += other.head[1]
    #         tmp_head[2] += other.head[2]
    #     tmp_head[0] /= len(childbonelist)
    #     tmp_head[1] /= len(childbonelist)
    #     tmp_head[2] /= len(childbonelist)
    #     return tmp_head
    # elif node.parent != -1:
    #     parent = shape.nodes[node.parent]
    #
    #     tmp_len = 0.0
    #     tmp_len += (node.head[0] - parent.head[0]) ** 2
    #     tmp_len += (node.head[1] - parent.head[1]) ** 2
    #     tmp_len += (node.head[2] - parent.head[2]) ** 2
    #     tmp_len = tmp_len ** 0.5 * 0.5
    #
    #     return Vector((
    #         node.head[0] + tmp_len * node.mat[0][0],
    #         node.head[1] + tmp_len * node.mat[1][0],
    #         node.head[2] + tmp_len * node.mat[2][0]))
    # else:
    return node.head + Vector((0, 0, 0.25))

def file_base_name(filepath):
    return os.path.basename(filepath).rsplit(".", 1)[0]

def load(operator, context, filepath,
         hide_default_player=False,
         import_node_order=False,
         reference_keyframe=False,
         import_sequences=True,
         debug_report=False,
         hacky_new_bone_connect=True):
    shape = DtsShape()

    with open(filepath, "rb") as fd:
        shape.load(fd)

    if debug_report:
        write_debug_report(filepath + ".txt", shape)
        with open(filepath + ".pass.dts", "wb") as fd:
            shape.save(fd)
    
    root_arm = bpy.data.armatures.new(file_base_name(filepath))
    root_ob = bpy.data.objects.new(root_arm.name, root_arm)

    context.scene.objects.link(root_ob)
    context.scene.objects.active = root_ob

    root_ob.show_x_ray = True

    # Preprocess our bones with magic spice?
    for i, node in enumerate(shape.nodes):
        node.mat = shape.default_rotations[i].to_matrix()
        node.mat = Matrix.Translation(shape.default_translations[i]) * node.mat.to_4x4()

        if node.parent != -1:
            node.mat = shape.nodes[node.parent].mat * node.mat

    for i, node in enumerate(shape.nodes):
        node.head = get_node_head(i, node, shape)

    for i, node in enumerate(shape.nodes):
        node.tail = get_node_tail(i, node, shape)

    bpy.ops.object.mode_set(mode="EDIT")

    edit_bone_table = []
    bone_names = []

    for i, node in enumerate(shape.nodes):
        bone = root_arm.edit_bones.new(shape.names[node.name])

        if hacky_new_bone_connect:
            bone.use_connect = True
        
        bone.head = node.head
        bone.tail = node.tail
        
        if node.parent != -1:
            parent_bone = edit_bone_table[node.parent]
            bone.parent = parent_bone
        
        bone.matrix = node.mat

        edit_bone_table.append(bone)
        bone_names.append(bone.name)

    bpy.ops.object.mode_set(mode="OBJECT")

    materials = {}
    color_source = get_rgb_colors()

    for dmat in shape.materials:
        materials[dmat] = import_material(color_source, dmat, filepath)

    # Now assign IFL material properties where needed
    for ifl in shape.iflmaterials:
        mat = materials[shape.materials[ifl.slot]]
        assert mat["ifl"] == True
        mat["iflName"] = shape.names[ifl.name]
        mat["iflFirstFrame"] = ifl.firstFrame
        mat["iflNumFrames"] = ifl.numFrames
        mat["iflTime"] = ifl.time

    detail_by_index = {}

    for lod in shape.detail_levels:
        detail_by_index[lod.objectDetail] = lod

    for obj in shape.objects:
        if shape.names[obj.name] not in blockhead_nodes:
            continue

        for index in range(obj.numMeshes):
            mesh = shape.meshes[obj.firstMesh + index]

            if mesh.type == Mesh.NullType:
                continue

            if mesh.type != Mesh.StandardType:
                print("{} is a {} mesh, unsupported, but trying".format(
                    shape.names[obj.name], mesh.type))
                # continue

            bmesh = create_bmesh(mesh, materials, shape)
            bobj = bpy.data.objects.new(shape.names[obj.name], bmesh)
            context.scene.objects.link(bobj)

            if obj.node != -1:
                bobj.parent = root_ob
                bobj.parent_bone = bone_names[obj.node]
                bobj.parent_type = "BONE"
                bobj.matrix_world = shape.nodes[obj.node].mat

            if shape.names[obj.name] not in blockhead_nodes:
                bobj.hide = True

            lod_name = shape.names[detail_by_index[index].name]

            if lod_name not in bpy.data.groups:
                bpy.data.groups.new(lod_name)

            bpy.data.groups[lod_name].objects.link(bobj)

    return {"FINISHED"}