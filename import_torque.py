import os
from collections import namedtuple

import bpy
from bpy_extras.io_utils import unpack_list
from mathutils import Quaternion, Matrix
from typing import List
from itertools import repeat

if "dts" in locals():
    import importlib
    importlib.reload(dts)

from . import dts

def filebase(filepath: str) -> str:
    return os.path.basename(filepath).rsplit(".", 1)[0]

def load(context,
         filepath: str,
         ):
    with open(filepath, "rb") as f:
        shape = dts.read_dts(f)

    armature, bone_data = load_armature(context, filepath, shape)

    lod_by_mesh = {}

    for detail in shape.details:
        lod_by_mesh[detail.object_detail_num] = detail

    for dts_obj in shape.objects:
        obj_name = shape.names[dts_obj.name_index]

        if dts_obj.node_index == -1:
            print(f"Skipping object {obj_name}: Not attached to a node")
            continue

        for mesh_index in range(dts_obj.num_meshes):
            mesh = shape.meshes[dts_obj.start_mesh_index + mesh_index]

            if mesh is None:
                continue

            if mesh.type != dts.StandardMeshType:
                print(f"Skipping mesh {mesh_index} of object {obj_name}: Unhandled mesh type {mesh.type}")
                continue

            detail = lod_by_mesh.get(mesh_index)

            if detail is None:
                print(f"Skipping mesh {mesh_index} of object {obj_name}: No matching detail level")
                continue

            bl_mesh = load_mesh(shape, mesh)
            bl_ob = bpy.data.objects.new(obj_name, bl_mesh)

            lod_coll_name = f"LOD {shape.names[detail.name_index]}"
            lod_coll = bpy.data.collections.get(lod_coll_name)

            if lod_coll is None:
                lod_coll = bpy.data.collections.new(lod_coll_name)
                context.scene.collection.children.link(lod_coll)

            lod_coll.objects.link(bl_ob)

            bl_ob.parent = armature
            bl_ob.parent_bone = bone_data[dts_obj.node_index].name
            bl_ob.parent_type = "BONE"
            bl_ob.matrix_world = bone_data[dts_obj.node_index].matrix

            print(f"Object {obj_name} in {lod_coll_name} got name {bl_ob.name}")

            if mesh.type == dts.SkinMeshType:
                modifier = bl_ob.modifiers.new("Armature", "ARMATURE")
                modifier.object = armature

    for seq in shape.sequences:
        load_sequence(context, shape, seq, bone_data, armature)

    return {'FINISHED'}

NodeBoneData = namedtuple("NodeBoneData", ("name", "matrix"))

def load_armature(context, filepath: str, shape: dts.Shape):
    armature_data = bpy.data.armatures.new("")
    armature_object = bpy.data.objects.new(filebase(filepath), armature_data)
    context.scene.collection.objects.link(armature_object)
    context.view_layer.objects.active = armature_object
    bpy.ops.object.mode_set(mode="EDIT", toggle=False)

    node_index_to_edit_bone = []
    bone_data = []

    for i, node in enumerate(shape.nodes):
        bone = armature_data.edit_bones.new(shape.names[node.name_index])
        bone.head = (0, 0, -0.25)
        bone.tail = (0, 0, 0)

        mat = quat_dts_to_bl(shape.default_rotations[i]).to_matrix()
        mat = Matrix.Translation(shape.default_translations[i]) @ mat.to_4x4()

        if node.parent_index != -1:
            parent_node = shape.nodes[node.parent_index]
            parent_bone = node_index_to_edit_bone[node.parent_index]
            bone.parent = parent_bone
            mat = parent_bone.matrix @ mat

        bone.matrix = mat

        node_index_to_edit_bone.append(bone)
        bone_data.append(NodeBoneData(bone.name, bone.matrix))

    num_edit = len(armature_data.edit_bones)

    bpy.ops.object.mode_set(mode="OBJECT", toggle=False)

    num_real = len(armature_data.bones)

    assert num_real == len(shape.nodes), "Blender 'remove zero sized bones' messed up the armature"

    return armature_object, bone_data

