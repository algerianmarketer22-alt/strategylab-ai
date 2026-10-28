"""Explications comptables issues du journal, sans récit de marché inventé."""
def explain(result, currency):
    initial=result['config']['capital']
    final=float(result['equity'].capital.iloc[-1])
    lines=[f'Le capital est passé de {initial:.2f} à {final:.2f} {currency} : résultat net {final-initial:+.2f} {currency}. La dernière position éventuelle a été liquidée selon la convention de fin de simulation.']
    trades=result['trades']
    if len(trades):
        gains=float(trades.loc[trades.pnl>0,'pnl'].sum())
        losses=float(trades.loc[trades.pnl<0,'pnl'].sum())
        lines.append(f'{len(trades)} transactions clôturées : gains nets cumulés {gains:.2f}, pertes nettes cumulées {losses:.2f} {currency}. Les frais de transaction sont déjà inclus dans ces résultats.')
        for label,idx in [('Meilleure transaction',trades.pnl.idxmax()),('Moins bonne transaction',trades.pnl.idxmin())]:
            trade=trades.loc[idx]
            lines.append(f"{label} : {trade['pnl']:+.2f} {currency}, entrée le {trade['entrée']}, sortie le {trade['sortie']} ; motif : {trade['motif']}. À quantité détenue donnée, l’écart des prix exécutés et les frais expliquent le gain ou la perte.")
    else:
        lines.append('Aucune transaction clôturée. Les liquidités restent conservées ; si elles ont été converties en USD au départ, le change et ses frais peuvent modifier leur valeur en euros même sans achat.')
    events=result['events']
    if len(events):
        rejected=events.loc[events.type=='rejet']
        if len(rejected):
            lines.append(f"{len(rejected)} ordres refusés : "+'; '.join(rejected.motif.dropna().unique()))
    lines.append(f"Frais de transaction et de conversion comptabilisés : {result['fees']:.2f} {currency}. Ils sont déjà intégrés au capital final, pas à déduire une seconde fois.")
    if 'conversion' in result:
        c=result['conversion']
        lines.append(f"Décomposition exacte du résultat final en euros : opérations en USD traduites au taux final {c['résultat opérations en EUR au taux final']:+.2f} € ; effet EUR/USD {c['effet du change en EUR']:+.2f} € ; coût des conversions au taux final −{c['coût des deux conversions en EUR au taux final']:.2f} €. Le P/L de chaque transaction est traduit au taux de sa sortie ; le change ultérieur des liquidités explique l’écart avec leur cumul.")
    if final<=1e-8:
        lines.append('Le capital est nul à la précision comptable affichée. Le journal détaille les pertes et frais qui l’ont consommé ; aucune dette ni marge ne peut être créée par le moteur.')
    elif final<.01:
        lines.append('Le capital est inférieur à un centime mais reste strictement positif : il ne doit pas être présenté comme une perte totale exacte.')
    lines.append('Cette explication décrit les exécutions simulées et leur comptabilité ; elle ne prétend pas expliquer les causes économiques des variations du marché.')
    return lines
