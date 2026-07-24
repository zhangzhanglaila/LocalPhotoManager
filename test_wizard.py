import sys
import os

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

os.environ['QT_QPA_PLATFORM'] = 'offscreen'  # 使用离屏模式

try:
    from PySide6.QtWidgets import QApplication
    from iPhoto.bootstrap.runtime_context import RuntimeContext
    from iPhoto.utils.pathutils import set_custom_workspace_base
    
    print("Testing welcome wizard...")
    
    # 创建应用实例
    app = QApplication.instance() or QApplication([])
    
    # 创建运行时上下文
    context = RuntimeContext.create(defer_startup=True)
    
    # 清除自定义工作目录设置以模拟需要配置的情况
    set_custom_workspace_base(None)
    
    # 测试 needs_workspace_config
    needs_config = context.needs_workspace_config()
    print(f"needs_workspace_config() = {needs_config}")
    
    if needs_config:
        print("Showing welcome wizard...")
        result = context.show_welcome_wizard()
        print(f"User selected: {result}")
    else:
        print("No workspace config needed")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

