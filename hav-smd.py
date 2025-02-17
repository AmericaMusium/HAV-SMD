import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.types import Operator, Panel
from bpy.props import BoolProperty
import mathutils

bl_info = {
    "name": "Hard Vertex Group Assign with Highlight SMD GoldSrc",
    "author": "Psycrow+America+DeepSeek",
    "version": (1, 7),  # Увеличил версию до 1.7
    "blender": (4, 1, 0),
    "location": "Properties Editor > Object Data > Vertex Groups",
    "description": "Assign selected vertices to active group with highlighting options",
    "warning": "",
    "category": "Mesh",
}

# Global variables
draw_handler = None
shader = gpu.shader.from_builtin('UNIFORM_COLOR')

# Properties
def init_properties():
    bpy.types.Scene.vg_show_vertices = BoolProperty(
        name="Show Vertices",
        description="Highlight vertices in active group",
        default=True
    )
    bpy.types.Scene.vg_show_edges = BoolProperty(
        name="Show Edges",
        description="Highlight edges between vertices in active group",
        default=True
    )

def clear_properties():
    del bpy.types.Scene.vg_show_vertices
    del bpy.types.Scene.vg_show_edges

def get_face_edges(faces):
    """Convert faces to line segments for drawing"""
    edges = set()  # Используем множество для избежания дубликатов рёбер
    for face in faces:
        verts = face.vertices
        for i in range(len(verts)):
            edge = tuple(sorted((verts[i], verts[(i+1)%len(verts)])))  # Сортируем, чтобы избежать дубликатов (a, b) и (b, a)
            edges.add(edge)
    return list(edges)  # Возвращаем список рёбер

def is_vertex_visible(vertex, context):
    """Check if a vertex is visible (not hidden)"""
    return not vertex.hide


import gpu
from gpu_extras.batch import batch_for_shader

# Вершинный шейдер (оставляем старый)
vertex_shader_code = """
uniform mat4 ModelViewProjectionMatrix;

in vec3 pos;

void main() {
    gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
}
"""

# Фрагментный шейдер для пунктирных линий
fragment_shader_code_dashed = """
uniform vec4 color;
uniform float dashSize;  // Длина пунктира
uniform float gapSize;   // Длина пробела

out vec4 fragColor;

void main() {
    float coord = gl_FragCoord.x;  // Используем координату X для создания эффекта пунктира
    if (mod(coord, dashSize + gapSize) < dashSize) {
        fragColor = color;  // Рисуем пунктир
    } else {
        discard;  // Пропускаем отрисовку (пробел)
    }
}
"""

# Создаём шейдер для пунктирных линий
dashed_shader = gpu.types.GPUShader(vertex_shader_code, fragment_shader_code_dashed)

def draw_highlight():
    """Draw highlighted elements based on settings"""
    scene = bpy.context.scene
    obj = bpy.context.object
    
    if not obj or obj.type != 'MESH' or not obj.vertex_groups.active:
        return

    active_vg = obj.vertex_groups.active
    mesh = obj.data
    
    # Get vertices in active group
    active_verts = set()
    for v in mesh.vertices:
        for g in v.groups:
            if g.group == active_vg.index:
                active_verts.add(v.index)
                break
    
    # Prepare data for drawing
    verts_to_draw = []
    edges_to_draw = []

    # Vertices highlighting
    if scene.vg_show_vertices:
        for v in mesh.vertices:
            if v.index in active_verts and is_vertex_visible(v, bpy.context):
                verts_to_draw.append(v.co)
    
    # Edges highlighting
    if scene.vg_show_edges:
        for edge in mesh.edges:
            if edge.vertices[0] in active_verts and edge.vertices[1] in active_verts:
                v1 = mesh.vertices[edge.vertices[0]]
                v2 = mesh.vertices[edge.vertices[1]]
                if is_vertex_visible(v1, bpy.context) and is_vertex_visible(v2, bpy.context):
                    edges_to_draw.append(tuple(sorted(edge.vertices)))

    # Draw visible vertices (используем старый шейдер)
    if verts_to_draw:
        batch = batch_for_shader(shader, 'POINTS', {"pos": verts_to_draw})
        shader.uniform_float("color", (1, 0, 0.1, 0.8))  # Ярко-красный для видимых вершин
        batch.draw(shader)

    # Draw visible edges (используем новый шейдер для пунктирных линий)
    if edges_to_draw:
        edge_coords = []
        for edge in edges_to_draw:
            edge_coords.append(mesh.vertices[edge[0]].co)
            edge_coords.append(mesh.vertices[edge[1]].co)
        
        # Создаём батч для отрисовки
        batch = batch_for_shader(dashed_shader, 'LINES', {"pos": edge_coords})
        
        # Устанавливаем параметры шейдера
        dashed_shader.uniform_float("color", (0, 1, 0.5, 0.4))  # Зелёный цвет с прозрачностью 40%
        dashed_shader.uniform_float("dashSize", 10.0)  # Длина пунктира
        dashed_shader.uniform_float("gapSize", 5.0)  # Длина пробела
        
        # Включаем смешивание для прозрачности (если нужно)
        gpu.state.blend_set('ALPHA')
        
        # Отрисовываем
        batch.draw(dashed_shader)
        
        # Выключаем смешивание
        gpu.state.blend_set('NONE')
        

