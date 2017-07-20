from .DtsTypes import *

def write_debug_report(filepath, shape):
    with open(filepath, "w") as fd:
        def p(line):
            fd.write(line + "\n")
        def gn(i):
            return shape.names[i]
        def ln(table, first, count):
            def each(i):
                entry = table[i]
                if hasattr(entry, "name"):
                    return str(i) + " -> " + gn(entry.name)
                else:
                    return str(i)
            return ", ".join(map(each, range(first, first + count)))
        def show_matters(matters):
            return ' '.join(map(lambda p: gn(p[0].name), filter(lambda p: p[1], zip(shape.nodes, matters))))

        p("smallest_size = " + str(shape.smallest_size))
        p("smallest_detail_level = " + str(shape.smallest_detail_level))
        p("radius = " + str(shape.radius))
        p("radius_tube = " + str(shape.radius_tube))
        p("center = " + str(shape.center))
        p("bounds = " + str(shape.bounds))
        # p("Decals (deprecated): " + str(len(shape.decals)))
        p("Ground frames: " + str(len(shape.ground_translations)))
        # p("Decal states (deprecated): " + str(len(shape.decalstates)))
        p("Triggers: " + str(len(shape.triggers)))

        p("Sequence node rotations: " + str(len(shape.node_rotations)))
        p("Sequence node translations: " + str(len(shape.node_translations)))
        p("Sequence node uniform scales: " + str(len(shape.node_uniform_scales)))
        p("Sequence node aligned scales: " + str(len(shape.node_aligned_scales)))
        p("Sequence node arbitrary scales: " + str(len(shape.node_arbitrary_scale_factors)))

        p("Detail levels (" + str(len(shape.detail_levels)) + "):")
        for i, lod in enumerate(shape.detail_levels):
            p("  LOD " + str(i) + " " + gn(lod.name) + " (size " + str(lod.size) + ")")
            p("    subshape = " + str(lod.subshape))
            p("    objectDetail = " + str(lod.objectDetail))
            p("    polyCount = " + str(lod.polyCount))
            # p("    avgError (unused) = " + str(lod.avgError))
            # p("    maxError (unused) = " + str(lod.maxError))

        p("Subshapes (" + str(len(shape.subshapes)) + "):")
        for i, sub in enumerate(shape.subshapes):
            p("  Subshape " + str(i))
            # p("    firstNode = " + str(sub.firstNode))
            # p("    firstObject = " + str(sub.firstObject))
            # p("    firstDecal (deprecated) = " + str(sub.firstDecal))
            # p("    numNodes = " + str(sub.numNodes))
            # p("    numObjects = " + str(sub.numObjects))
            # p("    numDecals (deprecated) = " + str(sub.numDecals))
            # p("      nodes = " + ln(shape.nodes, sub.firstNode, sub.numNodes))
            # p("      objects = " + ln(shape.objects, sub.firstObject, sub.numObjects))
            p("    nodes = " + ln(shape.nodes, sub.firstNode, sub.numNodes))
            p("    objects = " + ln(shape.objects, sub.firstObject, sub.numObjects))
            # p("      decals (deprecated) = " + ln(shape.decals, sub.firstDecal, sub.numDecals))

        p("Nodes (" + str(len(shape.nodes)) + "):")
        for i, node in enumerate(shape.nodes):
            if node.parent == -1:
                p("  " + str(i) + " " + gn(node.name))
            else:
                p("  " + str(i) + " " + gn(node.name) + "  ->  " + str(node.parent) + " " + gn(shape.nodes[node.parent].name))
            if i < len(shape.default_translations):
                p("    translation = " + str(shape.default_translations[i]))
            else:
                p("    translation = MISSING!")
            if i < len(shape.default_rotations):
                p("    rotation = " + str(shape.default_rotations[i]))
            else:
                p("    rotation = MISSING!")

        # TODO: tell if default transform lists are longer than node list

        p("Object states: " + str(len(shape.objectstates)))
        p("Objects (" + str(len(shape.objects)) + "):")
        for i, obj in enumerate(shape.objects):
            s = "  " + str(i) + " " + gn(obj.name)
            if obj.node == -1:
                s += " NOT ATTACHED!"
            else:
                s += " in " + str(obj.node) + " (" + gn(shape.nodes[obj.node].name) + ")"
            s += ", meshes = " + ln(shape.meshes, obj.firstMesh, obj.numMeshes)
            p(s)

        p("Materials (" + str(len(shape.materials)) + "):")
        for i, mat in enumerate(shape.materials):
            flagNames = ("SWrap", "TWrap", "Translucent", "Additive", "Subtractive", "SelfIlluminating", "NeverEnvMap", "NoMipMap", "MipMapZeroBorder", "IFLMaterial", "IFLFrame", "DetailMap", "BumpMap", "ReflectanceMap", "AuxiliaryMask")
            flags = ""
            for name in flagNames:
                if mat.flags & getattr(Material, name):
                    flags += " " + name
            p("  " + str(i) + " " + mat.name + " (" + str(mat.flags) + flags + ")")
            p("    bumpMap = " + str(mat.bumpMap) + ", reflectanceMap = " + str(mat.reflectanceMap) + ", detailMap = " + str(mat.detailMap))
            p("    reflectance = " + str(mat.reflectance) + ", detailScale = " + str(mat.detailScale))

        p("IFL materials (" + str(len(shape.iflmaterials)) + "):")
        for ifl in shape.iflmaterials:
            p("  IflMat " + gn(ifl.name))
            if ifl.slot in shape.materials:
                mat_name = gn(shape.materials[ifl.slot].name)
            else:
                mat_name = "<MISSING>"
            p("    slot = " + str(ifl.slot) + " " + mat_name + ", time = " + str(ifl.time))
            p("    firstFrame = " + str(ifl.firstFrame) + ", numFrames = " + str(ifl.numFrames))

        p("Meshes (" + str(len(shape.meshes)) + "):")
        for i, mesh in enumerate(shape.meshes):
            mtype = mesh.get_type()
            p("  Mesh " + str(i) + " - " + Mesh.TypeName[mtype])

            if mtype == Mesh.NullType:
                continue

            p("    flags = " + str(mesh.get_flags()))
            p("    bounds = " + str(mesh.bounds))
            p("    center = " + str(mesh.center))
            p("    radius = " + str(mesh.radius))
            # p("    numFrames = " + str(mesh.numFrames))
            # p("    numMatFrames = " + str(mesh.numMatFrames))
            # p("    vertsPerFrame = " + str(mesh.vertsPerFrame))
            # p("    parent (unused?) = " + str(mesh.parent))
            # p("    indices = " + ",".join(map(str, mesh.indices)))
            # p("    mindices = " + ",".join(map(str, mesh.mindices)))
            p("    + Primitives (" + str(len(mesh.primitives)) + "):")
            for prim in mesh.primitives:
                flags = ""
                if prim.type & Primitive.Triangles:
                    flags += " Triangles"
                if prim.type & Primitive.Strip:
                    flags += " Strip"
                if prim.type & Primitive.Fan:
                    flags += " Fan"
                if flags == "":
                    flags += " NoExplicitType->Triangles"
                if prim.type & Primitive.Indexed:
                    flags += " Indexed"
                if prim.type & Primitive.NoMaterial:
                    flags += " NoMaterial"
                mat = prim.type & Primitive.MaterialMask
                flags += " MaterialMask:" + str(mat)
                p("      " + str(prim.firstElement) + "->" + str(prim.firstElement + prim.numElements - 1) + " " + str(prim.type) + flags)
            p("    + Vertices (" + str(len(mesh.verts)) + "): <omitted>")
            # for i in range(len(mesh.verts)):
            #     p("      vert" + str(i) + " " + str(mesh.verts[i]) + " normal " + str(mesh.normals[i]) + " encoded " + str(mesh.enormals[i]))
            p("    + Texture coords (" + str(len(mesh.tverts)) + "): <omitted>")
            # for i in range(len(mesh.tverts)):
            #     p("      tvert" + str(i) + " " + str(mesh.tverts[i]))

            if mtype == Mesh.SkinType:
                p("    + Bones ({})".format(len(mesh.bones)))
                for i, (node_index, initial_transform) in enumerate(mesh.bones):
                    p("      bone{} node={} initial_transform={}".format(i, node_index, initial_transform))
                p("    + Influences ({}): <omitted>".format(len(mesh.influences)))
                # for vi, bi, w in mesh.influences:
                #     p
                #     p("      influence vert{} bone{} weight={}".format(vi, bi, w))

        p("Sequences (" + str(len(shape.sequences)) + "):")
        for i, seq in enumerate(shape.sequences):
            p("  " + str(i) + " " + shape.names[seq.nameIndex])
            p("    flags: " + str(seq.flags))
            p("    numKeyframes: " + str(seq.numKeyframes))
            p("    duration: " + str(seq.duration))
            p("    priority: " + str(seq.priority))
            p("    firstGroundFrame: " + str(seq.firstGroundFrame))
            p("    numGroundFrames: " + str(seq.numGroundFrames))
            p("    baseRotation: " + str(seq.baseRotation))
            p("    baseTranslation: " + str(seq.baseTranslation))
            p("    baseScale: " + str(seq.baseScale))
            p("    baseObjectState: " + str(seq.baseObjectState))
            p("    baseDecalState: " + str(seq.baseDecalState))
            p("    firstTrigger: " + str(seq.firstTrigger))
            p("    numTriggers: " + str(seq.numTriggers))
            p("    toolBegin: " + str(seq.toolBegin))
            p("    rotationMatters: " + show_matters(seq.rotationMatters))
            p("    translationMatters: " + show_matters(seq.translationMatters))
            p("    scaleMatters: " + show_matters(seq.scaleMatters))
            p("    decalMatters: " + show_matters(seq.decalMatters))
            p("    iflMatters: " + show_matters(seq.iflMatters))
            p("    visMatters: " + show_matters(seq.visMatters))
            p("    frameMatters: " + show_matters(seq.frameMatters))
            p("    matFrameMatters: " + show_matters(seq.matFrameMatters))

        p("Names (" + str(len(shape.names)) + "):")
        for i, name in enumerate(shape.names):
            p("  " + str(i) + " = " + name)
