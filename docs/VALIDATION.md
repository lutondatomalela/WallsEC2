# Validação e âmbito — 1.6.0-rc1

Referência principal consultada: NP EN 1992-1-1:2010, incluindo o Anexo Nacional, AC:2012 e A1:2019 fornecidos para revisão. Os PDFs normativos não são redistribuídos no repositório.

## Verificações numéricas

Executar `python -m unittest discover -s tests -v`.

Os testes incluem equilíbrio M = As fyd (d-lambda x/2), cálculo independente de VRd,c com gamma_c alterado, secção fendilhada transformada em ELS, expressões (7.9), (7.11), (7.12), (7.14), geometria, unidades, dados inválidos, transformação de momentos e malha comum ELU/ELS.

Referências: 3.1.7 (bloco rectangular); 6.2.2/6.2.3 (corte); 7.2 (tensão de serviço); 7.3.2/7.3.4 (fendilhação); 8.2 (distância livre); 9.3/9.6 (pormenorização).

A verificação de fendilhação permanece restrita à flexão simples de uma faixa com armadura traccionada. A transformação de secção considera essa armadura e despreza a contribuição da armadura comprimida. Os limites tabulados de diâmetro/espaçamento continuam indicativos e não constituem uma verificação autónoma de 7.3.3.

A altura útil reserva a maior bitola seleccionável como camada ortogonal exterior, de modo conservador. A capacidade é limitada ao domínio x/d <= 0,45; trata-se de uma restrição explícita do motor, não de um limite universal para qualquer classe de betão ou análise.

## Critérios de utilização

Esta versão é uma candidata de validação para flexão transversal de paredes modeladas como placas. Não é uma validação integral de paredes estruturais. Esforços de membrana não nulos desencadeiam «Verificar»: não está implementada interacção N-M, estabilidade ou segunda ordem. Corte não fornecido e ELS não avaliado também impedem aprovação integral.

A malha adoptada é uniforme por painel/face e envelope dos casos analisados; não se combinam esforços de casos diferentes. As linhas fora da combinação QP ficam sem avaliação de wk. A distribuição localizada de reforços requer desenvolvimento adicional.

São necessários, antes de declarar equivalência de robustez a uma ferramenta de projecto completa:

- motor de flexão composta, esforços de membrana e convenções NXX/NYY/NXY explicitamente configuráveis;
- imperfeições, esbelteza, estabilidade e segunda ordem;
- definição das combinações ELU/ELS em conjuntos separados, com envelope de dimensionamento apenas ELU e verificação ELS;
- cálculo de estanquidade segundo NP EN 1992-3 para reservatórios, caso solicitado;
- revisão independente das tabelas de fendilhação, pormenorização, amarrações e ligações;
- ensaios de importação/exportação com ficheiros reais, revisão visual GUI/PDF/XLSX e validação do executável Windows.

As partes 1-2 (incêndio), 2 (pontes), 3 (retenção de líquidos) e fib MC2010 não foram implementadas por esta alteração. Não se afirma conformidade com essas extensões.
