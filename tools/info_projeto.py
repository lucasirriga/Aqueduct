from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, 
    QDoubleSpinBox, QPushButton, QMessageBox, QLabel, QComboBox, QGroupBox, QWidget
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import QgsProject, QgsWkbTypes, QgsUnitTypes, QgsDistanceArea
import os
import json

from .ferramenta_base import AqueductTool

class InfoProjetoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aqueduct - Informações do Projeto")
        self.resize(500, 600)
        
        self.project_data = {}
        self.filepath = self.get_filepath()
        
        self.setup_ui()
        self.load_data()

    def get_filepath(self):
        project_home = QgsProject.instance().homePath()
        if not project_home:
            return None
        return os.path.join(project_home, 'dados_projeto.json')

    def setup_ui(self):
        layout = QVBoxLayout()
        
        # --- Cadastro ---
        group_cad = QGroupBox("Dados Cadastrais")
        form_cad = QFormLayout()
        
        self.edit_cliente = QLineEdit()
        self.edit_local = QLineEdit()
        
        form_cad.addRow("Nome do Cliente:", self.edit_cliente)
        form_cad.addRow("Localidade:", self.edit_local)
        group_cad.setLayout(form_cad)
        layout.addWidget(group_cad)
        
        # --- Parâmetros de Cálculo ---
        group_param = QGroupBox("Parâmetros de Funcionamento")
        form_param = QFormLayout()
        
        # Camada de Setores
        self.combo_layer = QComboBox()
        self.populate_layers()
        
        self.spin_simultaneos = QSpinBox()
        self.spin_simultaneos.setRange(1, 100)
        self.spin_simultaneos.setValue(1)
        
        self.spin_tempo_setor = QDoubleSpinBox()
        self.spin_tempo_setor.setRange(0.1, 24.0)
        self.spin_tempo_setor.setSuffix(" h")
        self.spin_tempo_setor.setValue(1.0)
        
        form_param.addRow("Camada de Setores:", self.combo_layer)
        form_param.addRow("Setores Simultâneos:", self.spin_simultaneos)
        form_param.addRow("Tempo por Setor:", self.spin_tempo_setor)
        
        btn_calc = QPushButton("Calcular Dados")
        btn_calc.clicked.connect(self.calculate)
        form_param.addRow(btn_calc)
        
        group_param.setLayout(form_param)
        layout.addWidget(group_param)
        
        # --- Resultados ---
        group_res = QGroupBox("Resultados Calculados")
        form_res = QFormLayout()
        
        self.lbl_area_total = QLineEdit()
        self.lbl_area_total.setReadOnly(True)
        
        self.lbl_qtd_setores = QLineEdit()
        self.lbl_qtd_setores.setReadOnly(True)
        
        self.lbl_vazao_media = QLineEdit()
        self.lbl_vazao_media.setReadOnly(True)
        
        self.lbl_vazao_projeto = QLineEdit()
        self.lbl_vazao_projeto.setReadOnly(True)
        self.lbl_vazao_projeto.setStyleSheet("font-weight: bold; color: blue;")
        
        self.lbl_vazao_diaria = QLineEdit()
        self.lbl_vazao_diaria.setReadOnly(True)
        self.lbl_vazao_diaria.setStyleSheet("font-weight: bold; color: darkblue;")
        
        self.lbl_tempo_total = QLineEdit()
        self.lbl_tempo_total.setReadOnly(True)
        self.lbl_tempo_total.setStyleSheet("font-weight: bold; color: green;")
        
        form_res.addRow("Área Total (ha):", self.lbl_area_total)
        form_res.addRow("Qtd. Setores:", self.lbl_qtd_setores)
        form_res.addRow("Vazão Média/Setor (m³/h):", self.lbl_vazao_media)
        form_res.addRow("Vazão Projeto (m³/h):", self.lbl_vazao_projeto)
        form_res.addRow("Vazão Total Diária (m³):", self.lbl_vazao_diaria)
        form_res.addRow("Tempo Total de Irrigação (h):", self.lbl_tempo_total)
        
        group_res.setLayout(form_res)
        layout.addWidget(group_res)
        
        # --- Botão Salvar ---
        self.btn_save = QPushButton("Salvar Informações")
        self.btn_save.clicked.connect(self.save_data)
        layout.addWidget(self.btn_save)
        
        self.setLayout(layout)

    def populate_layers(self):
        self.combo_layer.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == layer.VectorLayer and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.combo_layer.addItem(layer.name(), layer)

    def calculate(self):
        layer = self.combo_layer.currentData()
        if not layer:
            QMessageBox.warning(self, "Aviso", "Selecione uma camada de setores válida.")
            return
            
        simultaneos = self.spin_simultaneos.value()
        tempo_setor = self.spin_tempo_setor.value()
        
        total_area = 0.0
        total_vazao = 0.0
        count = 0
        
        # Check fields
        fields = [f.name() for f in layer.fields()]
        has_vazao = 'vazao' in fields
        
        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid(QgsProject.instance().ellipsoid())
        
        for feat in layer.getFeatures():
            count += 1
            # Area
            geom = feat.geometry()
            total_area += da.measureArea(geom)
            
            # Vazao
            if has_vazao:
                val = feat['vazao']
                if val:
                    total_vazao += float(val)
        
        if count == 0:
            QMessageBox.warning(self, "Aviso", "A camada está vazia.")
            return

        # Conversão m² -> ha
        area_ha = total_area / 10000.0
        
        # Médias
        vazao_media = total_vazao / count if count > 0 else 0
        
        # Fórmulas do Usuário
        # Vazão Projeto (Instantânea) = Média * Simultâneos
        vazao_projeto = vazao_media * simultaneos
        
        # Vazão Total Diária (Volume) = Total Vazão (Soma) * Tempo Setor
        # Se cada setor opera por X horas, o volume total é a soma dos volumes de cada setor.
        # Volume Setor = Vazão Setor * Tempo.
        # Volume Total = (Soma Vazão) * Tempo.
        vazao_diaria = total_vazao * tempo_setor
        
        # Tempo Total = (Qtd Setores * Tempo Setor) / Simultâneos
        tempo_total = (count * tempo_setor) / simultaneos
        
        # Display
        self.lbl_area_total.setText(f"{area_ha:.4f}")
        self.lbl_qtd_setores.setText(str(count))
        self.lbl_vazao_media.setText(f"{vazao_media:.2f}")
        self.lbl_vazao_projeto.setText(f"{vazao_projeto:.2f}")
        self.lbl_vazao_diaria.setText(f"{vazao_diaria:.2f}")
        self.lbl_tempo_total.setText(f"{tempo_total:.2f}")
        
        if not has_vazao:
            QMessageBox.information(self, "Info", "O campo 'vazao' não foi encontrado na camada. A vazão será 0.")

    def load_data(self):
        if self.filepath and os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.edit_cliente.setText(data.get('cliente', ''))
                    self.edit_local.setText(data.get('local', ''))
                    self.spin_simultaneos.setValue(data.get('simultaneos', 1))
                    self.spin_tempo_setor.setValue(data.get('tempo_setor', 1.0))
                    
                    # Tenta selecionar layer
                    layer_name = data.get('layer_name', '')
                    idx = self.combo_layer.findText(layer_name)
                    if idx >= 0:
                        self.combo_layer.setCurrentIndex(idx)
                        
                    # Preenche resultados salvos
                    self.lbl_area_total.setText(str(data.get('area_total', '')))
                    self.lbl_vazao_projeto.setText(str(data.get('vazao_projeto', '')))
                    self.lbl_vazao_diaria.setText(str(data.get('vazao_diaria', '')))
                    self.lbl_tempo_total.setText(str(data.get('tempo_total', '')))
            except:
                pass

    def save_data(self):
        if not self.filepath:
            QMessageBox.warning(self, "Erro", "Salve o projeto QGIS antes de salvar os dados.")
            return
            
        data = {
            'cliente': self.edit_cliente.text(),
            'local': self.edit_local.text(),
            'layer_name': self.combo_layer.currentText(),
            'simultaneos': self.spin_simultaneos.value(),
            'tempo_setor': self.spin_tempo_setor.value(),
            'area_total': self.lbl_area_total.text(),
            'vazao_projeto': self.lbl_vazao_projeto.text(),
            'vazao_diaria': self.lbl_vazao_diaria.text(),
            'tempo_total': self.lbl_tempo_total.text()
        }
        
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "Sucesso", "Informações salvas com sucesso!")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao salvar: {e}")

class InfoProjetoTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_info.svg')
        self.action = QAction(QIcon(icon_path), 'Informações do Projeto', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        dlg = InfoProjetoDialog(self.iface.mainWindow())
        dlg.exec_()
