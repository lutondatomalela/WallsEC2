# WallsEC2

**WallsEC2** é uma ferramenta em Python para dimensionamento e verificação de paredes de betão armado segundo o Eurocódigo 2, a partir de esforços por metro obtidos em modelos de painéis/placas.

Repositório: [https://github.com/lutondatomalela/WallsEC2](https://github.com/lutondatomalela/WallsEC2)

## Funcionalidades

* Importação de tabelas de esforços em `.xlsx`, `.csv` ou por colagem directa na interface.
* Leitura de esforços no formato `MXX`, `MYY`, `MXY`, `QXX` e `QYY`.
* Leitura alternativa de momentos Wood-Armer já separados: `MXX+`, `MXX-`, `MYY+` e `MYY-`.
* Dimensionamento de armadura por direcção e por face local do painel.
* Estratégia de armadura base com reforços locais intercalados.
* Verificação ao esforço transverso com `VRd,c` e limite simplificado `VRd,max`.
* Controlo indirecto da fendilhação por diâmetro e espaçamento quando `wk` não é calculado.
* Verificação explícita de `wk` apenas para a combinação quase-permanente de ELS indicada pelo utilizador.
* Diagnóstico de dados importados, unidades, eixos locais, casos governantes e avisos de validação.
* Visualização ampliada de células truncadas na GUI.
* Exportação de resultados para `.xlsx`, `.csv` e relatório `.pdf`.

## Âmbito de cálculo

A ferramenta considera paredes modeladas como elementos de placa/casca e dimensiona faixas de 1 m. Os resultados dependem da orientação dos eixos locais, da normal local do painel, das unidades adoptadas e da qualidade da tabela de esforços importada.

A direcção local vertical deve ser confirmada antes do cálculo. Quando o eixo local `Y` é vertical, os resultados `Y+` e `Y-` correspondem à armadura vertical nas faces positiva e negativa do painel. A face `+` é definida pela normal local positiva do elemento.

## Fendilhação

A verificação da fendilhação segue duas lógicas distintas:

1. **Sem cálculo explícito de `wk`**  
O programa aplica apenas controlo indirecto por armadura mínima, diâmetro e espaçamento. O resultado é assinalado como `OK\*`, e não como `OK` puro, porque `wk` não foi calculado.
2. **Com cálculo explícito de `wk`**  
O utilizador deve activar a opção de verificação de `wk` e indicar a combinação quase-permanente de ELS. O programa calcula `wk` apenas nas linhas dessa combinação. Linhas ELU ou outras combinações ficam como `Não avaliado` para fendilhação.

Os campos de fendilhação são interpretados assim:

|Campo|Interpretação|
|-|-|
|`wk\_x+`|fendilhação associada à armadura X na face +|
|`wk\_x-`|fendilhação associada à armadura X na face -|
|`wk\_y+`|fendilhação associada à armadura Y na face +|
|`wk\_y-`|fendilhação associada à armadura Y na face -|
|`wk\_max`|maior valor entre as quatro verificações|

Para paredes de cave, reservatórios, elementos com exigência de estanquidade ou paredes exteriores críticas, recomenda-se a verificação explícita de `wk` com a combinação quase-permanente de ELS.

## Formatos de entrada

### Formato geral com `MXY`

```text
Panel   Node   Case       MXX      MYY      MXY      QXX      QYY
43      49     101        -12.40    3.80     1.25    18.50     6.20
43      49     302 (QP)    -5.10    1.40     0.52     7.20     2.10
```

Neste caso, o programa trata `MXY` pelo método seleccionado na interface.

### Formato com momentos Wood-Armer separados

```text
Panel   Node   Case       MXX+     MXX-     MYY+     MYY-
43      49     101        12.40     3.10     8.50     2.20
43      49     302 (QP)    5.10     1.20     3.60     0.90
```

Neste caso, o programa usa directamente os momentos positivos e negativos por direcção e não reaplica `MXY`.

## Resultados exportados

A exportação `.xlsx` inclui folhas organizadas por tema:

* metadados;
* dados de entrada;
* resumo por painel;
* armaduras adoptadas;
* zonas de armadura;
* optimização;
* diagnóstico;
* validação da tabela;
* verificação de unidades;
* flexão;
* corte;
* fendilhação;
* resultados completos.

O relatório `.pdf` apresenta um resumo técnico com os resultados principais, incluindo a verificação de fendilhação por ELS quase-permanente quando aplicável.

## Limitações

A versão actual não substitui a validação técnica do engenheiro responsável. Não estão incluídas, de forma completa:

* verificação global de compressão;
* flexão composta `N-M`;
* estabilidade de parede;
* efeitos de segunda ordem;
* efeitos sísmicos específicos;
* retracção impedida;
* temperatura;
* juntas de betonagem;
* estanquidade de reservatórios;
* verificações específicas de paredes de contenção com interacção solo-estrutura.

## Requisitos

* Python 3.10 ou superior
* pandas
* openpyxl
* reportlab

Instalação das dependências:

```bash
pip install pandas openpyxl reportlab
```

## Utilização

Executar:

```bash
python WallsEC2.py
```

Fluxo recomendado:

1. Confirmar espessura, recobrimento, betão e aço.
2. Confirmar orientação dos eixos locais.
3. Importar ou colar a tabela de esforços.
4. Confirmar unidades.
5. Activar a verificação de `wk` e indicar a combinação quase-permanente, quando a fendilhação for condicionante.
6. Executar o cálculo.
7. Rever diagnóstico, armaduras adoptadas, fendilhação e avisos.
8. Exportar os resultados para Excel e PDF.

## Licença

Este projecto é disponibilizado de acordo com a licença incluída no ficheiro `LICENSE`.

