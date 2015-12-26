import bpy
import mathutils
import os
from bpy_extras.io_utils import unpack_list

from .DtsShape import DtsShape
from .DtsTypes import *
from .write_report import write_debug_report

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
         hide_default_player=False,
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
    nodes = [] # For accessing indices when parenting later

    lod_by_mesh = {}

    for lod in shape.detail_levels:
        lod_by_mesh[lod.objectDetail] = lod

    if "NodeOrder" in bpy.data.texts:
        order_buf = bpy.data.texts["NodeOrder"]
    else:
        order_buf = bpy.data.texts.new("NodeOrder")

    order_buf.from_string("\n".join(shape.names[node.name] for node in shape.nodes))

    for i, node in enumerate(shape.nodes):
        amt = bpy.data.armatures.new(shape.names[node.name])
        bnode = bpy.data.objects.new(name=shape.names[node.name], object_data=amt)
        bnode.location = mathutils.Vector(shape.default_translations[i].tuple())

        bnode.rotation_mode = "QUATERNION"
        # weird representation difference -wxyz vs xyzw
        bnode.rotation_quaternion = mathutils.Quaternion((
            -shape.default_rotations[i].w,
            shape.default_rotations[i].x,
            shape.default_rotations[i].y,
            shape.default_rotations[i].z
        ))

        context.scene.objects.link(bnode)
        nodes.append((node, bnode, i))

    # Now set all the parents appropriately
    for node, bnode, nodei in nodes:
        if node.parent != -1:
            bnode.parent = nodes[node.parent][1]

    # Then put objects in the armatures
    for obj in shape.objects:
        for meshIndex in range(obj.numMeshes):
            mesh = shape.meshes[obj.firstMesh + meshIndex]

            if mesh.type == MeshType.Null:
                continue

            if mesh.type != MeshType.Standard:
                print("{} is a {} mesh, skipping due to lack of support".format(
                    shape.names[obj.name], mesh.type.name))
                continue

            bmesh = create_bmesh(mesh, materials, shape)
            bobj = bpy.data.objects.new(name=shape.names[obj.name], object_data=bmesh)
            context.scene.objects.link(bobj)

            if obj.node != -1:
                bobj.parent = nodes[obj.node][1]

            if hide_default_player and shape.names[obj.name] not in blockhead_nodes:
                bobj.hide = True

            lod_name = shape.names[lod_by_mesh[meshIndex].name]

            if lod_name not in bpy.data.groups:
                bpy.data.groups.new(lod_name)

            bpy.data.groups[lod_name].objects.link(bobj)

    return {"FINISHED"}
