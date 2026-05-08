import os

tools_dir = r'd:\Aqueduct\Aqueduct\tools'

mapa = [
    ('acumulo_vazao.py',          'icone_hf.svg',              'icone_acumulo_vazao.svg'),
    ('analise_lucro.py',          'icone_lucro.svg',            'icone_analise_lucro.svg'),
    ('assistente_robson.py',      'icone_robson.svg',           'icone_assistente_robson.svg'),
    ('atribuir_dn.py',            'icone_dn.svg',               'icone_atribuir_dn.svg'),
    ('calculo_area.py',           'icone_area.svg',             'icone_calculo_area.svg'),
    ('calculo_hf.py',             'icone_hf.svg',               'icone_calculo_hf.svg'),
    ('comprimento_linha.py',      'icone_comprimento.svg',      'icone_comprimento_linha.svg'),
    ('contabilizar_materiais.py', 'icone_contabilizar.svg',     'icone_contabilizar_materiais.svg'),
    ('contabilizar_tubos.py',     'icone_tubos.svg',            'icone_contabilizar_tubos.svg'),
    ('dimensionar_tubulacao.py',  'icone_hf.svg',               'icone_dimensionar_tubulacao.svg'),
    ('gerar_orcamento.py',        'icone_pdf_orcamento.svg',    'icone_gerar_orcamento.svg'),
    ('gerenciar_pecas.py',        'icone_pecas.svg',            'icone_gerenciar_pecas.svg'),
    ('gerenciar_servicos.py',     'icone_servicos.svg',         'icone_gerenciar_servicos.svg'),
    ('grade_poligonos.py',        'icone_grade_poligono.svg',   'icone_grade_poligonos.svg'),
    ('grade_pontos.py',           'icone_grade.svg',            'icone_grade_pontos.svg'),
    ('info_projeto.py',           'icone_info.svg',             'icone_info_projeto.svg'),
    ('inserir_reducoes.py',       'icone_contabilizar.svg',     'icone_inserir_reducoes.svg'),
    ('inverter_linha.py',         'icone_inverter.svg',         'icone_inverter_linha.svg'),
    ('microtubo_comando.py',      'icone_microtubo.svg',        'icone_microtubo_comando.svg'),
    ('recortar_camada.py',        'icone_recortar.svg',         'icone_recortar_camada.svg'),
    ('selecionar_bomba.py',       'icone_hf.svg',               'icone_selecionar_bomba.svg'),
    ('simbologia_direcao.py',     'icone_direcao.svg',          'icone_simbologia_direcao.svg'),
    ('simbologia_dn.py',          'icone_simbologia.svg',       'icone_simbologia_dn.svg'),
    ('simbologia_emissores.py',   'icone_simbologia.svg',       'icone_simbologia_emissores.svg'),
    ('simbologia_hf.py',          'icone_simbologia.svg',       'icone_simbologia_hf.svg'),
    ('simbologia_setores.py',     'icone_simbologia.svg',       'icone_simbologia_setores.svg'),
    ('simbologia_vazao.py',       'icone_simbologia.svg',       'icone_simbologia_vazao.svg'),
    ('somador_selecao.py',        'icone_soma.svg',             'icone_somador_selecao.svg'),
    ('termos_servico.py',         'icone_termos.svg',           'icone_termos_servico.svg'),
    ('vazao_setor.py',            'icone_vazao.svg',            'icone_vazao_setor.svg'),
]

log = []
for filename, antigo, novo in mapa:
    path = os.path.join(tools_dir, filename)
    if not os.path.exists(path):
        log.append('NOTFOUND: ' + filename)
        continue
    with open(path, 'r', encoding='utf-8') as f:
        c = f.read()
    if antigo in c:
        c2 = c.replace(antigo, novo, 1)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(c2)
        log.append('OK: ' + filename + ' -> ' + novo)
    elif novo in c:
        log.append('ALREADY: ' + filename)
    else:
        log.append('MISS: ' + filename + ' (buscou: ' + antigo + ')')

with open(r'd:\Aqueduct\Aqueduct\resultado_icones.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(log))

print('Concluido! Ver resultado_icones.txt')
