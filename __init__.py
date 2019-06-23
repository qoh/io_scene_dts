bl_info = {
    "name": "Torque DTS format",
    "author": "port",
    "version": (0, 3, 0),
    "blender": (2, 80, 0),
    "location": "File > Import-Export",
    "description": "Import-Export DTS meshes, UV's, materials and animations",
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
    if "util" in locals():
        importlib.reload(util)

is_developer = False
try:
    from .developer import is_developer
except ImportError:
    pass

if is_developer:
    debug_prop_options = set()
else:
    debug_prop_options = {'HIDDEN'}

import bpy
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
    EnumProperty,
    PointerProperty,
    )
from bpy_extras.io_utils import (
    ImportHelper,
    ExportHelper,
    )

class ImportDTS(bpy.types.Operator, ImportHelper):
    """Load a Torque DTS File"""
    bl_idname = "import_scene.dts"
    bl_label = "Import DTS"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = ".dts"
    filter_glob: StringProperty(
        default="*.dts",
        options={'HIDDEN'},
        )

    reference_keyframe: BoolProperty(
        name="Reference keyframe",
        description="Set a keyframe with the reference pose for blend animations",
        default=True,
        )

    import_sequences: BoolProperty(
        name="Import sequences",
        description="Automatically add keyframes for embedded sequences",
        default=True,
        )

    use_armature: BoolProperty(
        name="Experimental: Skeleton as armature",
        description="Import bones into an armature instead of empties. Does not work with 'Import sequences'",
        default=False,
        )

    debug_report: BoolProperty(
        name="Write debug report",
        description="Dump out all the information from the DTS to a file",
        options=debug_prop_options,
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
    filter_glob: StringProperty(
        default="*.dsq",
        options={'HIDDEN'},
        )

    debug_report: BoolProperty(
        name="Write debug report",
        description="Dump out all the information from the DSQ to a file",
        options=debug_prop_options,
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
    filter_glob: StringProperty(
        default="*.dts",
        options={'HIDDEN'},
        )

    select_object: BoolProperty(
        name="Selected objects only",
        description="Export selected objects (empties, meshes) only",
        default=False,
        )
    select_marker: BoolProperty(
        name="Selected markers only",
        description="Export selected timeline markers only, used for sequences",
        default=False,
        )

    blank_material: BoolProperty(
        name="Blank material",
        description="Add a blank material to meshes with none assigned",
        default=True,
        )

    generate_texture: EnumProperty(
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

    apply_modifiers: BoolProperty(
        name="Apply modifiers",
        description="Apply modifiers to meshes",
        default=True,
        )

    debug_report: BoolProperty(
        name="Write debug report",
        description="Dump out all the information from the DTS to a file",
        options=debug_prop_options,
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
    filter_glob: StringProperty(
        default="*.dsq",
        options={'HIDDEN'},
        )

    select_marker: BoolProperty(
        name="Selection only",
        description="Export selected timeline markers only",
        default=False,
        )

    debug_report: BoolProperty(
        name="Write debug report",
        description="Dump out all the information from the DSQ to a file",
        options=debug_prop_options,
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

class HideBlockheadNodes(bpy.types.Operator):
    """Set all non-default Blockhead model apparel meshes as hidden"""

    bl_idname = "mesh.hide_blockhead_nodes"
    bl_label = "Hide Blockhead nodes on selection"
    bl_options = {"REGISTER", "UNDO"}

    blacklist = (
        "copHat",
        "knitHat",
        "pack",
        "quiver",
        "femChest",
        "epauletsRankB",
        "epauletsRankC",
        "epauletsRankD",
        "epauletsRankA",
        "skirtHip",
        "skirtTrimRight",
        "RHook",
        "RarmSlim",
        "LHook",
        "LarmSlim",
        "PointyHelmet",
        "Helmet",
        "bicorn",
        "scoutHat",
        "FlareHelmet",
        "triPlume",
        "plume",
        "septPlume",
        "tank",
        "armor",
        "cape",
        "Bucket",
        "epaulets",
        "ShoulderPads",
        "Rski",
        "Rpeg",
        "Lski",
        "Lpeg",
        "skirtTrimLeft",
        "Visor",
    )

    def execute(self, context):
        for ob in context.selected_objects:
            if ob.type == "MESH" and ob.name in self.blacklist:
                ob.hide_viewport = True
                ob.hide_render = True

        return {"FINISHED"}

class TorqueMaterialProperties(bpy.types.PropertyGroup):
    blend_mode: EnumProperty(
        name="Blend mode",
        items=(
            ("ADDITIVE", "Additive", "White is white, black is transparent"),
            ("SUBTRACTIVE", "Subtractive", "White is black, black is transparent"),
            ("NONE", "None", "I don't know how to explain this, try it yourself"),
        ),
        default="ADDITIVE")
    s_wrap: BoolProperty(name="S-Wrap", default=True)
    t_wrap: BoolProperty(name="T-Wrap", default=True)
    use_ifl: BoolProperty(name="IFL")
    ifl_name: StringProperty(name="Name")

class TorqueMaterialPanel(bpy.types.Panel):
    bl_idname = "MATERIAL_PT_torque"
    bl_label = "Torque"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (context.material is not None)

    def draw(self, context):
        layout = self.layout
        obj = context.material

        sublayout = layout.row()
        sublayout.enabled = obj.use_transparency
        sublayout.prop(obj.torque_props, "blend_mode", expand=True)

        row = layout.row()
        row.prop(obj.torque_props, "use_ifl")
        sublayout = row.column()
        sublayout.enabled = obj.torque_props.use_ifl
        sublayout.prop(obj.torque_props, "ifl_name", text="")
        sublayout = layout.column()
        sublayout.enabled = obj.torque_props.use_ifl

def menu_func_import_dts(self, context):
    self.layout.operator(ImportDTS.bl_idname, text="Torque (.dts)")

def menu_func_import_dsq(self, context):
    self.layout.operator(ImportDSQ.bl_idname, text="Torque Sequences (.dsq)")

def menu_func_export_dts(self, context):
    self.layout.operator(ExportDTS.bl_idname, text="Torque (.dts)")

def menu_func_export_dsq(self, context):
    self.layout.operator(ExportDSQ.bl_idname, text="Torque Sequences (.dsq)")

classes = (
    ImportDTS,
    ImportDSQ,
    ExportDTS,
    ExportDSQ,
    SplitMeshIndex,
    HideBlockheadNodes,
    TorqueMaterialProperties,
    TorqueMaterialPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Material.torque_props = PointerProperty(
        type=TorqueMaterialProperties)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_dts)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_dsq)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_dts)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_dsq)

def unregister():
    del bpy.types.Material.torque_props

    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_dts)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_dsq)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_dts)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_dsq)

    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
