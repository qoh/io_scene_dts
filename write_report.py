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

        p("smallest_size = " + str(shape.smallest_size))
        p("smallest_detail_level = " + str(shape.smallest_detail_level))
        p("radius = " + str(shape.radius))
        p("radius_tube = " + str(shape.radius_tube))
        p("center = " + str(shape.center))
        p("bounds = " + str(shape.bounds))
        # p("Decals (deprecated): " + str(len(shape.decals)))
        # p("IFL materials: " + str(len(shape.iflmaterials)))
        # p("Materials: " + str(len(shape.materials)))
        p("Ground frames: " + str(len(shape.ground_translations)))
        # p("Decal states (deprecated): " + str(len(shape.decalstates)))
        p("Triggers: " + str(len(shape.triggers)))
        p("Sequences: " + str(len(shape.sequences)))

        p("Default translations:")
        for each in shape.default_translations:
            p("  " + str(each))
        for each in shape.default_rotations:
            p("  " + str(each))

        p("Node scales uniform:")
        p(", ".join(map(str, shape.node_scales_uniform)))
        p("Node scales aligned:")
        p(", ".join(map(str, shape.node_scales_aligned)))
        p("Node scales arbitrary:")
        p(", ".join(map(str, shape.node_scales_arbitrary)))
        p("Node scalerots arbitrary:")
        p(", ".join(map(str, shape.node_scalerots_arbitrary)))

        p("Object states (" + str(len(shape.objectstates)) + "):")
        for i, state in enumerate(shape.objectstates):
            p("  " + str(i))
            p("    vis = " + str(state.vis))
            p("    frame = " + str(state.frame))
            p("    matFrame = " + str(state.matFrame))

        p("IFL materials (" + str(len(shape.iflmaterials)) + "):")
        for ifl in shape.iflmaterials:
            p("  IflMat " + gn(ifl.name))
            p("    slot = " + str(ifl.slot))
            p("    firstFrame = " + str(ifl.firstFrame))
            p("    numFrames = " + str(ifl.numFrames))
            p("    time = " + str(ifl.time))

        p("Materials (" + str(len(shape.materials)) + "):")
        for i, mat in enumerate(shape.materials):
            p("  " + str(i) + " " + mat.name)
            flagNames = ("SWrap", "TWrap", "Translucent", "Additive", "Subtractive", "SelfIlluminating", "NeverEnvMap", "NoMipMap", "MipMapZeroBorder", "IFLMaterial", "IFLFrame", "DetailMap", "BumpMap", "ReflectanceMap", "AuxiliaryMask")
            flags = ""
            for name in flagNames:
                if mat.flags & getattr(Material, name):
                    flags += " " + name
            p("    flags = " + str(mat.flags) + flags)
            p("    reflectanceMap = " + str(mat.reflectanceMap))
            p("    reflectance = " + str(mat.reflectance))
            p("    bumpMap = " + str(mat.bumpMap))
            p("    detailMap = " + str(mat.detailMap))
            p("    detailScale = " + str(mat.detailScale))

        p("Detail levels (" + str(len(shape.detail_levels)) + "):")
        for i, lod in enumerate(shape.detail_levels):
            p("  LOD " + str(i) + " " + gn(lod.name))
            # p("    name = " + gn(lod.name))
            p("    subshape = " + str(lod.subshape))
            p("    objectDetail = " + str(lod.objectDetail))
            p("    size = " + str(lod.size))
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
            # p("  Node " + str(i))
            # p("    name = " + gn(node.name))
            # if node.parent == -1:
            #     p("    parent = -1 (NONE)")
            # else:
            #     p("    parent = " + str(node.parent) + " (" + gn(shape.nodes[node.parent].name) + ")")
            # p("    firstObject (deprecated) = " + str(node.firstObject))
            # p("    child (deprecated) = " + str(node.child))
            # p("    sibling (deprecated) = " + str(node.sibling))

        p("Objects (" + str(len(shape.objects)) + "):")
        for i, obj in enumerate(shape.objects):
            p("  " + str(i) + " " + gn(obj.name))
            # p("    name = " + gn(obj.name))
            # p("    numMeshes = " + str(obj.numMeshes))
            # p("    firstMesh = " + str(obj.firstMesh))
            if obj.node == -1:
                p("    node = -1 (none)")
            else:
                p("    node = " + str(obj.node) + " (" + gn(shape.nodes[obj.node].name) + ")")
            # p("    sibling (deprecated) = " + str(obj.sibling))
            # p("    firstDecal (deprecated) = " + str(obj.firstDecal))
            # p("      meshes = " + ln(shape.meshes, obj.firstMesh, obj.numMeshes))
            p("    meshes = " + ln(shape.meshes, obj.firstMesh, obj.numMeshes))

        p("Meshes (" + str(len(shape.meshes)) + "):")
        for i, mesh in enumerate(shape.meshes):
            p("  Mesh " + str(i))
            p("    type = " + mesh.type.name + " (" + str(mesh.type.value) + ")")
            p("    bounds = " + str(mesh.bounds))
            p("    center = " + str(mesh.center))
            p("    radius = " + str(mesh.radius))
            p("    numFrames = " + str(mesh.numFrames))
            p("    matFrames = " + str(mesh.matFrames))
            p("    vertsPerFrame = " + str(mesh.vertsPerFrame))
            p("    parent (unused?) = " + str(mesh.parent))
            p("    flags = " + str(mesh.flags))
            p("    indices = " + ",".join(map(str, mesh.indices)))
            p("    mindices = " + ",".join(map(str, mesh.mindices)))
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
            p("    + Vertices (" + str(len(mesh.verts)) + "):")
            for i in range(len(mesh.verts)):
                p("      vert" + str(i) + " " + str(mesh.verts[i]) + " normal " + str(mesh.normals[i]) + " encoded " + str(mesh.enormals[i]))
            p("    + Texture coords (" + str(len(mesh.tverts)) + "):")
            for i in range(len(mesh.tverts)):
                p("      tvert" + str(i) + " " + str(mesh.tverts[i]))

        p("Names (" + str(len(shape.names)) + "):")
        for i, name in enumerate(shape.names):
            p("  " + str(i) + " = " + name)

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
            p("    rotationMatters: " + str(seq.rotationMatters))
            p("    translationMatters: " + str(seq.translationMatters))
            p("    scaleMatters: " + str(seq.scaleMatters))
            p("    decalMatters: " + str(seq.decalMatters))
            p("    iflMatters: " + str(seq.iflMatters))
            p("    visMatters: " + str(seq.visMatters))
            p("    frameMatters: " + str(seq.frameMatters))
            p("    matFrameMatters: " + str(seq.matFrameMatters))
