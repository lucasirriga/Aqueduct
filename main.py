import os
import sys
import importlib
import inspect
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtGui import QIcon

from .tools.base_tool import AqueductTool

class AqueductPlugin:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.tools = []
        self.menu_name = '&Aqueduct'

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        
        # Cria o menu se não existir (o QGIS gerencia isso, mas garantimos a referência)
        # Na verdade, self.iface.addPluginToMenu lida com a criação do menu pai se necessário
        
        # Loader Dinâmico de Ferramentas
        self.load_tools()

    def load_tools(self):
        """Varre o diretório tools/ e carrega as subclasses de AqueductTool."""
        tools_dir = os.path.join(self.plugin_dir, 'tools')
        sys.path.append(tools_dir) # Garante que podemos importar

        for filename in os.listdir(tools_dir):
            if filename.endswith(".py") and filename != "__init__.py" and filename != "base_tool.py":
                module_name = filename[:-3]
                try:
                    # Importa o módulo dinamicamente
                    # Nota: em um plugin real, usar importlib com o pacote do plugin é mais seguro
                    # Mas como adicionamos ao path ou estamos no mesmo pacote relativa...
                    # Vamos usar import relativo calcado no nome do pacote
                    
                    package = "Aqueduct.tools"
                    module = importlib.import_module(f".tools.{module_name}", package="Aqueduct")
                    
                    # Procura por subclasses de AqueductTool no módulo
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, AqueductTool) and obj is not AqueductTool:
                            # Instancia e inicializa a ferramenta
                            tool_instance = obj(self.iface)
                            tool_instance.initGui()
                            self.tools.append(tool_instance)
                
                except Exception as e:
                    # Logar erro sem quebrar o plugin inteiro
                    print(f"Erro ao carregar ferramenta {filename}: {e}")
                    # Em QGIS production, usar QgsMessageLog

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for tool in self.tools:
            try:
                tool.unload()
            except Exception as e:
                print(f"Erro ao descarregar ferramenta: {e}")
        
        self.tools = []
