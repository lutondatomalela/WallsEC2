# WallsEC2 — v2.0.0-rc1

Ferramenta de dimensionamento seccional de paredes de betão armado, segundo a NP EN 1992-1-1:2010 e alterações aplicáveis, com metodologia complementar de placa/casca (NP EN 1992-2:2018, Anexo LL e secção 6.109). **Release candidate para testes de aceitação; não constitui validação regulamentar integral.** Consultar as condições de utilização e a evidência de validação em `docs/`.

## Windows x64 — release candidate

**[Descarregar WallsEC2 v2.0.0-rc1 para Windows x64 (.zip)](https://github.com/lutondatomalela/WallsEC2/releases/download/v2.0.0-rc1/WallsEC2-v2.0.0-rc1-Windows-x64.zip)**

1. Extrair integralmente o ZIP.
2. Abrir a pasta `WallsEC2` e executar `WallsEC2.exe`.
3. Manter todos os ficheiros da pasta de distribuição juntos. Não é necessário instalar Python.

- [Página da pré-release](https://github.com/lutondatomalela/WallsEC2/releases/tag/v2.0.0-rc1)
- [SHA-256 da distribuição](https://github.com/lutondatomalela/WallsEC2/releases/download/v2.0.0-rc1/SHA256SUMS.txt)
- [Compilação, regressão e teste de arranque em Windows](https://github.com/lutondatomalela/WallsEC2/actions/runs/45812348273) — concluídos com sucesso.

A distribuição corresponde ao código da [branch de lançamento](https://github.com/lutondatomalela/WallsEC2/tree/release/v2.0.0-rc1). O workflow de compilação está em `.github/workflows/windows-release.yml`. O estatuto de pré-release é mantido: os testes de software não constituem validação estrutural integral.

## Instalação Windows a partir do código fonte

1. Instalar Python 3.12 ou 3.13 de 64 bits.
2. Executar `INSTALAR_Windows.bat`.
3. Executar `INICIAR_WallsEC2.bat`.
4. Opcional: `COMPILAR_Windows.bat` gera a distribuição PyInstaller. Manter a pasta `dist/WallsEC2` completa. A distribuição publicada foi compilada e testada em Windows através do GitHub Actions.

## Utilização

1. Importar a tabela de esforços assinados e concomitantes (Nxx, Nyy, Nxy, Mxx, Myy, Mxy, Qxx, Qyy), identificando painel, nó e combinação. Confirmar unidades, eixos locais, normal das faces e sinais. A tabela não deve misturar envolventes independentes como tensores simultâneos.
2. Definir betão, aço, espessura e recobrimento; indicar as combinações ELU, CAR, FREQ e QP. Introduzir a malha base e os limites de diâmetros. As hipóteses de estabilidade por faixa podem ser introduzidas manualmente ou a partir da geometria dos nós, com factores de encurvadura confirmados pelo projetista.
3. Calcular e consultar o resumo, a envolvente de resistência, a limitação de tensões e a fendilhação. Exportar PDF ou Excel. Não adotar um resultado condicionado como conforme.
4. Se necessário, em **Configuração**, criar e importar a ficha de corte intercamadas. A ficha compara um limite superior do corte adicional documentado externamente com a reserva de resistência calculada. Ver instruções abaixo.

## Âmbito

- ELU: N–M por faixa; modelo sandwich; resistência dos campos comprimidos (6.109); corte resultante e proposta de ligações; equilíbrio de forças e momentos; optimização base + reforços. A segunda ordem local por faixas X/Y é incluída no modelo sandwich através da envolvente de incrementos. A análise global e a estabilidade acoplada da casca são externas.
- LL(115)(c): cálculo da correcção excêntrica de forças e da reserva resistente ao corte adicional; comparação opcional com o limite adicional fornecido por cálculo complementar independente. A diferença de forças de membrana não é o corte adicional. A reserva usa a resistência sem armadura específica, em qualquer orientação. Para secções que exigem ligações, a avaliação do corte adicional fica condicionada.
- ELS: limites CAR (0,60 fck, 0,80 fyk para ações diretas) e limiar QP (0,45 fck); envolvente elástica e, para N–M estritamente uniaxial, modelo fendilhado. Fendilhação convencional segundo 7.3.4 no domínio aplicável. A avaliação condicional de ausência de fendas por cargas não substitui o cálculo de fendas existentes, coacção ou estanquidade (NP EN 1992-3).
- A alternativa LL(103)/(107) de secção íntegra é condicional à história física e à ausência de deformações impostas relevantes. Mantém-se o ramo fendilhado. O limite de triagem de 6.109 não constitui aprovação.

**Cumpre sob hipóteses** indica que os limites seccionais calculados são satisfeitos nas hipóteses declaradas (incluindo a integridade da secção quando se usa a alternativa elástica). **Condicionado** indica uma verificação necessária sem demonstração suficiente. **Não conforme** indica uma verificação não satisfeita no domínio avaliado. Não existe aprovação global automática. O dashboard apresenta o estado seccional, não a estabilidade global. A análise espacial do esforço adicional LL(115)(c) não é executada pela aplicação: apenas é possível verificar a reserva com um limite documentado. Os dados internos mantêm identificadores estáveis para integração e auditoria.

## Corte adicional por transferência intercamadas

A ficha de cálculo em JSON contém a identidade SHA-256 do cálculo e a menor reserva de corte por painel. Um relatório independente deve estabelecer um limite superior não negativo de ΔVEd, em kN/m, abrangendo toda a área do painel, os campos de forças e todos os estados ELU, incluindo os incrementos locais e a armadura final. Confirmar também que a reserva calculada é válida entre os pontos de avaliação; não inferir esta condição a partir de uma nuvem de coordenadas. Preencher o limite, as confirmações, o método, a referência e o responsável; importar a ficha e o relatório correspondente. Se ΔVEd,lim ≤ reserva, o programa regista a satisfação desta comparação conservadora, não a validação do relatório espacial. Se o limite faltar, exceder a reserva ou houver cobertura insuficiente, mantém-se Condicionado. Nenhuma declaração externa promove automaticamente a conformidade global.

## Testes

`python -m unittest discover -s tests -v` (em Linux sem monitor, `xvfb-run -a`). Os testes distribuídos são sintéticos. Não equivalem a validação física/regulamentar integral. A GUI e `python -m tools.calcular_paineis` selecionam o modelo sandwich; a API histórica mantém módulos de investigação fora do fluxo principal para regressão. Não estão incluídos dados privados de projetos.
