import {useState} from 'react';

type RequestRow = {
 branch: string;
 createdAt: string;
 type?: string;
 status?: string;
 items: {name: string; category: string; quantity: number}[];
};
const branch = 'Bourj Hammoud';
const statuses = ['Pending', 'Accepted', 'Refused'] as const;
const beirutDay = new Intl.DateTimeFormat('en-CA', {
 timeZone: 'Asia/Beirut', year: 'numeric', month: '2-digit', day: '2-digit',
});
const label = new Intl.DateTimeFormat('en-GB', {
 timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric',
});

// Represent Beirut calendar dates at UTC midnight so week shifts work across DST.
export function calendarDay(date: Date) {
 const parts = Object.fromEntries(beirutDay.formatToParts(date).map(part => [part.type, part.value]));
 return Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day));
}

const day = 86_400_000;
export function weekStart(date: Date) {
 const civil = calendarDay(date);
 return civil - ((new Date(civil).getUTCDay() + 6) % 7) * day;
}

export function summarize(rows: RequestRow[], start: number) {
 const totals = {Pending: 0, Accepted: 0, Refused: 0};
 const items = new Map<string, {name: string; category: string; requested: number; accepted: number}>();
 for (const row of rows) {
  if (row.branch !== branch || row.type !== 'Request') continue;
  const timestamp = new Date(row.createdAt);
  if (!Number.isFinite(timestamp.getTime())) continue;
  const submitted = calendarDay(timestamp);
  if (submitted < start || submitted >= start + 7 * day) continue;
  const status = statuses.find(value => value === row.status) ?? 'Pending';
  totals[status]++;
  for (const item of row.items) {
   const key = JSON.stringify([item.category, item.name]);
   const total = items.get(key) ?? {name: item.name, category: item.category, requested: 0, accepted: 0};
   total.requested += item.quantity;
   if (status === 'Accepted') total.accepted += item.quantity;
   items.set(key, total);
  }
 }
 return {totals, items: [...items.values()].sort((a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name))};
}

export default function WeeklyBranchSummary({rows}: {rows: RequestRow[]}) {
 const [weeksBack, setWeeksBack] = useState(0);
 const start = weekStart(new Date()) - weeksBack * 7 * day;
 const {totals, items} = summarize(rows, start);
 return <section className="identity stocktable weekly-summary" aria-label="Bourj Hammoud weekly summary">
  <h2>Bourj Hammoud weekly summary</h2>
  <p>Requests grouped by submission date, Monday through Sunday in Beirut time.</p>
  <div className="weekly-controls">
   <button type="button" className="refresh" onClick={() => setWeeksBack(weeksBack + 1)}>Previous week</button>
   <strong aria-live="polite">{label.format(start)} – {label.format(start + 6 * day)}</strong>
   <button type="button" className="refresh" disabled={weeksBack === 0} onClick={() => setWeeksBack(weeksBack - 1)}>Next week</button>
  </div>
  <p>{totals.Pending + totals.Accepted + totals.Refused} requests · {totals.Pending} pending · {totals.Accepted} accepted · {totals.Refused} refused</p>
  {items.length === 0 ? <p>No requests submitted this week.</p> :
   <div className="tablewrap"><table>
    <thead><tr><th scope="col">Item</th><th scope="col">Units requested</th><th scope="col">Units accepted</th></tr></thead>
    <tbody>{items.map(item => <tr key={JSON.stringify([item.category,item.name])}>
     <td>{item.name}<small>{item.category}</small></td><td>{item.requested}</td><td>{item.accepted}</td>
    </tr>)}</tbody>
   </table></div>}
 </section>;
}
