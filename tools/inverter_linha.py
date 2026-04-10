from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsMapLayerType, QgsWkbTypes, QgsGeometry
import os

from .ferramenta_base import AqueductTool

class InverterLinhaTool(AqueductTool):
    """
    Ferramenta para inverter a direção (ordem dos vértices) das linhas SELECIONADAS.
    Útil para corrigir fluxo hidráulico.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_inverter.svg')
        
        self.action = QAction(QIcon(icon_path), 'Inverter Direção (Linhas Selecionadas)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        
        # 1. Validações
        if not layer or layer.type() != QgsMapLayerType.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de LINHAS.", level=3, duration=5)
            return

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de LINHA.", level=3, duration=5)
            return

        # 2. Seleção Obrigatória
        selected_count = layer.selectedFeatureCount()
        if selected_count == 0:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma linha selecionada. Selecione as linhas que deseja inverter.", level=2, duration=5)
            return

        # 3. Confirmação (Opccional, mas bom para edições destrutivas em massa)
        # Vamos assumir "Undo" resolve e ser mais ágil, sem popup de confirmação extra além da mensagem final.
        
        if not layer.isEditable():
            res = QMessageBox.question(
                self.iface.mainWindow(),
                "Aqueduct - Modo Edição",
                f"A camada não está editável. Deseja habilitar edição e inverter {selected_count} linhas?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res != QMessageBox.Yes:
                return
            layer.startEditing()

        # 4. Processamento
        layer.beginEditCommand("Inverter Direção de Linhas")
        
        count = 0
        features = layer.selectedFeatures()
        
        for feat in features:
            geom = feat.geometry()
            # QgsGeometry.reversed() retorna uma nova geometria invertida
            # Disponível em APIs recentes. Se falhar, usar asPolyline().
            
            # Método moderno:
            try:
                # new_geom = geom.reversed() # Nem sempre exposto diretamente em todas versoes do PyQGIS wrapper
                # Método seguro via WKB/Polyline
                if geom.isMultipart():
                    lines = geom.asMultiPolyline()
                    new_lines = [list(reversed(line)) for line in lines]
                    new_geom = QgsGeometry.fromMultiPolylineXY(new_lines)
                else:
                    line = geom.asPolyline()
                    new_geom = QgsGeometry.fromPolylineXY(list(reversed(line)))
                
                layer.changeGeometry(feat.id(), new_geom)
                count += 1
            except Exception as e:
                print(f"Erro ao inverter feat {feat.id()}: {e}")

        layer.endEditCommand()
        layer.triggerRepaint()

        # 5. Relatório
        self.iface.messageBar().pushMessage(
            "Aqueduct", 
            f"Inversão concluída em {count} linhas. Verifique a orientação com a ferramenta de setas.", 
            level=0, 
            duration=4
        )
