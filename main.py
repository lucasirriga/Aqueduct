import os
import sys
import importlib
import inspect
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtGui import QIcon

from .tools.ferramenta_base import AqueductTool

class AqueductPlugin:
    """Implementação do Plugin QGIS Aqueduct."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.tools = []
        self.menu_name = '&Aqueduct'

    def initGui(self):
        """Cria as entradas de menu e ícones da barra de ferramentas na interface do QGIS."""
        
        # Cria Toolbar dedicada
        self.toolbar = self.iface.addToolBar("Aqueduct")
        self.toolbar.setObjectName("AqueductToolbar")
        
        # Loader Dinâmico de Ferramentas
        self.load_tools()

    def load_tools(self):
        """Varre o diretório tools/ e carrega as subclasses de AqueductTool."""
        tools_dir = os.path.join(self.plugin_dir, 'tools')
        # sys.path.append(tools_dir) # Não necessário se usarmos import relativo correto ou importlib robusto

        for filename in os.listdir(tools_dir):
            if filename.endswith(".py") and filename != "__init__.py" and filename != "ferramenta_base.py":
                module_name = filename[:-3]
                try:
                    # Importação robusta usando importlib
                    # Assume que 'tools' é um subpacote do plugin atual
                    if __package__:
                        package = f"{__package__}.tools"
                    else:
                        package = "tools"
                        
                    module = importlib.import_module(f".{module_name}", package=package)
                    
                    # Procura por subclasses de AqueductTool no módulo
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, AqueductTool) and obj is not AqueductTool:
                            # Instancia e inicializa a ferramenta passando a toolbar
                            tool_instance = obj(self.iface, self.toolbar)
                            tool_instance.initGui()
                            self.tools.append(tool_instance)
                
                except Exception as e:
                    print(f"Erro ao carregar ferramenta {filename}: {e}")
                    # Mostra erro na MessageBar para debug do usuário
                    self.iface.messageBar().pushMessage(
                        "Aqueduct Error", 
                        f"Falha ao carregar {filename}: {e}", 
                        level=2, # Warning
                        duration=10
                    )

    def unload(self):
        """Remove o item de menu do plugin e o ícone da interface do QGIS."""
        for tool in self.tools:
            try:
                tool.unload()
            except Exception as e:
                print(f"Erro ao descarregar ferramenta: {e}")
        
        # Remove a toolbar
        if hasattr(self, 'toolbar'):
            del self.toolbar
            
        self.tools = []