class OBJECT_OT_HARD_ASSIGN(Operator):
    bl_idname = "object.hard_assign"
    bl_label = "Hard Assign"
    bl_description = "Assign selected vertices to active group and remove from others"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob and ob.type == 'MESH' and ob.vertex_groups.active

    def execute(self, context):
        ob = context.object
        active_vg = ob.vertex_groups.active
        mesh = ob.data

        # Save current mode and switch to Object mode
        original_mode = ob.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Get selected vertices
        selected_verts = [v.index for v in mesh.vertices if v.select]
        if not selected_verts:
            self.report({'WARNING'}, "No vertices selected")
            return {'CANCELLED'}

        # Remove from all groups except active
        for vg in ob.vertex_groups:
            if vg != active_vg:
                vg.remove(selected_verts)

        # Add to active group
        active_vg.add(selected_verts, 1.0, 'REPLACE')

        # Restore original mode
        if original_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

class OBJECT_OT_UNSIGN_FROM_ALL_GROUPS(Operator):
    bl_idname = "object.unsign_from_all_groups"
    bl_label = "Unsign from all groups"
    bl_description = "Remove selected vertices from all vertex groups"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob and ob.type == 'MESH' and ob.vertex_groups

    def execute(self, context):
        ob = context.object
        mesh = ob.data

        # Save current mode and switch to Object mode
        original_mode = ob.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Get selected vertices
        selected_verts = [v.index for v in mesh.vertices if v.select]
        if not selected_verts:
            self.report({'WARNING'}, "No vertices selected")
            return {'CANCELLED'}

        # Remove from all groups
        for vg in ob.vertex_groups:
            vg.remove(selected_verts)

        # Restore original mode
        if original_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, f"Removed {len(selected_verts)} vertices from all groups")
        return {'FINISHED'}

class OBJECT_OT_SELECT_UNSIGNED_VERTICES(Operator):
    bl_idname = "object.select_unsigned_vertices"
    bl_label = "Select Unsigned Vertices"
    bl_description = "Select vertices that are not assigned to any vertex group"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob and ob.type == 'MESH'

    def execute(self, context):
        ob = context.object
        mesh = ob.data

        # Save current mode and switch to Object mode
        original_mode = ob.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Deselect all vertices
        for v in mesh.vertices:
            v.select = False

        # Select vertices not in any group
        unsigned_verts = []
        for v in mesh.vertices:
            if not v.groups:
                v.select = True
                unsigned_verts.append(v.index)

        # Restore original mode
        if original_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, f"Selected {len(unsigned_verts)} unsigned vertices")
        return {'FINISHED'}

def draw_button(self, context):
    if (context.object and 
        context.object.type == 'MESH' and 
        context.object.mode == 'EDIT'):
        col = self.layout.column(align=True)
        col.operator(OBJECT_OT_HARD_ASSIGN.bl_idname, text="Hard Assign")
        col.operator(OBJECT_OT_UNSIGN_FROM_ALL_GROUPS.bl_idname, text="Unsign from all groups")
        col.operator(OBJECT_OT_SELECT_UNSIGNED_VERTICES.bl_idname, text="Select Unsigned Vertices")
        
        # Добавляем кнопки управления подсветкой
        col.separator()
        col.prop(context.scene, "vg_show_vertices", toggle=True, text="Show Vertices")
        col.prop(context.scene, "vg_show_edges", toggle=True, text="Show Edges")

def register():
    init_properties()
    bpy.utils.register_class(OBJECT_OT_HARD_ASSIGN)
    bpy.utils.register_class(OBJECT_OT_UNSIGN_FROM_ALL_GROUPS)
    bpy.utils.register_class(OBJECT_OT_SELECT_UNSIGNED_VERTICES)
    bpy.types.DATA_PT_vertex_groups.append(draw_button)

    # Регистрируем шейдеры
    global dashed_shader
    dashed_shader = gpu.types.GPUShader(vertex_shader_code, fragment_shader_code_dashed)
    
    global draw_handler
    draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_highlight, (), 'WINDOW', 'POST_VIEW'
    )

def unregister():
    clear_properties()
    bpy.types.DATA_PT_vertex_groups.remove(draw_button)
    bpy.utils.unregister_class(OBJECT_OT_SELECT_UNSIGNED_VERTICES)
    bpy.utils.unregister_class(OBJECT_OT_UNSIGN_FROM_ALL_GROUPS)
    bpy.utils.unregister_class(OBJECT_OT_HARD_ASSIGN)
    # Удаляем шейдеры
    global dashed_shader
    del dashed_shader

    global draw_handler
    if draw_handler:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')

# Регистрация модуля
if __name__ == "__main__":
    register()