import bpy, bmesh
from math import sqrt

from .DtsShape import DtsShape
from .DtsTypes import *
from .write_report import write_debug_report

def save(operator, context, filepath,
         use_selection=True,
         blank_material=True,
         force_flatshade=True,
         force_opaque=False,
         debug_report=True):
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
    rooto = Node(shape.name("exporter-root"))
    rooti = len(shape.nodes)
    shape.nodes.append(rooto)
    shape.default_translations.append(Point())
    shape.default_rotations.append(Quaternion())

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

        # So here's an experiment
        tverts = {}
        # for i, loop in enumerate(mesh.loops):
        #     tverts[loop.vertex_index] = mesh.uv_layers[0].data[i].uv
        lawur = mesh.uv_layers[0].data
        for i, polygon in enumerate(mesh.polygons):
            # for uv_index, l_index in enumerate(polygon.loop_indices):
            # for vi, uvi in zip(polygon.vertices, polygon.loop_indices):
            #     tverts[vi] = lawur[uvi].uv
            # for j, loop_index in polygon.loop_indices:
            #     loop =
            pass

        # for vertex in mesh.vertices:
        for numero, vertex in enumerate(mesh.vertices):
            mesho.verts.append(Point(*vertex.co))
            mesho.normals.append(Point(*vertex.normal))
            mesho.enormals.append(0)
            # mesho.tverts.append(Point2D(0, 0))
            # uuuv = mesh.uv_layers[0].data[numero].uv
            uuuv = tverts[numero]
            mesho.tverts.append(Point2D(uuuv.x, uuuv.y))

        # for polygon in mesh.polygons:
        for pi, polygon in enumerate(mesh.polygons):
            poly_count += 1
            # mesho.primitives.append(Primitive(len(mesho.indices), 3, Primitive.Triangles | Primitive.Indexed | Primitive.NoMaterial))
            mesho.indices.append(polygon.vertices[2])
            mesho.indices.append(polygon.vertices[1])
            mesho.indices.append(polygon.vertices[0])
            # for stuff in polygon.loop_indices:
            #     print("polygon {} has uv {}".format(pi, mesh.uv_layers[0].data[stuff].uv))

        mesho.bounds = mesho.calculate_bounds(Point(), Quaternion())
        mesho.center = Point(
            (mesho.bounds.min.x + mesho.bounds.max.x) / 2,
            (mesho.bounds.min.y + mesho.bounds.max.y) / 2,
            (mesho.bounds.min.z + mesho.bounds.max.z) / 2)
        mesho.radius = mesho.calculate_radius(Point(), Quaternion(), mesho.center)

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

                if material.use_transparency and not force_opaque:
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

        if bobj.rotation_mode == "QUATERNION":
            rot = bobj.rotation_quaternion
        else:
            rot = bobj.rotation_euler.to_quaternion()
        # other rotation modes?

        shape.default_rotations.append(
            Quaternion(rot[1], rot[2], rot[3], -rot[0])
        )

        # whatever
        # shape.meshes.append(mesho)

        # Now put the Mesh in an Object
        print("  creating object " + bobj.name + " with 1 mesh")
        objecto = Object(shape.name(bobj.name), numMeshes=1, firstMesh=meshi, node=nodei)
        # objecto = Object(shape.name(bobj.name), numMeshes=2, firstMesh=meshi, node=nodei)
        objecti = len(shape.objects)
        shape.objects.append(objecto)
        shape.objectstates.append(ObjectState(1065353216, 0, 0))

    print("Creating subshape with " + str(len(shape.nodes)) + " nodes and " + str(len(shape.objects)) + " objects")
    shape.subshapes.append(Subshape(firstNode=0, firstObject=0, firstDecal=0, numNodes=len(shape.nodes), numObjects=len(shape.objects), numDecals=0))
    print("Creating Detail-1 LOD")
    shape.detail_levels.append(DetailLevel(name=shape.name("Detail-1"), subshape=0, objectDetail=0, size=1, polyCount=poly_count))
    # print("Creating Collision-1 LOD")
    # shape.detail_levels.append(DetailLevel(name=shape.name("Collision-1"), subshape=0, objectDetail=1, size=-1, polyCount=poly_count))

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
    shape.radius = 0
    shape.radius_tube = 0

    for i, obj in enumerate(shape.objects):
        trans, rot = shape.get_world(obj.node)

        for j in range(0, obj.numMeshes):
            mesh = shape.meshes[obj.firstMesh + j]
            bounds = mesh.calculate_bounds(trans, rot)

            shape.radius = max(shape.radius, mesh.calculate_radius(trans, rot, shape.center))
            shape.radius_tube = max(shape.radius_tube, mesh.calculate_radius_tube(trans, rot, shape.center))

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

    if debug_report:
        write_debug_report(filepath + ".txt", shape)

    with open(filepath, "wb") as fd:
        shape.save(fd)

    return {"FINISHED"}
