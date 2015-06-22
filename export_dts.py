import bpy, bmesh
from math import sqrt

from .DtsShape import DtsShape
from .DtsTypes import *

def save(operator, context, filepath,
         use_selection=True,
         blank_material=True,
         force_flatshade=True):
    scene = context.scene

    if use_selection:
        objects = context.selected_objects
    else:
        objects = scene.objects

    shape = DtsShape()

    poly_count = 0
    smin = [0, 0, 0]
    smax = [0, 0, 0]

    material_lookup = {}
    blank_material_index = None

    for bobj in objects:
        if bobj.type != "MESH":
            print("skipping " + bobj.name)
            continue

        if force_flatshade:
            # Hack in flatshading
            scene.objects.active = bobj
            bpy.ops.object.modifier_add(type="EDGE_SPLIT")
            bobj.modifiers[-1].split_angle = 0

        mesh = bobj.to_mesh(scene, force_flatshade, "PREVIEW")
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()

        if force_flatshade:
            # Clean up our hack
            bpy.ops.object.modifier_remove(modifier=bobj.modifiers[-1].name)

        # For now, just output a Mesh, Object and Node for each Blender object
        mesho = Mesh()
        meshi = len(shape.meshes)
        shape.meshes.append(mesho)

        mmin = [0, 0, 0]
        mmax = [0, 0, 0]

        for vertex in mesh.vertices:
            mmin[0] = min(mmin[0], vertex.co.x)
            mmin[1] = min(mmin[1], vertex.co.y)
            mmin[2] = min(mmin[2], vertex.co.z)
            mmax[0] = min(mmax[0], vertex.co.x)
            mmax[1] = min(mmax[1], vertex.co.y)
            mmax[2] = min(mmax[2], vertex.co.z)
            smin[0] = min(smin[0], vertex.co.x)
            smin[1] = min(smin[1], vertex.co.y)
            smin[2] = min(smin[2], vertex.co.z)
            smax[0] = min(smax[0], vertex.co.x)
            smax[1] = min(smax[1], vertex.co.y)
            smax[2] = min(smax[2], vertex.co.z)

            radius = sqrt(vertex.co.x**2 + vertex.co.y**2 + vertex.co.z**2)
            radius_tube = sqrt(vertex.co.x**2 + vertex.co.y**2)
            mesho.radius = max(mesho.radius, radius)
            shape.radius = max(shape.radius, radius)
            shape.radius_tube = max(shape.radius_tube, radius_tube)

            mesho.verts.append(Point(*vertex.co))
            mesho.normals.append(Point(*vertex.normal))
            mesho.enormals.append(0)
            mesho.tverts.append(Point2D(0, 0))

        mesho.bounds = Box(Point(*mmin), Point(*mmax))

        for polygon in mesh.polygons:
            poly_count += 1
            mesho.indices.append(polygon.vertices[2])
            mesho.indices.append(polygon.vertices[1])
            mesho.indices.append(polygon.vertices[0])

        flags = Primitive.Triangles | Primitive.Indexed

        if len(mesh.materials) > 0:
            material = mesh.materials[0]
            material_index = material_lookup.get(material)

            if material_index == None:
                material_index = len(shape.materials)
                material_lookup[material] = material_index
                mat_flags = Material.SWrap | Material.TWrap | Material.NeverEnvMap

                if material.use_transparency:
                    mat_flags |= Material.Translucent
                if material.use_shadeless:
                    mat_flags |= Material.SelfIlluminating
                if "additive" in material:
                    mat_flags |= Material.Additive
                if "subtractive" in material:
                    mat_flags |= Material.Additive

                shape.materials.append(Material(name=material.name, flags=mat_flags))

            flags |= material_index & Primitive.MaterialMask
        else:
            if blank_material:
                if blank_material_index == None:
                    blank_material_index = len(shape.materials)
                    shape.materials.append(Material(name="blank", flags=Material.SWrap | Material.TWrap | Material.NeverEnvMap, reflectanceMap=0))
                flags |= blank_material_index & Primitive.MaterialMask
            else:
                flags |= Primitive.NoMaterial

        bpy.data.meshes.remove(mesh)

        mesho.primitives.append(Primitive(0, len(mesho.indices), flags))
        mesho.vertsPerFrame = len(mesho.verts)

        # Make a Node for the future Object
        nodeo = Node(shape.name(bobj.name))
        nodei = len(shape.nodes)
        shape.nodes.append(nodeo)
        shape.default_translations.append(Point(*bobj.location))
        # shape.default_rotations.append(Quaternion(*bobj.rotation_quaternion))
        shape.default_rotations.append(Quaternion(
            bobj.rotation_quaternion[1],
            bobj.rotation_quaternion[2],
            bobj.rotation_quaternion[3],
            -bobj.rotation_quaternion[0]
        ))
        # ^ this needs to consider bobj.rotation_mode!

        # Now put the Mesh in an Object
        objecto = Object(shape.name(bobj.name), numMeshes=1, firstMesh=meshi, node=nodei)
        objecti = len(shape.objects)
        shape.objects.append(objecto)

    shape.subshapes.append(Subshape(firstNode=0, firstObject=0, firstDecal=0, numNodes=len(shape.nodes), numObjects=len(shape.objects), numDecals=0))
    shape.detail_levels.append(DetailLevel(name=shape.name("detail-100"), subshape=0, objectDetail=0, size=100.0, polyCount=poly_count))

    shape.smallest_size = 1.401298464324817e-45
    shape.bounds = Box(Point(*smin), Point(*smax))

    with open(filepath, "wb") as fd:
        shape.save(fd)

    return {"FINISHED"}