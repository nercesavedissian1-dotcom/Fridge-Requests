import {useState} from 'react';
import FridgeSales from './FridgeSales';

type RequestRow = {
 branch: string;
 createdAt: string;
 type?: string;
 status?: string;
 decidedAt?: string;
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
 const categories = new Map<string, Map<string, {name: string; requested: number; taken: number}>>();
 const inWeek = (value: string) => {
  const timestamp = new Date(value);
  if (!Number.isFinite(timestamp.getTime())) return false;
  const civil = calendarDay(timestamp);
  return civil >= start && civil < start + 7 * day;
 };

 for (const row of rows) {
  if (row.branch !== branch) continue;
  const requested = row.type === 'Request' && inWeek(row.createdAt);
  const taken = (row.type === 'Request' && row.status === 'Accepted' && inWeek(row.decidedAt || row.createdAt))
   || (row.type === 'Taken from stock' && inWeek(row.createdAt));
  if (!requested && !taken) continue;
  if (requested) totals[statuses.find(value => value === row.status) ?? 'Pending']++;
  for (const item of row.items) {
   const group = categories.get(item.category) ?? new Map();
   const total = group.get(item.name) ?? {name: item.name, requested: 0, taken: 0};
   if (requested) total.requested += item.quantity;
   if (taken) total.taken += item.quantity;
   group.set(item.name, total);
   categories.set(item.category, group);
  }
 }
 const groups = [...categories].sort(([a], [b]) => a.localeCompare(b)).map(([name, group]) => {
  const items = [...group.values()].sort((a, b) => a.name.localeCompare(b.name));
  return {name, items, requested: items.reduce((sum, item) => sum + item.requested, 0),
   taken: items.reduce((sum, item) => sum + item.taken, 0)};
 });
 return {totals, categories: groups};
}

export default function WeeklyBranchSummary({rows, catalog}: {rows: RequestRow[]; catalog: Record<string,string[]>}) {
 const [weeksBack, setWeeksBack] = useState(0);
 const start = weekStart(new Date()) - weeksBack * 7 * day;
 const {totals, categories} = summarize(rows, start);
 return <section className="identity stocktable weekly-summary" aria-label="Bourj Hammoud weekly summary">
  <h2>Bourj Hammoud weekly summary</h2>
  <p>Monday through Sunday in Beirut time. Requests count on the day submitted. Units taken count on the day stock was deducted.</p>
  <div className="weekly-controls">
   <button type="button" className="refresh" onClick={() => setWeeksBack(weeksBack + 1)}>Previous week</button>
   <strong aria-live="polite">{label.format(start)} – {label.format(start + 6 * day)}</strong>
   <button type="button" className="refresh" disabled={weeksBack === 0} onClick={() => setWeeksBack(weeksBack - 1)}>Next week</button>
  </div>
  <p>{totals.Pending + totals.Accepted + totals.Refused} requests · {totals.Pending} pending · {totals.Accepted} accepted · {totals.Refused} refused</p>
  {categories.length === 0 ? <p>No requests or stock deductions this week.</p> :
   <div className="tablewrap"><table>
    <thead><tr><th scope="col">Item</th><th scope="col">Units requested</th><th scope="col">Units taken</th></tr></thead>
    {categories.map(category => <tbody key={category.name}>
     <tr><th scope="rowgroup">{category.name} total</th>
      <td><strong>{category.requested}</strong></td><td><strong>{category.taken}</strong></td>
     </tr>
     {category.items.map(item => <tr key={item.name}>
      <th scope="row">{item.name}</th><td>{item.requested}</td><td>{item.taken}</td>
     </tr>)}
    </tbody>)}
   </table></div>}
  <FridgeSales key={start} week={new Date(start).toISOString().slice(0,10)}
   catalog={catalog} restocks={Object.fromEntries(categories.flatMap(group => group.items.map(item => [item.name,item.taken])))} />
 </section>;
}
