bl_info = {
    "name": "Torque DTS format",
    "author": "ns",
    "version": (0, 1, 0),
    "blender": (2, 81, 0),
    "location": "File > Import-Export",
    "description": "Import-Export DTS, DSQ",
    "warning": "",
    "category": "Import-Export",
}

if "bpy" in locals():
    import importlib
    if "import_torque" in locals():
        importlib.reload(import_torque)

import bpy
from bpy.props import (
    StringProperty,
)
from bpy_extras.io_utils import (
    ImportHelper,
    ExportHelper,
    orientation_helper,
    path_reference_mode,
    axis_conversion,
)

class ImportDtsDsq(bpy.types.Operator, ImportHelper):
    """Load a Torque DTS/DSQ file"""
    bl_idname = "import_scene.torque_dts_dsq"
    bl_label = "Import DTS/DSQ"
    bl_options = {'PRESET', 'UNDO'}

    filter_glob: StringProperty(
        default="*.dts;*.dsq",
        options={'HIDDEN'},
    )

    def execute(self, context):
        from . import import_torque
        keywords = self.as_keywords(ignore=(
            "filter_glob",
        ))
        return import_torque.load(context, **keywords)

class ExportDts(bpy.types.Operator, ExportHelper):
    """Save a Torque DTS file"""

    bl_idname = "export_scene.dsq"
    bl_label = "Export DSQ"
    bl_options = {'PRESET'}

    filename_ext = ".dsq"
    filter_glob: StringProperty(
        default="*.dsq",
        options={'HIDDEN'},
    )

class ExportDsq(bpy.types.Operator, ExportHelper):
    """Save a Torque DSQ file"""

    bl_idname = "export_scene.dts"
    bl_label = "Export DTS"
    bl_options = {'PRESET'}

    filename_ext = ".dts"
    filter_glob: StringProperty(
        default="*.dts",
        options={'HIDDEN'},
    )

def menu_func_import(self, context):
    self.layout.operator(ImportDtsDsq.bl_idname, text="Torque (.dts/.dsq)")

def menu_func_export(self, context):
    self.layout.operator(ExportDts.bl_idname, text="Torque (.dts)")
    self.layout.operator(ExportDsq.bl_idname, text="Torque Sequences (.dsq)")

classes = (
    ImportDtsDsq,
    ExportDts,
    ExportDsq,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
