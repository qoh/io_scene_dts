import os
import time

import bpy
import mathutils
import bpy_extras.io_utils

"""
def mesh_triangulate(me):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()

def write_file(filepath, objects, scene,
               EXPORT_TRI=False,
               EXPORT_EDGES=False,
               EXPORT_SMOOTH_GROUPS=False,
               EXPORT_SMOOTH_GROUPS_BITFLAGS=False,
               EXPORT_NORMALS=False,
               EXPORT_UV=True,
               EXPORT_MTL=True,
               EXPORT_APPLY_MODIFIERS=True,
               EXPORT_BLEN_OBS=True,
               EXPORT_GROUP_BY_OB=False,
               EXPORT_GROUP_BY_MAT=False,
               EXPORT_KEEP_VERT_ORDER=False,
               EXPORT_POLYGROUPS=False,
               EXPORT_CURVE_AS_NURBS=True,
               EXPORT_GLOBAL_MATRIX=None,
               EXPORT_PATH_MODE='AUTO',
               ):
    ""
    #Basic write function. The context and options must be already set
    #This can be accessed externaly
    #eg.
    #write( 'c:\\test\\foobar.obj', Blender.Object.GetSelected() ) # Using default options.
    ""

    if EXPORT_GLOBAL_MATRIX is None:
        EXPORT_GLOBAL_MATRIX = mathutils.Matrix()

    def veckey3d(v):
        return round(v.x, 4), round(v.y, 4), round(v.z, 4)

    def veckey2d(v):
        return round(v[0], 4), round(v[1], 4)

    def findVertexGroupName(face, vWeightMap):
        ""
        Searches the vertexDict to see what groups is assigned to a given face.
        We use a frequency system in order to sort out the name because a given vetex can
        belong to two or more groups at the same time. To find the right name for the face
        we list all the possible vertex group names with their frequency and then sort by
        frequency in descend order. The top element is the one shared by the highest number
        of vertices is the face's group
        ""
        weightDict = {}
        for vert_index in face.vertices:
            vWeights = vWeightMap[vert_index]
            for vGroupName, weight in vWeights:
                weightDict[vGroupName] = weightDict.get(vGroupName, 0.0) + weight

        if weightDict:
            return max((weight, vGroupName) for vGroupName, weight in weightDict.items())[1]
        else:
            return '(null)'

    print('OBJ Export path: %r' % filepath)

    time1 = time.time()

    file = open(filepath, "w", encoding="utf8", newline="\n")
    fw = file.write

    # Write Header
    fw('# Blender v%s OBJ File: %r\n' % (bpy.app.version_string, os.path.basename(bpy.data.filepath)))
    fw('# www.blender.org\n')

    # Tell the obj file what material file to use.
    if EXPORT_MTL:
        mtlfilepath = os.path.splitext(filepath)[0] + ".mtl"
        fw('mtllib %s\n' % repr(os.path.basename(mtlfilepath))[1:-1])  # filepath can contain non utf8 chars, use repr

    # Initialize totals, these are updated each object
    totverts = totuvco = totno = 1

    face_vert_index = 1

    # A Dict of Materials
    # (material.name, image.name):matname_imagename # matname_imagename has gaps removed.
    mtl_dict = {}
    # Used to reduce the usage of matname_texname materials, which can become annoying in case of
    # repeated exports/imports, yet keeping unique mat names per keys!
    # mtl_name: (material.name, image.name)
    mtl_rev_dict = {}

    copy_set = set()

    # Get all meshes
    for ob_main in objects:

        # ignore dupli children
        if ob_main.parent and ob_main.parent.dupli_type in {'VERTS', 'FACES'}:
            # XXX
            print(ob_main.name, 'is a dupli child - ignoring')
            continue

        obs = []
        if ob_main.dupli_type != 'NONE':
            # XXX
            print('creating dupli_list on', ob_main.name)
            ob_main.dupli_list_create(scene)

            obs = [(dob.object, dob.matrix) for dob in ob_main.dupli_list]

            # XXX debug print
            print(ob_main.name, 'has', len(obs), 'dupli children')
        else:
            obs = [(ob_main, ob_main.matrix_world)]

        for ob, ob_mat in obs:
            uv_unique_count = no_unique_count = 0

            # Nurbs curve support
            if EXPORT_CURVE_AS_NURBS and test_nurbs_compat(ob):
                ob_mat = EXPORT_GLOBAL_MATRIX * ob_mat
                totverts += write_nurb(fw, ob, ob_mat)
                continue
            # END NURBS

            try:
                me = ob.to_mesh(scene, EXPORT_APPLY_MODIFIERS, 'PREVIEW', calc_tessface=False)
            except RuntimeError:
                me = None

            if me is None:
                continue

            me.transform(EXPORT_GLOBAL_MATRIX * ob_mat)

            if EXPORT_TRI:
                # _must_ do this first since it re-allocs arrays
                mesh_triangulate(me)

            if EXPORT_UV:
                faceuv = len(me.uv_textures) > 0
                if faceuv:
                    uv_texture = me.uv_textures.active.data[:]
                    uv_layer = me.uv_layers.active.data[:]
            else:
                faceuv = False

            me_verts = me.vertices[:]

            # Make our own list so it can be sorted to reduce context switching
            face_index_pairs = [(face, index) for index, face in enumerate(me.polygons)]
            # faces = [ f for f in me.tessfaces ]

            if EXPORT_EDGES:
                edges = me.edges
            else:
                edges = []

            if not (len(face_index_pairs) + len(edges) + len(me.vertices)):  # Make sure there is somthing to write

                # clean up
                bpy.data.meshes.remove(me)

                continue  # dont bother with this mesh.

            if EXPORT_NORMALS and face_index_pairs:
                me.calc_normals_split()
                # No need to call me.free_normals_split later, as this mesh is deleted anyway!
                loops = me.loops
            else:
                loops = []

            if (EXPORT_SMOOTH_GROUPS or EXPORT_SMOOTH_GROUPS_BITFLAGS) and face_index_pairs:
                smooth_groups, smooth_groups_tot = me.calc_smooth_groups(EXPORT_SMOOTH_GROUPS_BITFLAGS)
                if smooth_groups_tot <= 1:
                    smooth_groups, smooth_groups_tot = (), 0
            else:
                smooth_groups, smooth_groups_tot = (), 0

            materials = me.materials[:]
            material_names = [m.name if m else None for m in materials]

            # avoid bad index errors
            if not materials:
                materials = [None]
                material_names = [name_compat(None)]

            # Sort by Material, then images
            # so we dont over context switch in the obj file.
            if EXPORT_KEEP_VERT_ORDER:
                pass
            else:
                if faceuv:
                    if smooth_groups:
                        sort_func = lambda a: (a[0].material_index,
                                               hash(uv_texture[a[1]].image),
                                               smooth_groups[a[1]] if a[0].use_smooth else False)
                    else:
                        sort_func = lambda a: (a[0].material_index,
                                               hash(uv_texture[a[1]].image),
                                               a[0].use_smooth)
                elif len(materials) > 1:
                    if smooth_groups:
                        sort_func = lambda a: (a[0].material_index,
                                               smooth_groups[a[1]] if a[0].use_smooth else False)
                    else:
                        sort_func = lambda a: (a[0].material_index,
                                               a[0].use_smooth)
                else:
                    # no materials
                    if smooth_groups:
                        sort_func = lambda a: smooth_groups[a[1] if a[0].use_smooth else False]
                    else:
                        sort_func = lambda a: a[0].use_smooth

                face_index_pairs.sort(key=sort_func)

                del sort_func

            # Set the default mat to no material and no image.
            contextMat = 0, 0  # Can never be this, so we will label a new material the first chance we get.
            contextSmooth = None  # Will either be true or false,  set bad to force initialization switch.

            if EXPORT_BLEN_OBS or EXPORT_GROUP_BY_OB:
                name1 = ob.name
                name2 = ob.data.name
                if name1 == name2:
                    obnamestring = name_compat(name1)
                else:
                    obnamestring = '%s_%s' % (name_compat(name1), name_compat(name2))

                if EXPORT_BLEN_OBS:
                    fw('o %s\n' % obnamestring)  # Write Object name
                else:  # if EXPORT_GROUP_BY_OB:
                    fw('g %s\n' % obnamestring)

            # Vert
            for v in me_verts:
                fw('v %.6f %.6f %.6f\n' % v.co[:])

            # UV
            if faceuv:
                # in case removing some of these dont get defined.
                uv = f_index = uv_index = uv_key = uv_val = uv_ls = None

                uv_face_mapping = [None] * len(face_index_pairs)

                uv_dict = {}
                uv_get = uv_dict.get
                for f, f_index in face_index_pairs:
                    uv_ls = uv_face_mapping[f_index] = []
                    for uv_index, l_index in enumerate(f.loop_indices):
                        uv = uv_layer[l_index].uv
                        uv_key = veckey2d(uv)
                        uv_val = uv_get(uv_key)
                        if uv_val is None:
                            uv_val = uv_dict[uv_key] = uv_unique_count
                            fw('vt %.6f %.6f\n' % uv[:])
                            uv_unique_count += 1
                        uv_ls.append(uv_val)

                del uv_dict, uv, f_index, uv_index, uv_ls, uv_get, uv_key, uv_val
                # Only need uv_unique_count and uv_face_mapping

            # NORMAL, Smooth/Non smoothed.
            if EXPORT_NORMALS:
                no_key = no_val = None
                normals_to_idx = {}
                no_get = normals_to_idx.get
                loops_to_normals = [0] * len(loops)
                for f, f_index in face_index_pairs:
                    for l_idx in f.loop_indices:
                        no_key = veckey3d(loops[l_idx].normal)
                        no_val = no_get(no_key)
                        if no_val is None:
                            no_val = normals_to_idx[no_key] = no_unique_count
                            fw('vn %.6f %.6f %.6f\n' % no_key)
                            no_unique_count += 1
                        loops_to_normals[l_idx] = no_val
                del normals_to_idx, no_get, no_key, no_val
            else:
                loops_to_normals = []

            if not faceuv:
                f_image = None

            # XXX
            if EXPORT_POLYGROUPS:
                # Retrieve the list of vertex groups
                vertGroupNames = ob.vertex_groups.keys()
                if vertGroupNames:
                    currentVGroup = ''
                    # Create a dictionary keyed by face id and listing, for each vertex, the vertex groups it belongs to
                    vgroupsMap = [[] for _i in range(len(me_verts))]
                    for v_idx, v_ls in enumerate(vgroupsMap):
                        v_ls[:] = [(vertGroupNames[g.group], g.weight) for g in me_verts[v_idx].groups]

            for f, f_index in face_index_pairs:
                f_smooth = f.use_smooth
                if f_smooth and smooth_groups:
                    f_smooth = smooth_groups[f_index]
                f_mat = min(f.material_index, len(materials) - 1)

                if faceuv:
                    tface = uv_texture[f_index]
                    f_image = tface.image

                # MAKE KEY
                if faceuv and f_image:  # Object is always true.
                    key = material_names[f_mat], f_image.name
                else:
                    key = material_names[f_mat], None  # No image, use None instead.

                # Write the vertex group
                if EXPORT_POLYGROUPS:
                    if vertGroupNames:
                        # find what vertext group the face belongs to
                        vgroup_of_face = findVertexGroupName(f, vgroupsMap)
                        if vgroup_of_face != currentVGroup:
                            currentVGroup = vgroup_of_face
                            fw('g %s\n' % vgroup_of_face)

                # CHECK FOR CONTEXT SWITCH
                if key == contextMat:
                    pass  # Context already switched, dont do anything
                else:
                    if key[0] is None and key[1] is None:
                        # Write a null material, since we know the context has changed.
                        if EXPORT_GROUP_BY_MAT:
                            # can be mat_image or (null)
                            fw("g %s_%s\n" % (name_compat(ob.name), name_compat(ob.data.name)))
                        if EXPORT_MTL:
                            fw("usemtl (null)\n")  # mat, image

                    else:
                        mat_data = mtl_dict.get(key)
                        if not mat_data:
                            # First add to global dict so we can export to mtl
                            # Then write mtl

                            # Make a new names from the mat and image name,
                            # converting any spaces to underscores with name_compat.

                            # If none image dont bother adding it to the name
                            # Try to avoid as much as possible adding texname (or other things)
                            # to the mtl name (see [#32102])...
                            mtl_name = "%s" % name_compat(key[0])
                            if mtl_rev_dict.get(mtl_name, None) not in {key, None}:
                                if key[1] is None:
                                    tmp_ext = "_NONE"
                                else:
                                    tmp_ext = "_%s" % name_compat(key[1])
                                i = 0
                                while mtl_rev_dict.get(mtl_name + tmp_ext, None) not in {key, None}:
                                    i += 1
                                    tmp_ext = "_%3d" % i
                                mtl_name += tmp_ext
                            mat_data = mtl_dict[key] = mtl_name, materials[f_mat], f_image
                            mtl_rev_dict[mtl_name] = key

                        if EXPORT_GROUP_BY_MAT:
                            # can be mat_image or (null)
                            fw("g %s_%s_%s\n" % (name_compat(ob.name), name_compat(ob.data.name), mat_data[0]))
                        if EXPORT_MTL:
                            fw("usemtl %s\n" % mat_data[0])  # can be mat_image or (null)

                contextMat = key
                if f_smooth != contextSmooth:
                    if f_smooth:  # on now off
                        if smooth_groups:
                            f_smooth = smooth_groups[f_index]
                            fw('s %d\n' % f_smooth)
                        else:
                            fw('s 1\n')
                    else:  # was off now on
                        fw('s off\n')
                    contextSmooth = f_smooth

                f_v = [(vi, me_verts[v_idx], l_idx)
                       for vi, (v_idx, l_idx) in enumerate(zip(f.vertices, f.loop_indices))]

                fw('f')
                if faceuv:
                    if EXPORT_NORMALS:
                        for vi, v, li in f_v:
                            fw(" %d/%d/%d" % (totverts + v.index,
                                              totuvco + uv_face_mapping[f_index][vi],
                                              totno + loops_to_normals[li],
                                              ))  # vert, uv, normal
                    else:  # No Normals
                        for vi, v, li in f_v:
                            fw(" %d/%d" % (totverts + v.index,
                                           totuvco + uv_face_mapping[f_index][vi],
                                           ))  # vert, uv

                    face_vert_index += len(f_v)

                else:  # No UV's
                    if EXPORT_NORMALS:
                        for vi, v, li in f_v:
                            fw(" %d//%d" % (totverts + v.index, totno + loops_to_normals[li]))
                    else:  # No Normals
                        for vi, v, li in f_v:
                            fw(" %d" % (totverts + v.index))

                fw('\n')

            # Write edges.
            if EXPORT_EDGES:
                for ed in edges:
                    if ed.is_loose:
                        fw('l %d %d\n' % (totverts + ed.vertices[0], totverts + ed.vertices[1]))

            # Make the indices global rather then per mesh
            totverts += len(me_verts)
            totuvco += uv_unique_count
            totno += no_unique_count

            # clean up
            bpy.data.meshes.remove(me)

        if ob_main.dupli_type != 'NONE':
            ob_main.dupli_list_clear()

    file.close()

    # Now we have all our materials, save them
    if EXPORT_MTL:
        write_mtl(scene, mtlfilepath, EXPORT_PATH_MODE, copy_set, mtl_dict)

    # copy all collected files.
    bpy_extras.io_utils.path_reference_copy(copy_set)

    print("OBJ Export time: %.2f" % (time.time() - time1))

def _write(context, filepath,
           EXPORT_TRI,  # ok
           EXPORT_EDGES,
           EXPORT_SMOOTH_GROUPS,
           EXPORT_SMOOTH_GROUPS_BITFLAGS,
           EXPORT_NORMALS,  # ok
           EXPORT_UV,  # ok
           EXPORT_MTL,
           EXPORT_APPLY_MODIFIERS,  # ok
           EXPORT_BLEN_OBS,
           EXPORT_GROUP_BY_OB,
           EXPORT_GROUP_BY_MAT,
           EXPORT_KEEP_VERT_ORDER,
           EXPORT_POLYGROUPS,
           EXPORT_CURVE_AS_NURBS,
           EXPORT_SEL_ONLY,  # ok
           EXPORT_ANIMATION,
           EXPORT_GLOBAL_MATRIX,
           EXPORT_PATH_MODE,  # Not used
           ):

    base_name, ext = os.path.splitext(filepath)
    context_name = [base_name, '', '', ext]  # Base name, scene name, frame number, extension

    scene = context.scene

    # Exit edit mode before exporting, so current object states are exported properly.
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')

    orig_frame = scene.frame_current

    # Export an animation?
    if EXPORT_ANIMATION:
        scene_frames = range(scene.frame_start, scene.frame_end + 1)  # Up to and including the end frame.
    else:
        scene_frames = [orig_frame]  # Dont export an animation.

    # Loop through all frames in the scene and export.
    for frame in scene_frames:
        if EXPORT_ANIMATION:  # Add frame to the filepath.
            context_name[2] = '_%.6d' % frame

        scene.frame_set(frame, 0.0)
        if EXPORT_SEL_ONLY:
            objects = context.selected_objects
        else:
            objects = scene.objects

        full_path = ''.join(context_name)

        # erm... bit of a problem here, this can overwrite files when exporting frames. not too bad.
        # EXPORT THE FILE.
        write_file(full_path, objects, scene,
                   EXPORT_TRI,
                   EXPORT_EDGES,
                   EXPORT_SMOOTH_GROUPS,
                   EXPORT_SMOOTH_GROUPS_BITFLAGS,
                   EXPORT_NORMALS,
                   EXPORT_UV,
                   EXPORT_MTL,
                   EXPORT_APPLY_MODIFIERS,
                   EXPORT_BLEN_OBS,
                   EXPORT_GROUP_BY_OB,
                   EXPORT_GROUP_BY_MAT,
                   EXPORT_KEEP_VERT_ORDER,
                   EXPORT_POLYGROUPS,
                   EXPORT_CURVE_AS_NURBS,
                   EXPORT_GLOBAL_MATRIX,
                   EXPORT_PATH_MODE,
                   )

    scene.frame_set(orig_frame, 0.0)
"""

