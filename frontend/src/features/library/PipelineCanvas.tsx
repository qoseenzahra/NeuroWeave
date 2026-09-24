import { ui } from '../../lib/libraryText';
import { useRef, useState } from 'react';
import { displayedInputSlots } from '../workflows/workflowConditions';
import type { InputPort, Method, Node } from './libraryApi';
import { nodePosition, canvasOutputSlots, displayBindings, inputPortKey } from './pipelineGraph';
import type { Point } from './pipelineGraph';

type Props={sharedInputs?:InputPort[][];onShareInputs?:(from:InputPort,to:InputPort)=>void;onDetachSharedInput?:(port:InputPort)=>void;showConditionalInputs?:boolean;onToggleConditionalInputs?:()=>void;steps:Node[];definitions:Record<string,Method>;selected:string|null;disabled:boolean;
  onSelect:(id:string)=>void;onMove:(id:string,position:Point)=>void;onAdd:(id:string,position:Point)=>void;
  onConnect:(from:string,output:string,to:string,input:string)=>void;onDisconnect:(to:string,input:string)=>void;onArrange:()=>void};
const button='rounded border border-line bg-raised px-2 py-1 text-xs disabled:opacity-40';
const curve=(a:Point,b:Point)=>`M ${a.x} ${a.y} C ${a.x+Math.max(70,Math.abs(b.x-a.x)/2)} ${a.y}, ${b.x-Math.max(70,Math.abs(b.x-a.x)/2)} ${b.y}, ${b.x} ${b.y}`;

