import os, re
d = r'd:\Aqueduct\Aqueduct\tools'
skip = {'__init__.py','ferramenta_base.py','gerar_layout_mapa.py','gerar_pdf.py','gerenciar_blocos.py'}
for f in sorted(os.listdir(d)):
    if f.endswith('.py') and f not in skip:
        c = open(os.path.join(d,f),'r',encoding='utf-8').read()
        icons = re.findall(r'icone_[\w]+\.svg', c)
        print(f + ': ' + (icons[0] if icons else 'SEM_ICONE'))
