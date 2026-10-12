"""Idempotent, observable chat turns. Disconnected HTTP clients do not cancel planning."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from threading import Event
from uuid import uuid4
from fastapi import HTTPException
from .operation_context import OperationContext, current_operation, OperationCancelled


class ChatTurns:
    def __init__(self,store,conversations,handler):
        self.store,self.conversations,self.handler=store,conversations,handler
        self.tasks={};self.events={}
        with store._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS chat_turns(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,conversation_id TEXT NOT NULL,status TEXT NOT NULL,message TEXT NOT NULL,request_json TEXT NOT NULL,result_json TEXT,error_json TEXT,updated_at TEXT NOT NULL)')
            db.execute("UPDATE chat_turns SET status='interrupted',message='服务已重启；请检查已返回的内容，再明确重试。' WHERE status IN ('queued','running')")

    async def shutdown(self):
        # Only planning tasks belong here; Runner jobs have their own lifetime.
        pending=list(self.tasks.values())
        for task in pending:task.cancel()
        if pending:await asyncio.gather(*pending,return_exceptions=True)

    def _require_turn_action(self, identity, action):
        """Authorize access using the turn's server-stored conversation scope."""
        with self.store._connect() as db:
            row = db.execute(
                'SELECT conversation_id FROM chat_turns WHERE id=?', (identity,)
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        self.conversations.require_action(row["conversation_id"], action)

    def get(self,identity):
        from .access.contracts import ResourceAction
        with self.store._connect() as db:row=db.execute('SELECT * FROM chat_turns WHERE id=?',(identity,)).fetchone()
        if row is None:raise KeyError(identity)
        self.conversations.require_action(row["conversation_id"], ResourceAction.READ)
        return dict(turn_id=identity,conversation_id=row['conversation_id'],status=row['status'],message=row['message'],
                    result=json.loads(row['result_json']) if row['result_json'] else None,error=json.loads(row['error_json']) if row['error_json'] else None)

    def submit(self,request):
        identity=request.client_turn_id or 'turn-'+uuid4().hex
        payload=request.model_dump(mode='json');payload['client_turn_id']=identity
        signature=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.store._lock,self.store._connect() as db:
            row=db.execute('SELECT fingerprint FROM chat_turns WHERE id=?',(identity,)).fetchone()
            if row:
                if row['fingerprint']!=signature:raise HTTPException(409,'同一请求 ID 不能用于不同的消息或上下文')
                return self.get(identity)
            if db.execute("SELECT COUNT(*) FROM chat_turns WHERE status IN ('queued','running')").fetchone()[0]>=8:raise HTTPException(429,'对话处理队列已满，请稍后重试')
            conversation_id=request.conversation_id
            if conversation_id:
                if not self.store.get_conversation(conversation_id):raise HTTPException(404,'Conversation not found')
                from .access.contracts import ResourceAction
                self.conversations.require_action(conversation_id, ResourceAction.UPDATE)
                if db.execute("SELECT 1 FROM chat_turns WHERE conversation_id=? AND status IN ('queued','running')",(conversation_id,)).fetchone():raise HTTPException(409,'当前会话仍在处理上一条消息')
            else:
                conversation_id=self.conversations.create(request.message[:80]).conversation_id
            payload['conversation_id']=conversation_id
            db.execute('INSERT INTO chat_turns VALUES(?,?,?,?,?,?,NULL,NULL,?)',(identity,signature,conversation_id,'queued','等待处理',json.dumps(payload,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        self._start(identity,request.model_copy(update={'client_turn_id':identity,'conversation_id':conversation_id}))
        return self.get(identity)

    def _start(self,identity,request):
        event=Event();self.events[identity]=event
        task=asyncio.create_task(self._run(identity,request,event));self.tasks[identity]=task
        task.add_done_callback(lambda _:self.tasks.pop(identity,None))

    async def _run(self,identity,request,event):
        def report(message):
            with self.store._connect() as db:db.execute("UPDATE chat_turns SET message=?,updated_at=? WHERE id=?",(message,datetime.now(timezone.utc).isoformat(),identity))
        token=current_operation.set(OperationContext(event,report))
        try:
            with self.store._connect() as db:db.execute("UPDATE chat_turns SET status='running',message='解析需求' WHERE id=?",(identity,))
            result=await self.handler(request)
            with self.store._connect() as db:db.execute("UPDATE chat_turns SET status='succeeded',message='处理完成',result_json=? WHERE id=?",(result.model_dump_json(),identity))
        except (Exception,asyncio.CancelledError) as exc:
            status='cancelled' if isinstance(exc,OperationCancelled) else 'interrupted' if isinstance(exc,asyncio.CancelledError) else 'failed'
            message=str(getattr(exc,'detail',exc)) or '处理已中断'
            error=dict(message=message,status_code=getattr(exc,'status_code',500))
            with self.store._connect() as db:db.execute("UPDATE chat_turns SET status=?,message=?,error_json=? WHERE id=? AND status!='succeeded'",(status,message,json.dumps(error,ensure_ascii=False),identity))
        finally:current_operation.reset(token);self.events.pop(identity,None)

    def retry(self,identity):
        from .models import ChatRequest
        from .access.contracts import ResourceAction
        self._require_turn_action(identity, ResourceAction.RETRY)
        with self.store._lock,self.store._connect() as db:
            row=db.execute('SELECT * FROM chat_turns WHERE id=?',(identity,)).fetchone()
            if row is None:raise KeyError(identity)
            if row['status'] not in {'failed','interrupted','cancelled'}:return self.get(identity)
            if db.execute("SELECT 1 FROM chat_turns WHERE conversation_id=? AND status IN ('queued','running')",(row['conversation_id'],)).fetchone():raise ValueError('当前会话仍有运行中的请求')
            db.execute("UPDATE chat_turns SET status='queued',error_json=NULL,message='等待重试' WHERE id=?",(identity,))
        self._start(identity,ChatRequest.model_validate_json(row['request_json']))
        return self.get(identity)

    def cancel(self,identity):
        from .access.contracts import ResourceAction
        self._require_turn_action(identity, ResourceAction.CANCEL)
        if identity in self.events:
            self.events[identity].set()
            with self.store._connect() as db:db.execute("UPDATE chat_turns SET message='已请求停止规划，等待当前调用结束' WHERE id=? AND status='running'",(identity,))
        return self.get(identity)

    async def wait(self,identity):
        task=self.tasks.get(identity)
        if task:await asyncio.shield(task)
        result=self.get(identity)
        if result['status']!='succeeded':raise HTTPException((result['error'] or {}).get('status_code',503),(result['error'] or {}).get('message',result['message']))
        from .models import ChatResponse
        return ChatResponse.model_validate(result['result'])