export function PipelineCanvas(props:Props){
  const viewport=useRef<HTMLDivElement>(null);const [zoom,setZoom]=useState(1);
  const [wire,setWire]=useState<{kind:'input'|'output';from:string;output:string;point:Point}|null>(null);
  const [edge,setEdge]=useState<{to:string;input:string}|null>(null);
  const [sharedEdge,setSharedEdge]=useState<InputPort|null>(null);
  const shared=props.sharedInputs??[];
  const gesture=useRef<{kind:'node';id:string;start:Point;position:Point}|{kind:'pan';start:Point;left:number;top:number}|null>(null);
  const positions=Object.fromEntries(props.steps.map((n,i)=>[n.id,nodePosition(n,i)]));
  const outputs=Object.fromEntries(props.steps.map(n=>[n.id,props.definitions[n.method_id]?canvasOutputSlots(n,props.definitions[n.method_id],props.steps):[]]));
  const inputs=Object.fromEntries(props.steps.map(n=>[n.id,props.definitions[n.method_id]?displayedInputSlots(props.definitions[n.method_id],n.parameters,displayBindings(n,shared),props.showConditionalInputs):[]]));
  const width=Math.max(1800,...Object.values(positions).map(p=>p.x+430));
  const height=Math.max(1100,...props.steps.map(n=>positions[n.id].y+160+Math.max(props.definitions[n.method_id]?.input_slots.length??0,props.definitions[n.method_id]?.output_slots.length??0)*32));
  const point=(x:number,y:number):Point=>{const el=viewport.current!;const box=el.getBoundingClientRect();return {x:(x-box.left+el.scrollLeft)/zoom,y:(y-box.top+el.scrollTop)/zoom};};
  const endpoint=(id:string,slot:string,output:boolean):Point|null=>{
    const node=props.steps.find(n=>n.id===id);if(!node)return null;
    const ports=output?outputs[node.id]:inputs[node.id];
    const index=ports?.findIndex(s=>s.id===slot)??-1;if(index<0)return null;
    return {x:positions[id].x+(output?280:0),y:positions[id].y+72+index*32};
  };
  const finish=(x:number,y:number)=>{
    if(!wire)return;
    const input=document.elementFromPoint(x,y)?.closest<HTMLElement>('[data-pipeline-input]');
    if(input){
      const to={step_id:input.dataset.node!,input_slot_id:input.dataset.pipelineInput!};
      if(wire.kind==='input'){
        if(wire.from===to.step_id&&wire.output===to.input_slot_id)return;
        props.onShareInputs?.({step_id:wire.from,input_slot_id:wire.output},to);
      }else props.onConnect(wire.from,wire.output,to.step_id,to.input_slot_id);
      setWire(null);
    }
  };
  return <section aria-label={ui("Pipeline 节点画布")} className="flex min-h-[480px] min-w-0 flex-col overflow-hidden rounded border border-line">
    <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-line bg-raised p-2 text-xs">
      <button className={button} onClick={()=>setZoom(z=>Math.max(.25,Number((z-.1).toFixed(2))))}>−</button><span aria-label={ui("缩放比例")}>{Math.round(zoom*100)}%</span>
      <button className={button} onClick={()=>setZoom(z=>Math.min(1.5,Number((z+.1).toFixed(2))))}>＋</button>
      <button className={button} onClick={()=>{setZoom(1);viewport.current?.scrollTo(0,0);}}>{ui("重置视图")}</button>
      <button className={button} disabled={props.disabled||!props.steps.length} onClick={props.onArrange}>{ui("自动排列")}</button>
      {props.onToggleConditionalInputs&&<label className="flex items-center gap-1"><input type="checkbox" checked={props.showConditionalInputs??false} onChange={props.onToggleConditionalInputs}/>{ui("显示当前非必需的条件输入")}</label>}
      {edge&&<button className={button} disabled={props.disabled} onClick={()=>{props.onDisconnect(edge.to,edge.input);setEdge(null);}}>{ui("删除所选连线")}</button>}
      {sharedEdge&&<button className={button} disabled={props.disabled} onClick={()=>{props.onDetachSharedInput?.(sharedEdge);setSharedEdge(null);}}>{ui("解除此输入共享")}</button>}
      {wire&&<button className={button} onClick={()=>setWire(null)}>{ui("取消连线")}</button>}
      <span className="text-subtle">{wire?(wire.kind==='input'?ui("选择另一输入端口，共用文件；Esc 取消"):ui("选择目标输入端口；Esc 取消")):ui("输出→输入：步骤依赖 · 输入↔输入：共享文件（紫色虚线） · 拖动空白处平移")}</span>
    </div>
    <div ref={viewport} className="relative min-h-0 flex-1 overflow-auto bg-base" tabIndex={0} style={{minHeight:420,touchAction:'none'}}
      onKeyDown={e=>{if(e.key==='Escape'&&wire){e.preventDefault();e.stopPropagation();setWire(null);}}}
      onDragOver={e=>{if(e.dataTransfer.types.includes('application/x-neuroweave-method')){e.preventDefault();e.dataTransfer.dropEffect='copy';}}}
      onDrop={e=>{e.preventDefault();const id=e.dataTransfer.getData('application/x-neuroweave-method');if(id&&!props.disabled)props.onAdd(id,point(e.clientX,e.clientY));}}
      onPointerDown={e=>{if(e.button!==0||(e.target as HTMLElement).closest('button,[data-pipeline-node]'))return;
        if(wire){setWire(null);return;}setEdge(null);setSharedEdge(null);const el=e.currentTarget;
        gesture.current={kind:'pan',start:{x:e.clientX,y:e.clientY},left:el.scrollLeft,top:el.scrollTop};el.setPointerCapture(e.pointerId);}}
      onPointerMove={e=>{const g=gesture.current;if(g?.kind==='node'&&!props.disabled){const p=point(e.clientX,e.clientY);props.onMove(g.id,{x:Math.max(12,Math.min(30000,g.position.x+p.x-g.start.x)),y:Math.max(12,Math.min(30000,g.position.y+p.y-g.start.y))});}
        else if(g?.kind==='pan'){e.currentTarget.scrollLeft=g.left+g.start.x-e.clientX;e.currentTarget.scrollTop=g.top+g.start.y-e.clientY;}
        else if(wire&&!props.disabled)setWire({...wire,point:point(e.clientX,e.clientY)});}}
      onPointerUp={e=>{gesture.current=null;finish(e.clientX,e.clientY);if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}
      onPointerCancel={()=>{gesture.current=null;setWire(null);}}>
      <div style={{width:width*zoom,height:height*zoom}}>
        <div className="relative origin-top-left" style={{width,height,transform:`scale(${zoom})`,backgroundImage:'radial-gradient(#94a3b844 1px, transparent 1px)',backgroundSize:'20px 20px'}}>
          <svg width={width} height={height} className="pointer-events-none absolute inset-0" aria-label={ui("步骤依赖连线")}>
            <defs><marker id="pipeline-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#3b82f6"/></marker></defs>
            {props.steps.flatMap(n=>Object.entries(n.inputs).map(([input,link])=>{const a=endpoint(link.step_id,link.output_slot_id,true),b=endpoint(n.id,input,false);if(!a||!b)return null;
              return <g key={n.id+'/'+input}><path d={curve(a,b)} stroke={edge?.to===n.id&&edge.input===input?'#f59e0b':'#3b82f6'} strokeWidth="2.5" fill="none" markerEnd="url(#pipeline-arrow)"/>
                <path d={curve(a,b)} stroke="transparent" strokeWidth="18" fill="none" style={{pointerEvents:'stroke',cursor:'pointer'}} onPointerDown={e=>e.stopPropagation()} onClick={()=>{setSharedEdge(null);setEdge({to:n.id,input});}}/></g>;}))}
            {shared.flatMap(group=>group.slice(1).map(port=>{
              const a=endpoint(group[0].step_id,group[0].input_slot_id,false),b=endpoint(port.step_id,port.input_slot_id,false);if(!a||!b)return null;
              const d=`M ${a.x} ${a.y} C ${Math.min(a.x,b.x)-70} ${a.y}, ${Math.min(a.x,b.x)-70} ${b.y}, ${b.x} ${b.y}`;
              return <g key={'shared/'+inputPortKey(port)} aria-label={ui("共享输入连线")}><path d={d} stroke={sharedEdge&&inputPortKey(sharedEdge)===inputPortKey(port)?'#f59e0b':'#a855f7'} strokeWidth="2.5" strokeDasharray="6 4" fill="none"/>
                <path d={d} stroke="transparent" strokeWidth="18" fill="none" style={{pointerEvents:'stroke',cursor:'pointer'}} onPointerDown={e=>e.stopPropagation()} onClick={()=>{setEdge(null);setSharedEdge(port);}}/></g>;
            }))}
            {wire&&(()=>{const a=endpoint(wire.from,wire.output,wire.kind==='output');return a?<path d={curve(a,wire.point)} stroke="#3b82f6" strokeWidth="2" strokeDasharray="5 4" fill="none"/>:null;})()}
          </svg>
          {!props.steps.length&&<p className="absolute left-12 top-12 max-w-sm rounded border border-dashed border-line bg-raised p-6 text-sm text-subtle">{ui("从左侧拖入 Method 放在画布上，再从输出端口连到下一步的输入端口。")}</p>}
          {props.steps.map(node=>{const m=props.definitions[node.method_id];return <article key={node.id} data-pipeline-node={node.id}
            className={'absolute rounded-lg border bg-raised shadow-md '+(props.selected===node.id?'border-blue-500 ring-2 ring-blue-500/30':'border-line')}
            style={{left:positions[node.id].x,top:positions[node.id].y,width:280}} onClick={()=>props.onSelect(node.id)}>
            <button className="flex h-14 w-full cursor-grab items-center rounded-t-lg border-b border-line px-3 text-left text-xs font-semibold active:cursor-grabbing"
              aria-label={ui("移动或选择 {0}",m?.label??node.method_id)} disabled={props.disabled}
              onKeyDown={e=>{if(!e.key.startsWith('Arrow'))return;e.preventDefault();const p=positions[node.id];props.onMove(node.id,{x:Math.max(12,p.x+(e.key==='ArrowRight'?20:e.key==='ArrowLeft'?-20:0)),y:Math.max(12,p.y+(e.key==='ArrowDown'?20:e.key==='ArrowUp'?-20:0))});}}
              onPointerDown={e=>{if(e.button!==0)return;e.stopPropagation();props.onSelect(node.id);setWire(null);setEdge(null);gesture.current={kind:'node',id:node.id,start:point(e.clientX,e.clientY),position:positions[node.id]};viewport.current?.setPointerCapture(e.pointerId);}}>
              <span className="line-clamp-2 break-words">{m?.label??node.method_id}</span></button>
            <div className="grid grid-cols-2 pb-3 text-[11px]">
              <div>{inputs[node.id].map(slot=><div key={slot.id} className="relative flex h-8 items-center pl-4 pr-1" title={`${slot.label} · ${slot.type}${slot.requiredNow?ui(" · 必需"):ui(" · 可选")}${node.inputs[slot.id]?ui(" · 已连接"):''}`}>
                <button disabled={props.disabled} data-node={node.id} data-pipeline-input={slot.id} aria-label={ui("输入 {0} / {1}",m?.label,slot.label)}
                  className={'absolute -left-2 top-2 h-4 w-4 rounded-full border-2 border-blue-500 '+(node.inputs[slot.id]?'bg-blue-500':'bg-raised')}
                  onPointerDown={e=>{e.stopPropagation();if(e.button!==0||wire||!props.onShareInputs)return;props.onSelect(node.id);setEdge(null);setSharedEdge(null);setWire({kind:'input',from:node.id,output:slot.id,point:endpoint(node.id,slot.id,false)!});viewport.current?.setPointerCapture(e.pointerId);}}
                  onClick={e=>{e.stopPropagation();if(e.detail!==0)return;
                    if(wire){if(wire.kind==='input')props.onShareInputs?.({step_id:wire.from,input_slot_id:wire.output},{step_id:node.id,input_slot_id:slot.id});else props.onConnect(wire.from,wire.output,node.id,slot.id);setWire(null);}
                    else if(props.onShareInputs)setWire({kind:'input',from:node.id,output:slot.id,point:endpoint(node.id,slot.id,false)!});}}/>
                <span className="truncate">{shared.some(g=>g.some(p=>p.step_id===node.id&&p.input_slot_id===slot.id))?'↔ ':''}{slot.label}{slot.requiredNow?' *':slot.conditionalOptional?ui("（当前非必需）"):''}</span></div>)}</div>
              <div>{outputs[node.id].map(slot=><div key={slot.id} className="relative flex h-8 items-center justify-end pl-1 pr-4" title={`${slot.label} · ${slot.type}${slot.available?'':ui(" · 当前参数下不生成，请调整参数或删除连线")}`}>
                <span className={slot.available?"truncate":"truncate text-warning"}>{slot.label}{!slot.available&&ui("（当前不生成）")}</span><button disabled={props.disabled||!slot.available} aria-label={ui("输出 {0} / {1}",m?.label,slot.label)} className={"absolute -right-2 top-2 h-4 w-4 rounded-full border-2 "+(slot.available?"border-blue-500 bg-blue-500":"border-warning bg-warning-quiet")}
                  onPointerDown={e=>{e.stopPropagation();setEdge(null);setWire({kind:'output',from:node.id,output:slot.id,point:endpoint(node.id,slot.id,true)!});viewport.current?.setPointerCapture(e.pointerId);}}
                  onClick={e=>{e.stopPropagation();if(e.detail===0)setWire({kind:'output',from:node.id,output:slot.id,point:endpoint(node.id,slot.id,true)!});}}/></div>)}</div>
            </div>
            {!m&&<p className="px-3 pb-3 text-xs text-subtle">{ui("正在读取端口定义…")}</p>}
          </article>;})}
        </div>
      </div>
    </div>
  </section>;
}
