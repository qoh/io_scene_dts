bl_info = {
    "name": "Torque DTS format",
    "author": "port",
    "version": (0, 1, 0),
    "blender": (2, 74, 0),
    "location": "File > Import-Export",
    "description": "Import-Export DTS, Import DTS mesh, UV's, "
                   "materials and textures",
    "warning": "",
    "support": 'COMMUNITY',
    "category": "Import-Export"}

if "bpy" in locals():
    import importlib
    if "import_dts" in locals():
        importlib.reload(import_dts)
    if "import_dsq" in locals():
        importlib.reload(import_dsq)
    if "export_dts" in locals():
        importlib.reload(export_dts)
    if "export_dsq" in locals():
        importlib.reload(export_dsq)


import bpy
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       )
from bpy_extras.io_utils import (ImportHelper,
                                 ExportHelper,
                                 )

class ImportDTS(bpy.types.Operator, ImportHelper):
    """Load a Torque DTS File"""
    bl_idname = "import_scene.dts"
    bl_label = "Import DTS"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = ".dts"
    filter_glob = StringProperty(
            default="*.dts",
            options={'HIDDEN'},
            )

    hide_default_player = BoolProperty(
        name="Hide Blockhead Nodes",
        description="Set extra avatar nodes to hidden",
        default=False,
        )

    import_node_order = BoolProperty(
            name="Import node order",
            description="Creates the NodeOrder text block for compatibility with existing DSQ files for this skeleton",
            default=False,
            )
    
    reference_keyframe = BoolProperty(
            name="Reference keyframe",
            description="Set a keyframe with the reference pose for blend animations",
            default=False,
            )

    import_sequences = BoolProperty(
            name="Import sequences",
            description="Automatically add keyframes for embedded sequences",
            default=True,
            )

    debug_report = BoolProperty(
        name="Write debug report",
        description="Dump out all the information from the DTS to a file",
        default=False,
        )

    def execute(self, context):
        from . import import_dts

        keywords = self.as_keywords(ignore=("filter_glob", "split_mode"))
        return import_dts.load(self, context, **keywords)

class ImportDSQ(bpy.types.Operator, ImportHelper):
    """Load a Torque DSQ File"""
    bl_idname = "import_scene.dsq"
    bl_label = "Import DSQ"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = ".dsq"
    filter_glob = StringProperty(
            default="*.dsq",
            options={'HIDDEN'},
            )

    debug_report = BoolProperty(
        name="Write debug report",
        description="Dump out all the information from the DSQ to a file",
        default=False,
        )

    def execute(self, context):
        from . import import_dsq

        keywords = self.as_keywords(ignore=("filter_glob", "split_mode"))
        return import_dsq.load(self, context, **keywords)

class ExportDTS(bpy.types.Operator, ExportHelper):
    """Save a Torque DTS File"""

    bl_idname = "export_scene.dts"
    bl_label = 'Export DTS'
    bl_options = {'PRESET'}

    filename_ext = ".dts"
    filter_glob = StringProperty(
            default="*.dts",
            options={'HIDDEN'},
            )

    # use_selection = BoolProperty(
    #         name="Selection Only",
    #         description="Export selected objects only",
    #         default=False,
    #         )

    blank_material = BoolProperty(
            name="Blank material",
            description="Add a blank material to meshes with none assigned",
            default=True,
            )

    generate_texture = EnumProperty(
            name="Generate textures",
            description="Automatically generate solid color textures for materials",
            default="disabled",
            items=(
                ("disabled", "Disabled", "Do not generate any textures"),
                ("custom-missing", "Custom (if missing)", "Generate textures for non-default material names if not already present"),
                ("custom-always", "Custom (always)", "Generate textures for non-default material names"),
                ("all-missing", "All (if missing)", "Generate textures for all materials if not already present"),
                ("all-always", "All (always)", "Generate textures for all materials"))
            )

    transform_mesh = BoolProperty(
            name="Use mesh transforms",
            description="Apply local location/rotation/scale to geometry",
            default=True,
            )

    apply_modifiers = BoolProperty(
            name="Apply modifiers",
            description="Apply modifiers to meshes",
            default=True,
            )

    debug_report = BoolProperty(
        name="Write debug report",
        description="Dump out all the information from the DTS to a file",
        default=False,
        )

    check_extension = True

    def execute(self, context):
        from . import export_dts
        keywords = self.as_keywords(ignore=("check_existing", "filter_glob"))
        return export_dts.save(self, context, **keywords)

