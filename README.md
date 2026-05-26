# WallsEC2

**WallsEC2** é uma ferramenta em Python para dimensionamento e verificação de paredes de betão armado segundo o Eurocódigo 2, com tratamento de esforços por painel, armaduras distribuídas, esforço transverso, controlo de fendilhação e exportação de relatórios em Excel e PDF.

Repositório: [github.com/lutondatomalela/WallsEC2](https://github.com/lutondatomalela/WallsEC2)

## Funcionalidades

- Importação de tabelas de esforços a partir de ficheiros `.xlsx`, `.csv` ou colagem directa no GUI.
- Dimensionamento de armadura por face e direcção.
- Tratamento de `MXX`, `MYY`, `MXY`, `QXX` e `QYY`.
- Opções para consideração conservativa de `MXY` ou momentos principais.
- Verificação ao esforço transverso.
- Controlo de fendilhação simplificado e verificação explícita de `wk` para combinação quase-permanente.
- Optimização de armaduras com solução base e reforços locais.
- Resumo por painel, zonas de armadura, diagnóstico e validação da tabela importada.
- Exportação profissional para `.xlsx` e `.pdf`, com metadados.

## Âmbito

A ferramenta considera paredes modeladas como painéis/placas e dimensiona faixas de 1 m.  
Os resultados dependem da orientação dos eixos locais, das unidades adoptadas e da qualidade da tabela de esforços importada.

Não estão incluídas nesta versão:

- verificação global de compressão;
- flexão composta `N-M`;
- estabilidade;
- efeitos de segunda ordem;
- verificação sísmica específica.

## Requisitos

- Python 3.10 ou superior
- pandas
- openpyxl
- reportlab

Instalação das dependências:

```bash
pip install pandas openpyxl reportlab
```

## Utilização

Executar:

```bash
python WallsEC2_GUI_v10_9.py
```

Fluxo recomendado:

1. Definir geometria, materiais, unidades e opções de cálculo.
2. Colar ou importar a tabela de esforços.
3. Confirmar orientação dos eixos locais e combinação quase-permanente, quando aplicável.
4. Calcular.
5. Rever diagnóstico, resumo por painel e armaduras adoptadas.
6. Exportar os resultados em `.xlsx` e/ou `.pdf`.

## Formato mínimo da tabela

```text
Panel   Node   Case        MXX     MYY     MXY     QXX     QYY
43      49     101        -12.40   3.80    1.25    18.50   6.20
43      49     302 (QP)    -5.10   1.40    0.52     7.20   2.10
```

Unidades usuais:

- Momentos: `kNm/m`
- Esforços transversos: `kN/m`

## Resultados exportados

O ficheiro Excel inclui folhas separadas para:

- metadados;
- dados de entrada;
- resumo por painel;
- armaduras adoptadas;
- zonas de armadura;
- optimização;
- diagnóstico;
- validação da tabela;
- verificações por linha;
- notas EC2;
- resultados completos para auditoria.

O relatório PDF apresenta uma síntese técnica adequada para anexar a uma memória descritiva e justificativa.

## Licença

Distribuído sob a licença MIT. Ver o ficheiro `LICENSE`.

## Autor

**Eng.º Lutonda Tomalela**