from .DtsShape import DtsShape
from .DtsTypes import *

import math
import bmesh

def save(operator, context, filepath,
         use_selection=True):
    scene = context.scene

    if use_selection:
        objects = context.selected_objects
    else:
        objects = scene.objects

    shape = DtsShape()
    shape.nodes.append(Node(shape.name("Exp-Catch-Root")))
    shape.default_translations.append(Point(0,0,0))
    shape.default_rotations.append(Quaternion(0,0,0,1))

    poly_count = 0
    smin = [0, 0, 0]
    smax = [0, 0, 0]

    for bobj in objects:
        if bobj.type != "MESH":
            print("skipping " + bobj.name)
            continue

        mesh = bobj.to_mesh(scene, False, "PREVIEW")
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()

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

            radius = math.sqrt(vertex.co.x**2 + vertex.co.y**2 + vertex.co.z**2)
            radius_tube = math.sqrt(vertex.co.x**2 + vertex.co.y**2)
            mesho.radius = max(mesho.radius, radius)
            shape.radius = max(shape.radius, radius)
            shape.radius_tube = max(shape.radius_tube, radius_tube)

            mesho.verts.append(Point(*vertex.co))
            # mesho.normals.append(Point(*vertex.normal))
            mesho.normals.append(Point(-vertex.normal.x, -vertex.normal.y, -vertex.normal.z))
            mesho.enormals.append(0)
            mesho.tverts.append(Point2D(0, 0))

        mesho.bounds = Box(Point(*mmin), Point(*mmax))

        for polygon in mesh.polygons:
            poly_count += 1
            mesho.indices.append(polygon.vertices[2])
            mesho.indices.append(polygon.vertices[1])
            mesho.indices.append(polygon.vertices[0])
            # mesho.indices.extend(polygon.vertices)

        mesho.primitives.append(Primitive(0, len(mesho.indices), Primitive.Triangles | Primitive.Indexed))
        mesho.vertsPerFrame = len(mesho.verts)

        # Make a Node for the future Object
        nodeo = Node(shape.name(bobj.name))
        nodei = len(shape.nodes)
        shape.nodes.append(nodeo)
        shape.default_translations.append(Point(*bobj.location))
        shape.default_rotations.append(Quaternion(*bobj.rotation_quaternion))
        # ^ this needs to consider bobj.rotation_mode!

        # Now put the Mesh in an Object
        objecto = Object(shape.name(bobj.name), numMeshes=1, firstMesh=meshi, node=nodei)
        objecti = len(shape.objects)
        shape.objects.append(objecto)

    shape.materials.append(Material(name="Material", flags=Material.SWrap | Material.TWrap | Material.NeverEnvMap, reflectanceMap=0))
    shape.subshapes.append(Subshape(firstNode=0, firstObject=0, firstDecal=0, numNodes=len(shape.nodes), numObjects=len(shape.objects), numDecals=0))
    shape.detail_levels.append(DetailLevel(name=shape.name("Detail-1"), subshape=0, objectDetail=0, size=1.0, polyCount=poly_count))

    shape.smallest_size = 1.401298464324817e-45
    shape.bounds = Box(Point(*smin), Point(*smax))
    # shape.radius = 1.732050895690918
    # shape.radius_tube = 1.4142136573791504

    # Okay, so let's try to make a cube?
    # First of all we need a Mesh for that
    # mesho = Mesh()
    # meshi = len(shape.meshes)
    # shape.meshes.append(mesho)

    # # Try to do it again! This time with triangle lists!
    # # Maybe we can do it with 8 vertices again, but we really need 24 here because of the normals.
    # mesho.verts = [
    #     #   bottom left     bottom right         top left         top right
    #     Point(-1,-1, 1), Point( 1,-1, 1), Point(-1, 1, 1), Point( 1, 1, 1), # upper
    #     Point(-1,-1,-1), Point( 1,-1,-1), Point(-1, 1,-1), Point( 1, 1,-1), # lower
    # ]
    # mesho.tverts = [Point2D(0, 0)] * 8
    # mesho.normals = [Point(0, 0, 1)] * 8
    # mesho.enormals = [0] * 8
    # mesho.indices = [2,1,0,3,1,2]
    # mesho.primitives = [Primitive(0, 6, Primitive.Triangles | Primitive.Indexed)]
    # mesho.bounds = Box(Point(-1,-1,-1), Point(1,1,1))
    # mesho.radius = 1.732050895690918
    # mesho.vertsPerFrame = 8
    
    # # Let's make a Node for a future Object.
    # nodeo = Node(shape.name("Cube"))
    # nodei = len(shape.nodes)
    # shape.nodes.append(nodeo)
    # # Add this stuff for the node..
    # shape.default_translations.append(Point(0,0,0))
    # shape.default_rotations.append(Quaternion(0,0,0,1))
    # # Let's make an object containing the mesh under that node.
    # objecto = Object(shape.name("Cube"), numMeshes=1, firstMesh=meshi, node=nodei)
    # objecti = len(shape.objects)
    # shape.objects.append(objecto)

    # Does that actually work??
    # shape.materials.append(Material(name="Material", flags=Material.SWrap | Material.TWrap | Material.NeverEnvMap, reflectanceMap=0))
    # shape.subshapes.append(Subshape(firstNode=0, firstObject=objecti, firstDecal=0, numNodes=2, numObjects=1, numDecals=0))
    # shape.detail_levels.append(DetailLevel(name=shape.name("Detail-1"), subshape=0, objectDetail=0, size=1.0, polyCount=8))

    # shape.smallest_size = 1.401298464324817e-45
    # shape.bounds = Box(Point(-1,-1,-1), Point(1,1,1))
    # shape.radius = 1.732050895690918
    # shape.radius_tube = 1.4142136573791504

    with open(filepath, "wb") as fd:
        shape.save(fd)

    return {"FINISHED"}