class ExportDSQ(bpy.types.Operator, ExportHelper):
    """Save many Torque DSQ Files"""

    bl_idname = "export_scene.dsq"
    bl_label = 'Export DSQ'
    bl_options = {'PRESET'}

    filename_ext = ".dsq"
    filter_glob = StringProperty(
            default="*.dsq",
            options={'HIDDEN'},
            )

    # use_selection = BoolProperty(
    #         name="Selection Only",
    #         description="Export selected objects only",
    #         default=False,
    #         )

    debug_report = BoolProperty(
        name="Write debug report",
        description="Dump out all the information from the DSQ to a file",
        default=False,
        )

    check_extension = True

    def execute(self, context):
        from . import export_dsq
        keywords = self.as_keywords(ignore=("check_existing", "filter_glob"))
        return export_dsq.save(self, context, **keywords)

class SplitMeshIndex(bpy.types.Operator):
    """Split a mesh into new meshes limiting the number of indices"""

    bl_idname = "mesh.split_mesh_vindex"
    bl_label = "Split mesh by indices"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        limit = 10922

        ob = context.active_object

        if ob is None or ob.type != "MESH":
            self.report({"ERROR"}, "Select a mesh object first")
            return {"FINISHED"}

        me = ob.data

        out_me = None
        out_ob = None

        def split():
            nonlocal out_me
            nonlocal out_ob

            if out_me is not None:
                out_me.validate()
                out_me.update()

            out_me = bpy.data.meshes.new(ob.name)
            out_ob = bpy.data.objects.new(ob.name, out_me)

            context.scene.objects.link(out_ob)

            # For now, copy all verts over. See what happens?
            out_me.vertices.add(len(me.vertices))

            for vert, out_vert in zip(me.vertices, out_me.vertices):
                out_vert.co = vert.co
                out_vert.normal = vert.normal

        split()

        for poly in me.polygons:
            if poly.loop_total >= limit:
                continue

            if len(out_me.loops) + poly.loop_total > limit:
                split()

            loop_start = len(out_me.loops)
            out_me.loops.add(poly.loop_total)

            out_me.polygons.add(1)
            out_poly = out_me.polygons[-1]

            out_poly.loop_start = loop_start
            out_poly.loop_total = poly.loop_total
            out_poly.use_smooth = poly.use_smooth

            for loop_index, out_loop_index in zip(poly.loop_indices, out_poly.loop_indices):
                loop = me.loops[loop_index]
                out_loop = out_me.loops[out_loop_index]

                out_loop.normal = loop.normal
                out_loop.vertex_index = loop.vertex_index

        out_me.validate()
        out_me.update()

        return {"FINISHED"}

def menu_func_import_dts(self, context):
    self.layout.operator(ImportDTS.bl_idname, text="Torque (.dts)")

def menu_func_import_dsq(self, context):
    self.layout.operator(ImportDSQ.bl_idname, text="Torque Sequences (.dsq)")

def menu_func_export_dts(self, context):
    self.layout.operator(ExportDTS.bl_idname, text="Torque (.dts)")

def menu_func_export_dsq(self, context):
    self.layout.operator(ExportDSQ.bl_idname, text="Torque Sequences (.dsq)")

def register():
    bpy.utils.register_module(__name__)

    bpy.types.INFO_MT_file_import.append(menu_func_import_dts)
    bpy.types.INFO_MT_file_import.append(menu_func_import_dsq)
    bpy.types.INFO_MT_file_export.append(menu_func_export_dts)
    bpy.types.INFO_MT_file_export.append(menu_func_export_dsq)

def unregister():
    bpy.utils.unregister_module(__name__)

    bpy.types.INFO_MT_file_import.remove(menu_func_import_dts)
    bpy.types.INFO_MT_file_import.remove(menu_func_import_dsq)
    bpy.types.INFO_MT_file_export.remove(menu_func_export_dts)
    bpy.types.INFO_MT_file_export.remove(menu_func_export_dsq)

if __name__ == "__main__":
    register()
