# Histórico de alterações

## 1.6.0-rc1 — 2026-10-14

- Rejeição de esforços inválidos/não finitos, formatos Wood-Armer incompletos, unidades desconhecidas e geometrias incompatíveis.
- Conservação de todas as combinações: retirada a redução insegura por máximos de componentes.
- Malha comum por painel/face para verificar ELU e ELS com a mesma armadura adoptada.
- Dimensionamento à flexão pelo equilíbrio do bloco rectangular; retirada a redução adicional 0,87 sobre fyd.
- MRd fora do domínio declarado x/d <= 0,45 não produz aprovação.
- Reserva conservativa de uma camada ortogonal exterior na altura útil.
- Eliminação de armaduras forçadas fora das opções seleccionadas e de reforços com distância livre insuficiente.
- VRd,c utiliza gamma_c introduzido e a menor armadura entre faces; retirada a tentativa automática de compensar corte com aço longitudinal.
- Fendilhação: tensão elástica de secção fendilhada sem truncagem, altura efectiva com (h-x)/3, diâmetro equivalente, regra de espaçamento largo e interpolação do coeficiente k.
- Esforços de membrana convertidos nas unidades seleccionadas; verificações em falta impedem estado OK.
- Verificação do mínimo horizontal em função da armadura vertical realmente adoptada.
- Testes de regressão e integração contínua para Windows/Linux.
