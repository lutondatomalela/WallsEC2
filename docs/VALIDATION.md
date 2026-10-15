# Validação e âmbito

Referência consultada: NP EN 1992-1-1:2010 e Anexo Nacional, AC:2012 e A1:2019 fornecidos para revisão. As normas não são redistribuídas.

## Execução

`python -m unittest discover -s tests -v`

58 testes locais aprovados. Compilação Python e verificação de diferenças de código sem erros. A base anterior passou em Windows/Linux, Python 3.10/3.12; a revisão actual é submetida à mesma matriz de integração contínua.

## Evidência

- Equilíbrio analítico de flexão simples, compressão e tracção uniformes.
- Interacção N-M, inversão de sinais, armadura assimétrica e momento obrigatório no limite de tracção excêntrica.
- Comparação 160/320 fibras e pontos de curva em casos representativos.
- Equilíbrio da secção fendilhada e resíduo ELS; tensões sem truncagem.
- wk N-M por cálculo independente em tracção simples, compressão sem fendas, flexão pura, tracção excêntrica e inversão da flexão.
- Rigidez nominal por cálculo independente, influência da fluência/comprimento e carga de instabilidade.
- Convenções N, listas/intervalos ELU, QP por painel e preservação da malha comum.
- Importação/unidades, rejeição de dados inválidos, ausência de falsos wk com NXY/MXY.
- Exportação XLSX reaberta com verificação de parâmetros/resultados; regressão PDF com quadro N-M e resultado não avaliado.
- PDF de ensaio com dois painéis renderizado e inspeccionado; correcção de tabelas estreitas, larguras, títulos isolados e painéis omitidos.

## Limites

Verifica faixas de 1 m à flexão transversal e N-M direccional. Segunda ordem apenas de faixa isolada, com l0 definido externamente. Não calcula estabilidade global, flexão no plano de parede, membrana NXY, fendas inclinadas, sismo, estanquidade, incêndio ou pontes.

wk composto exige momentos originais assinados e ausência de NXY/MXY. A fluência entra de forma linear no modelo ELS; tensões acima dos limites adoptados geram aviso. A armadura mínima N-M usa uma aproximação conservadora, documentada em SECTION_MODEL.md.

Persistem ensaios com ficheiros reais, revisão visual GUI, comparação independente com outro programa/casos de referência publicados e validação do executável Windows. A contagem de testes não constitui certificação de utilização autónoma em projecto.
