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

        for filename in sorted(os.listdir(tools_dir)):
            if filename.endswith(".py") and filename != "__init__.py" and filename != "ferramenta_base.py":
                module_name = filename[:-3]
                full_module_name = f"Aqueduct.tools.{module_name}"
                try:
                    # Tenta importar usando o nome completo do pacote
                    if full_module_name in sys.modules:
                        module = importlib.reload(sys.modules[full_module_name])
                    else:
                        module = importlib.import_module(f".tools.{module_name}", package="Aqueduct")
                    
                    # Procura por subclasses de AqueductTool no módulo
                    loaded_count = 0
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, AqueductTool) and obj is not AqueductTool:
                            # Instancia e inicializa a ferramenta passando a toolbar
                            try:
                                tool_instance = obj(self.iface, self.toolbar)
                                tool_instance.initGui()
                                self.tools.append(tool_instance)
                                loaded_count += 1
                                # Log de sucesso removido para produção
                            except Exception as e_inst:
                                self.iface.messageBar().pushMessage("Aqueduct Error", f"Falha ao instanciar {name}: {e_inst}", level=2)
                    
                    if loaded_count == 0:
                         # Warn discreto ou removido, mantendo apenas para devs
                         print(f"Aqueduct Warn: Nenhuma ferramenta encontrada em {filename}")

                except Exception as e:
                    print(f"Erro ao carregar ferramenta {filename}: {e}")
                    # Mostra erro na MessageBar para debug do usuário
                    self.iface.messageBar().pushMessage(
                        "Aqueduct Error", 
                        f"Falha ao carregar arquivo {filename}: {e}", 
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
