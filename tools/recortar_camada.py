from qgis.PyQt.QtWidgets import QAction, QInputDialog, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsMapLayerType, QgsProject, QgsGeometry, QgsWkbTypes
import os

from .ferramenta_base import AqueductTool

class RecortarCamadaTool(AqueductTool):
    """
    Ferramenta para recortar (Clip) a camada ativa usando outra camada como máscara.
    A operação é feita IN-PLACE (atualiza as geometrias existentes).
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_recortar_camada.svg')
        
        self.action = QAction(QIcon(icon_path), 'Recortar pela Máscara (In-Place)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        target_layer = self.iface.activeLayer()
        
        # 1. Validação da Camada Alvo
        if not target_layer or target_layer.type() != QgsMapLayerType.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione a camada que será RECORTADA (Alvo).", level=3, duration=5)
            return

        if not target_layer.isEditable():
             res = QMessageBox.question(
                 self.iface.mainWindow(),
                 "Aqueduct - Modo Edição",
                 "A camada alvo não está em modo de edição. Deseja iniciar a edição? (A operação modificará os dados permanentemente ao salvar)",
                 QMessageBox.Yes | QMessageBox.No
             )
             if res != QMessageBox.Yes:
                 return
             target_layer.startEditing()

        # 2. Seleção da Máscara
        # Lista camadas de polígono (geralmente máscaras são polígonos)
        valid_layers = []
        for lid, layer in QgsProject.instance().mapLayers().items():
            if layer.id() == target_layer.id():
                continue # Não pode recortar por si mesma (poderia, mas complexo)
            if layer.type() == QgsMapLayerType.VectorLayer and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                valid_layers.append(layer)
        
        if not valid_layers:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma camada de POLÍGONO encontrada para usar como máscara.", level=3, duration=5)
            return
            
        layer_names = [l.name() for l in valid_layers]
        item, ok = QInputDialog.getItem(
            self.iface.mainWindow(), 
            "Aqueduct - Seleção de Máscara", 
            "Selecione a camada MÁSCARA (Polígono):", 
            layer_names, 
            0, 
            False
        )
        
        if not ok or not item:
            return
            
        mask_layer = None
        for layer in valid_layers:
            if layer.name() == item:
                mask_layer = layer
                break
        
        if not mask_layer:
            return

        # 3. Processamento
        self.iface.messageBar().pushMessage("Aqueduct", "Preparando máscara... (Isso pode demorar)", level=0, duration=5)
        
        # Combinar geometrias da máscara (Union)
        # Se houver seleção na máscara, usa apenas a seleção
        if mask_layer.selectedFeatureCount() > 0:
            mask_features = mask_layer.selectedFeatures()
        else:
            mask_features = mask_layer.getFeatures()
            
        # Cria geometria unificada da máscara para o recorte
        # Unary Union pode ser pesado.
        combined_mask = QgsGeometry.unaryUnion([f.geometry() for f in mask_features])
        
        if combined_mask.isEmpty():
             self.iface.messageBar().pushMessage("Aqueduct", "Geometria da máscara vazia.", level=3, duration=5)
             return

        # Determinar alvo
        if target_layer.selectedFeatureCount() > 0:
            target_features = target_layer.selectedFeatures()
            mode_msg = "apenas nas feições selecionadas"
        else:
            target_features = target_layer.getFeatures()
            mode_msg = "em todas as feições"

        self.iface.messageBar().pushMessage("Aqueduct", "Recortando...", level=0, duration=5)
        
        count_mod = 0
        count_del = 0
        
        # Buffer de updates para performance
        # No entanto, changeGeometry é imediato em edição.
        
        target_layer.beginEditCommand("Recortar pela Máscara")
        
        for feat in target_features:
            geom = feat.geometry()
            if not geom:
                continue
                
            # Interseção
            # Nota: geometry() retorna uma cópia, então é seguro.
            new_geom = geom.intersection(combined_mask)
            
            if new_geom.isEmpty() or new_geom.isNull():
                # Se a interseção é vazia, a feição está totalmente fora da máscara
                # Deve ser deletada? "Recortar" geralmente mantém o que está DENTRO.
                # Se não sobrou nada dentro, deleta.
                target_layer.deleteFeature(feat.id())
                count_del += 1
            else:
                # Se mudou algo
                if not new_geom.equals(geom):
                    target_layer.changeGeometry(feat.id(), new_geom)
                    count_mod += 1
        
        target_layer.endEditCommand()
        target_layer.triggerRepaint()

        # 4. Relatório
        msg = f"Recorte concluído {mode_msg}. Modificados: {count_mod}. Removidos (fora da máscara): {count_del}."
        self.iface.messageBar().pushMessage("Aqueduct", msg, level=0, duration=10)