def load_mesh(shape: dts.Shape, dm: dts.Mesh):
    bm = bpy.data.meshes.new("")

    bm.vertices.add(len(dm.verts))
    bm.vertices.foreach_set("co", unpack_list(dm.verts))
    bm.vertices.foreach_set("normal", unpack_list(dm.normals))

    faces = []

    for prim in dm.primitives:
        if prim.type & dts.PrimitiveIndexed:
            indices = dm.indices
        else:
            indices = IndexPass

        dmat = None

        if prim.type & dts.PrimitiveStrip:
            even = True
            for i in range(prim.first_element+2, prim.first_element+prim.num_elements):
                if even:
                    faces.append(((indices[i], indices[i-1], indices[i-2]), dmat))
                else:
                    faces.append(((indices[i-2], indices[i-1], indices[i]), dmat))
                even = not even
        elif prim.type & dts.PrimitiveFan:
            even = True
            for i in range(prim.first_element+2, prim.first_element+prim.num_elements):
                if even:
                    faces.append(((indices[i], indices[i-1], indices[0]), dmat))
                else:
                    faces.append(((indices[0], indices[i-1], indices[i]), dmat))
        else: # prim.type & dts.PrimitiveTriangles
            for i in range(prim.first_element+2, prim.first_element + prim.num_elements, 3):
                faces.append(((indices[i], indices[i-1], indices[i-2]), dmat))

    bm.polygons.add(len(faces))
    bm.loops.add(3 * len(faces))

    uvs = bm.uv_layers.new()

    for i, ((verts, dmat), poly) in enumerate(zip(faces, bm.polygons)):
        poly.use_smooth = True
        poly.loop_total = 3
        poly.loop_start = 3 * i

        # material

        for j, index in zip(poly.loop_indices, verts):
            bm.loops[j].vertex_index = index
            uv = dm.tverts[index]
            uvs.data[j].uv = (uv[0], 1 - uv[1])

    bm.validate()
    bm.update()

    return bm

def load_sequence(context, shape: dts.Shape, seq: dts.Sequence, bone_data: List[NodeBoneData], armature):
    action = bpy.data.actions.new(shape.names[seq.name_index])
    action.use_fake_user = True
    action.id_root = 'OBJECT'

    # If none yet assigned, assign this action to the armature.
    if not armature.animation_data:
        armature.animation_data_create()
    if not armature.animation_data.action:
        armature.animation_data.action = action

    fps = context.scene.render.fps
    frame_start = 1
    frame_step = fps * (seq.duration / seq.num_keyframes)
    frame_end = frame_start + seq.num_keyframes * frame_step

    translation_index = seq.base_rotation
    rotation_index = seq.base_translation
    scale_index = seq.base_scale

    for node_index, node in enumerate(shape.nodes):
        if node_index not in seq.rotation_matters:
            continue

        pose_bone = armature.pose.bones[bone_data[node_index].name]

        values = [quat_dts_to_bl(shape.node_rotations[i])
            for i in range(rotation_index, rotation_index + seq.num_keyframes)]
        rotation_index += len(values)

        for channel in range(4):
            curve = action.fcurves.new(
                data_path=pose_bone.path_from_id("rotation_quaternion"),
                index=channel,
                action_group=shape.names[node.name_index])
            curve.keyframe_points.add(seq.num_keyframes)

            # Set F-Curve points
            seq_inner = ((
                frame_start + frame * frame_step,
                values[frame][channel],
            ) for frame in range(seq.num_keyframes))
            cos = [x for sub in seq_inner for x in sub]
            curve.keyframe_points.foreach_set("co", cos)

            # Set interpolation modes
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"

        # TODO: Use .fcurves.add(N) and .foreach_set(..)

        #curves = [
        #    action.fcurves.new(
        #        data_path=pose_bone.path_from_id("rotation_quaternion"),
        #        index=index,
        #        )#action_group=shape.names[node.name_index])
        #    for index in range(4)]

        #for frame_index in range(seq.num_keyframes):
        #    value = quat_dts_to_bl(shape.node_rotations[rotation_index])
        #    rotation_index += 1
        #    for curve in curves:
        #        keyframe = curve.keyframe_points.insert(
        #            frame=frame_start + frame_index * frame_step,
        #            value=value[curve.array_index])
        #        keyframe.interpolation = "LINEAR"

        #curve.convert_to_samples(frame_start, frame_end)
        #curve.convert_to_keyframes(frame_start, frame_end)

def quat_dts_to_bl(quat: dts.DtsQuat) -> Quaternion:
    (x, y, z, nw) = quat
    return Quaternion((-nw, x, y, z))

class IndexPass:
    def __getitem__(self, item):
        return item

