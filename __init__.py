bl_info = {
    "name": "Torque DTS format",
    "author": "Nick Smith (port)",
    "version": (0, 0, 1),
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
    if "export_dts" in locals():
        importlib.reload(export_dts)


import bpy
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       )
from bpy_extras.io_utils import (ImportHelper,
                                 ExportHelper,
                                 orientation_helper_factory,
                                 path_reference_mode,
                                 axis_conversion,
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

    include_armatures = BoolProperty(
        name="Armatures",
        description="Import the full node->object hierarchy",
        default=True,
        )

    hide_default_player = BoolProperty(
        name="Hide Blockhead Nodes",
        description="Set extra avatar nodes to hidden",
        default=False,
        )

    def execute(self, context):
        from . import import_dts

        keywords = self.as_keywords(ignore=("filter_glob", "split_mode"))
        return import_dts.load(self, context, **keywords)

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

    # context group
    use_selection = BoolProperty(
            name="Selection Only",
            description="Export selected objects only",
            default=False,
            )

    check_extension = True

    def execute(self, context):
        from . import export_dts

        from mathutils import Matrix
        keywords = self.as_keywords(ignore=("check_existing", "filter_glob"))
        return export_dts.save(self, context, **keywords)


def menu_func_import(self, context):
    self.layout.operator(ImportDTS.bl_idname, text="Torque (.dts)")


def menu_func_export(self, context):
    self.layout.operator(ExportDTS.bl_idname, text="Torque (.dts)")


def register():
    bpy.utils.register_module(__name__)

    bpy.types.INFO_MT_file_import.append(menu_func_import)
    # bpy.types.INFO_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_module(__name__)

    bpy.types.INFO_MT_file_import.remove(menu_func_import)
    # bpy.types.INFO_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
