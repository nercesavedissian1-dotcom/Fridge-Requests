import {useEffect,useState} from 'react';

const prices: Record<string,number> = {
 Weidmann:120000, Rex:110000, Almaza:180000, 'Almaza 250 ml':90000,
 'Buz Tin Red':100000, 'Buz Tin Yellow':100000,
 Pepsi:80000, '7Up':80000, Mirinda:80000, 'Ice Coffee Red':90000, 'Ice Coffee Black':90000,
 'Dark Blue':80000, Water:30000, 'Ice Tea':80000,
 'Cedars Carton Silver':80000, 'Cedars Carton Blue':80000, 'Cedars Long':80000,
 'Cedars Old':80000, 'Cedars Slim Blue':80000, 'Cedars Slim Silver':80000,
 'Marlboro Craft Blue':150000, 'Marlboro Craft Gold':160000, 'Marlboro Red Paper':250000,
 'Marlboro Touch':200000, Snickers:90000, Mars:90000, Bounty:90000,
 'Choco Prince':50000, Twix:90000, 'Sandwich Wafer Red':40000,
 'Sandwich Wafer Blue':40000, 'Sandwich Wafer Black':40000,
};
const number = new Intl.NumberFormat('en-GB');
type Counts = Record<string,[number|null,number|null]>;
type Props = {week:string; catalog:Record<string,string[]>; restocks:Record<string,number>};

export default function FridgeSales({week,catalog,restocks}:Props) {
 const [counts,setCounts]=useState<Counts>({});
 const [revision,setRevision]=useState<number|null>(null);
 const [message,setMessage]=useState(''),[busy,setBusy]=useState(false),[dirty,setDirty]=useState(false);
 const endpoint='/api/fridge-counts/'+week;

 async function load(){
  setBusy(true);
  try {
   const response=await fetch(endpoint);
   const data=await response.json();
   if(!response.ok)throw Error(data.error);
   setCounts(data.counts);setRevision(data.revision);setDirty(false);setMessage('');
  } catch(error){setMessage(error instanceof Error?error.message:'Could not load fridge counts.');}
  finally{setBusy(false);}
 }
 useEffect(()=>{void load();},[endpoint]);

 async function save(event:React.FormEvent){
  event.preventDefault();setBusy(true);
  try {
   const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({counts,revision})});
   const data=await response.json();
   if(!response.ok)throw Error(data.error);
   setRevision(data.revision);setDirty(false);setMessage('Fridge counts saved.');
  } catch(error){setMessage(error instanceof Error?error.message:'Could not save counts.');}
  finally{setBusy(false);}
 }
 const groups=Object.entries(catalog).map(([category,names])=>({category,items:names.map(name=>{
  const [opening,closing]=counts[name]??[null,null];
  const restock=restocks[name]??0, price=Object.hasOwn(prices,name)?prices[name]:undefined;
  const difference=opening===null||closing===null?null:opening+restock-closing;
  const sold=difference===null||difference<0?null:difference;
  return {name,opening,closing,restock,price,sold,value:sold===null||price===undefined?null:sold*price,invalid:difference!==null&&difference<0};
 })}));
 const all=groups.flatMap(group=>group.items);
 const revenue=(items:typeof all)=>items.reduce((sum,item)=>sum+(item.value??0),0);
 const sold=(items:typeof all)=>items.reduce((sum,item)=>sum+(item.sold??0),0);
 return <details style={{marginTop:20}}>
  <summary><strong>Fridge Sales</strong></summary>
  <p>Enter opening and closing counts for this week. Accepted requests are restocks. Sales value uses selling prices in LBP.</p>
  <form onSubmit={save}>
   <p><strong>{number.format(sold(all))} units sold · {number.format(revenue(all))} LBP in priced sales</strong></p>
   <p>Totals use items with both counts entered. Sales value is incomplete when a sold item has no price.</p>
   <div className="tablewrap"><table>
    <thead><tr>{['Item','Opening','Restocked','Closing','Sold','Price (LBP)','Sales (LBP)'].map(title=><th key={title} scope="col">{title}</th>)}</tr></thead>
    {groups.map(({category,items})=><tbody key={category}>
     <tr><th scope="rowgroup" colSpan={4}>{category} total</th><td><strong>{number.format(sold(items))}</strong></td><td></td><td><strong>{number.format(revenue(items))}</strong></td></tr>
     {items.map(item=><tr key={item.name}>
      <th scope="row">{item.name}</th>
      {[0,1].map(position=>{
       const field=position===0?'Opening':'Closing';
       return <FragmentInput key={field} field={field} name={item.name} value={position===0?item.opening:item.closing}
        disabled={busy||revision===null} restock={position===0?item.restock:undefined}
        onChange={value=>{setDirty(true);setCounts(previous=>{
         const next:[number|null,number|null]=[...(previous[item.name]??[null,null])];next[position]=value;return {...previous,[item.name]:next};
        });}}/>;
      })}
      <td>{item.invalid?'Check counts':item.sold??'—'}</td>
      <td>{item.price===undefined?'Price needed':number.format(item.price)}</td>
      <td>{item.value===null?'—':number.format(item.value)}</td>
     </tr>)}
    </tbody>)}
   </table></div>
   <div className="weekly-controls">
    <button className="refresh" disabled={busy||!dirty||revision===null}>Save fridge counts</button>
    <button type="button" className="refresh" disabled={busy} onClick={()=>void load()}>Reload counts</button>
    <span role="status">{message}</span>
   </div>
  </form>
 </details>;
}

function FragmentInput({field,name,value,disabled,restock,onChange}:{
 field:string;name:string;value:number|null;disabled:boolean;restock?:number;onChange:(value:number|null)=>void;
}){
 return <><td><input type="number" min={0} max={1000000} step={1} style={{width:85}}
  aria-label={field+' count for '+name} value={value??''} disabled={disabled}
  onChange={event=>onChange(event.target.value===''?null:event.target.valueAsNumber)}/></td>
  {restock!==undefined&&<td>{number.format(restock)}</td>}</>;
}
