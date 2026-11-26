# WallsEC2 v2.0.0-rc1

Release candidate para testes de aceitação de dimensionamento seccional de paredes de betão armado (Eurocódigo 2). Inclui interface revista, modelo sandwich, segunda ordem por faixa, otimização das armaduras, verificações ELS no domínio aplicável e exportações PDF/XLSX.

**Não é uma certificação de conformidade regulamentar integral.** A classificação “Condicionado” exige análise complementar antes da adoção da solução. A resistência dos campos comprimidos e o corte adicional intercamadas mantêm condições de aplicabilidade; os esforços e os travamentos devem ser confirmados pelo projetista. Consultar `docs/VALIDACAO_REGULAMENTAR.md` e `README.md`.

Windows x64: extrair a pasta completa e executar `WallsEC2.exe`. O binário é uma distribuição PyInstaller one-folder, sem necessidade de instalação Python, disponibilizada apenas após aprovação dos testes e do arranque no Windows. Não separar o executável das restantes dependências da pasta.
