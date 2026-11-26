"""Compare an independent filled response against an immutable request."""
import argparse,json,csv
from pathlib import Path
from wall_reference_comparison import compare

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('pedido','resposta','relatorio','saida'):p.add_argument(key)
    a=p.parse_args(); read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
    rows=compare(read(a.pedido),read(a.resposta),a.relatorio)
    with open(a.saida,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(len(rows),'métricas; nenhuma classificação regulamentar atribuída')
if __name__=='__main__':main()
