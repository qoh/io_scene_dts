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
    smin = [10e30, 10e30, 10e30]
    smax = [-10e30, -10e30, -10e30]

    material_lookup = {}
    blank_material_index = None

    print("Exporting scene to DTS")

    # Let's try this
    print("Creating root")
    rooto = Node(shape.name("root-catch"))
    rooti = len(shape.nodes)
    shape.nodes.append(rooto)
    shape.default_translations.append(Point(0, 0, 0))
    shape.default_rotations.append(Quaternion(0, 0, 0, 1))

    for bobj in objects:
        print("Processing object " + bobj.name + "(" + bobj.type + ")")

        if bobj.type != "MESH":
            print("  not a MESH, skipping")
            continue

        if force_flatshade:
            print("  edge split")
            # Hack in flatshading
            scene.objects.active = bobj
            bpy.ops.object.modifier_add(type="EDGE_SPLIT")
            bobj.modifiers[-1].split_angle = 0

        print("  bmesh triangulation")
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

        # mmin = [10e30, 10e30, 10e30]
        # mmax = [-10e30, -10e30, -10e30]

        for vertex in mesh.vertices:
            # mmin[0] = min(mmin[0], vertex.co.x)
            # mmin[1] = min(mmin[1], vertex.co.y)
            # mmin[2] = min(mmin[2], vertex.co.z)
            # mmax[0] = min(mmax[0], vertex.co.x)
            # mmax[1] = min(mmax[1], vertex.co.y)
            # mmax[2] = min(mmax[2], vertex.co.z)
            # smin[0] = min(smin[0], vertex.co.x)
            # smin[1] = min(smin[1], vertex.co.y)
            # smin[2] = min(smin[2], vertex.co.z)
            # smax[0] = min(smax[0], vertex.co.x)
            # smax[1] = min(smax[1], vertex.co.y)
            # smax[2] = min(smax[2], vertex.co.z)

            # radius = sqrt(vertex.co.x**2 + vertex.co.y**2 + vertex.co.z**2)
            # radius_tube = sqrt(vertex.co.x**2 + vertex.co.y**2)
            # mesho.radius = max(mesho.radius, radius)
            # shape.radius = max(shape.radius, radius)
            # shape.radius_tube = max(shape.radius_tube, radius_tube)

            mesho.verts.append(Point(*vertex.co))
            mesho.normals.append(Point(*vertex.normal))
            mesho.enormals.append(0)
            mesho.tverts.append(Point2D(0, 0))

        # mesho.bounds = Box(Point(*mmin), Point(*mmax))
        mesho.bounds = mesho.calculate_bounds(Point(), Quaternion())

        for polygon in mesh.polygons:
            poly_count += 1
            mesho.indices.append(polygon.vertices[2])
            mesho.indices.append(polygon.vertices[1])
            mesho.indices.append(polygon.vertices[0])

        flags = Primitive.Triangles | Primitive.Indexed

        if len(mesh.materials) > 0:
            # TODO: per-face material exporting
            print("  processing materials")
            material = mesh.materials[0]
            material_index = material_lookup.get(material)

            if material_index == None:
                print("    creating material for blender mat " + material.name)
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
        nodeo = Node(shape.name(bobj.name), parent=rooti) # set parent
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
        print("  creating object " + bobj.name + " with 1 mesh")
        objecto = Object(shape.name(bobj.name), numMeshes=1, firstMesh=meshi, node=nodei)
        objecti = len(shape.objects)
        shape.objects.append(objecto)
        shape.objectstates.append(ObjectState(1065353216, 0, 0))

    print("Creating subshape with " + str(len(shape.nodes)) + " nodes and " + str(len(shape.objects)) + " objects")
    shape.subshapes.append(Subshape(firstNode=0, firstObject=0, firstDecal=0, numNodes=len(shape.nodes), numObjects=len(shape.objects), numDecals=0))
    print("Creating detail-1 LOD")
    shape.detail_levels.append(DetailLevel(name=shape.name("detail-1"), subshape=0, objectDetail=0, size=1, polyCount=poly_count))
    # shape.detail_levels.append(DetailLevel(name=shape.name("col-1"), subshape=0, objectDetail=0, size=-1, polyCount=poly_count))

    # Figure out all the things
    print("Computing bounds")
    shape.smallest_size = None
    shape.smallest_detail_level = None

    for i, lod in enumerate(shape.detail_levels):
        if shape.smallest_size == None or (lod.size >= 0 and lod.size < shape.smallest_size):
            shape.smallest_size = lod.size
            shape.smallest_detail_level = i

    shape.bounds = Box(
        Point( 10e30,  10e30,  10e30),
        Point(-10e30, -10e30, -10e30))

    for i, obj in enumerate(shape.objects):
        trans, rot = shape.get_world(obj.node)

        for j in range(0, obj.numMeshes):
            mesh = shape.meshes[obj.firstMesh + j]
            bounds = mesh.calculate_bounds(trans, rot)

            print(bounds.min.x, bounds.min.y, bounds.min.z, bounds.max.x, bounds.max.y, bounds.max.z)
            shape.bounds.min.x = min(shape.bounds.min.x, bounds.min.x)
            shape.bounds.min.y = min(shape.bounds.min.y, bounds.min.y)
            shape.bounds.min.z = min(shape.bounds.min.z, bounds.min.z)
            shape.bounds.max.x = max(shape.bounds.max.x, bounds.max.x)
            shape.bounds.max.y = max(shape.bounds.max.y, bounds.max.y)
            shape.bounds.max.z = max(shape.bounds.max.z, bounds.max.z)

    shape.center = Point(
        (shape.bounds.min.x + shape.bounds.max.x) / 2,
        (shape.bounds.min.y + shape.bounds.max.y) / 2,
        (shape.bounds.min.z + shape.bounds.max.z) / 2)
    shape.radius = 0
    shape.radius_tube = 0

    for i, obj in enumerate(shape.objects):
        trans, rot = shape.get_world(obj.node)

        for j in range(0, obj.numMeshes):
            mesh = shape.meshes[obj.firstMesh + j]
            shape.radius = max(shape.radius, mesh.calculate_radius(trans, rot, shape.center))
            shape.radius_tube = max(shape.radius_tube, mesh.calculate_radius_tube(trans, rot, shape.center))

    with open(filepath, "wb") as fd:
        shape.save(fd)

    return {"FINISHED"}
