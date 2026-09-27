import { useEffect, useState } from 'react';
import { useQueries, useQueryClient } from '@tanstack/react-query';
import { request } from '../../api/http';
import { pendingTurns, retryTurn, forgetTurn } from './chatTurns';
import type { Turn } from './chatTurns';
import { ui } from '../../lib/libraryText';

export function ChatTurnPanel({onOpen}:{onOpen:(id:string)=>void}){
  const [ids,setIds]=useState(pendingTurns);const client=useQueryClient();const [error,setError]=useState('');
  useEffect(()=>{const refresh=()=>setIds(pendingTurns());window.addEventListener('neuroweave:chat-progress',refresh);return()=>window.removeEventListener('neuroweave:chat-progress',refresh);},[]);
  const turns=useQueries({queries:ids.map(id=>({queryKey:['chat-turn',id],queryFn:()=>request<Turn>(`/api/chat/turns/${id}`),refetchInterval:(query:{state:{data?:Turn}})=>!query.state.data||['queued','running'].includes(query.state.data.status)?1000:false,retry:1}))});
  const completed=turns.map(t=>t.data?.status==='succeeded'?t.data.conversation_id:'').filter(Boolean).join(',');
  useEffect(()=>{if(completed){void client.invalidateQueries({queryKey:['conversations']});for(const id of completed.split(','))void client.invalidateQueries({queryKey:['conversation',id]});}},[completed,client]);
  if(!ids.length)return null;
  return <div className="max-h-40 shrink-0 space-y-2 overflow-auto border-b border-line p-3 text-xs" aria-live="polite">{error&&<p className="text-danger">{error}</p>}{turns.map((query,i)=>{const turn=query.data;return <div key={ids[i]} className="flex flex-wrap items-center gap-2"><span className="min-w-0 flex-1 break-words">{turn?ui(turn.message):query.isError?ui('未能恢复请求，请刷新检查或从会话中重新发送。'):ui('正在恢复对话进度…')}</span>
    {turn&&<button className="rounded border border-line px-2 py-1" onClick={()=>{onOpen(turn.conversation_id);if(turn.status==='succeeded'){void forgetTurn(ids[i]);setIds(pendingTurns());}}}>{ui('打开会话')}</button>}
    {turn&&['failed','interrupted','cancelled'].includes(turn.status)&&<button className="rounded border border-line px-2 py-1" onClick={()=>{void retryTurn(ids[i]).then(()=>client.invalidateQueries({queryKey:['chat-turn',ids[i]]})).catch(e=>setError(String(e)));void client.invalidateQueries({queryKey:['chat-turn',ids[i]]});}}>{ui('重试同一请求')}</button>}
    {turn&&['queued','running'].includes(turn.status)?<button className="rounded border border-line px-2 py-1" onClick={()=>void request(`/api/chat/turns/${ids[i]}/cancel`,{method:'POST'}).catch(e=>setError(String(e)))}>{ui('停止规划')}</button>:<button className="rounded border border-line px-2 py-1" onClick={()=>{void forgetTurn(ids[i]);setIds(pendingTurns());}}>{ui('关闭提示')}</button>}
  </div>;})}</div>;
}
