import { responseError } from './api-error';

export type OperationView = { operation_id: string; status: string; message: string };

export async function cancelOperation(apiBase: string, operationId: string) {
  const response = await fetch(`${apiBase}/api/operations/${operationId}/cancel`, { method: 'POST' });
  if (!response.ok) throw new Error(await responseError(response));
}

export async function fetchOperation(apiBase: string, url: string, init: RequestInit,
  onProgress: (operation: OperationView) => void): Promise<Response> {
  const response = await fetch(url, init);
  if (!response.ok) return response;
  let operation = await response.json() as OperationView & { result?: unknown; error?: { current?: unknown; message?: string } };
  if (!operation.operation_id || !operation.status) throw new Error('后台检查返回了无效的任务记录');
  let failures = 0;
  while (true) {
    onProgress(operation);
    if (operation.status === 'succeeded') return Response.json(operation.result);
    if (['failed', 'cancelled'].includes(operation.status)) {
      return Response.json({ detail: operation.error?.current ? operation.error : operation.message }, { status: 409 });
    }
    await new Promise(resolve => setTimeout(resolve, 750));
    try {
      const polled = await fetch(`${apiBase}/api/operations/${operation.operation_id}`);
      if (!polled.ok) throw new Error(await responseError(polled));
      operation = await polled.json() as typeof operation;
      failures = 0;
    } catch (error) {
      if (++failures >= 5) throw error;
      onProgress({ ...operation, message: '连接暂时中断，正在重新读取检查进度…' });
    }
  }
}
