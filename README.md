# WallsEC2

Ferramenta Python para dimensionamento e verificação de faixas de paredes de betão armado, a partir de esforços por metro de modelos de placa/casca, segundo o Eurocódigo 2.

## Versão de validação 1.8.0-rc1

Esta versão inclui flexão simples, interacção N-M de faixa por compatibilidade de extensões, tensões ELS de secção fendilhada e segunda ordem pelo método da rigidez nominal para faixas isoladas. A convenção de esforço normal é seleccionada explicitamente. O comprimento efectivo é definido pelo projectista.

As verificações são de secção/faixa. Não constituem análise de estabilidade global de uma parede ou de um sistema de paredes acopladas.

## Funcionalidades

- Importação XLSX/CSV ou colagem de tabelas; validação de valores, unidades e formato.
- Momentos MXX/MYY/MXY ou quatro colunas Wood-Armer M+/M-.
- Esforços de membrana NXX/NYY assinados para verificação N-M direccional.
- Combinações ELU por listas/intervalos e uma combinação ELS quase-permanente.
- Malha comum por painel/face, armadura base e reforços compatíveis.
- Corte VRd,c e limite simplificado VRd,max.
- wk de flexão simples e N-M direccional na QP, com a armadura comum adoptada em ELU/ELS.
- Relatórios Excel, CSV e PDF; folha Excel específica de N-M/segunda ordem/tensões ELS.

## Utilização

```bash
pip install -r requirements.txt
python WallsEC2.py
```

Python 3.10 ou superior, com Tkinter. Confirmar espessura, recobrimento, orientação X/Y, faces e unidades da tabela. Indicar as combinações ELU, por exemplo `101-133`, e a combinação QP quando se pretende calcular wk.

Para N-M, seleccionar «Compressão positiva» ou «Tracção positiva» de acordo com o software de origem. Momento positivo corresponde à tracção na face + do modelo adoptado: confirmar a correspondência com a normal local dos painéis. NXY e esforços de membrana Wood-Armer não são convertidos automaticamente numa verificação completa de membrana.

Para segunda ordem, indicar l0 em mm, fluência efectiva e extensão última de cálculo do aço. O valor 0 de l0 significa que a segunda ordem não foi avaliada. A extensão última predefinida de 0,01 é uma hipótese conservadora que deve ser confirmada com a classe de ductilidade do aço.

Rever estados, razões e acções recomendadas antes de adoptar os resultados. A redução por máximos de componentes está desactivada: as combinações seleccionadas são preservadas.

## Âmbito e limitações

A interacção N-M usa uma faixa rectangular de 1 m, duas camadas de aço, betão parábola-rectângulo sem resistência à tracção e aço elástico-perfeitamente plástico. A curva é discretizada e a convergência é testada.

O método de rigidez nominal aplica-se ao modelo de faixa isolada de secção/esforço normal constantes, com l0 definido externamente. Considera excentricidade mínima e imperfeição simplificada. Não calcula vínculos, estabilidade global, interacção entre paredes ou flexão no plano da parede.

wk N-M é calculado com tensões de secção fendilhada, k2 dependente do gradiente de tracção e área efectiva por face. Exige convenção N explícita, momentos originais assinados e ausência de NXY/MXY. Casos fora destas condições permanecem não avaliados. São verificados limites conservadores de armadura mínima e de tensões para a utilização do modelo linear.

Não estão incluídas verificações completas de membrana NXY, sismo, amarrações/emendas, retracção impedida, temperatura, estanquidade de reservatórios, incêndio ou pontes. O PDF foi renderizado e inspeccionado num caso sintético, incluindo resultados não avaliados. A validação visual da GUI e os ensaios com ficheiros reais continuam pendentes. Esta versão é candidata de validação e não uma certificação para utilização autónoma em projecto.

## Validação

```bash
python -m unittest discover -s tests -v
```

58 testes locais aprovados, incluindo equilíbrio de secção, convergência, rigidez nominal, importação/unidades, combinação de casos e exportação XLSX. Integração contínua configurada para Windows/Linux e Python 3.10/3.12; a base anterior passou nas quatro configurações; os testes desta revisão devem ser consultados na pull request.

Consultar [validação e hipóteses](docs/VALIDATION.md), [motor N-M](docs/SECTION_MODEL.md) e [histórico](CHANGELOG.md).

## Licença

MIT, conforme [LICENSE](LICENSE). As normas usadas na revisão não são redistribuídas.
