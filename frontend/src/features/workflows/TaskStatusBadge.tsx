import { CheckCircle2, CircleDashed, Clock3, Loader2, TriangleAlert, XCircle } from 'lucide-react';
import { stateText } from '../../lib/stateText';
import { ui } from '../../lib/libraryText';
import type { TaskEntry } from './taskIndex';

export function TaskStatusBadge({task}:{task:TaskEntry}) {
  const status=task.latest_run_status??task.status;
  const active=['queued','running','cancel_requested'].includes(status);
  const tone=active?'bg-running-quiet text-running':status==='succeeded'?'bg-success-quiet text-success':status==='failed'?'bg-danger-quiet text-danger':status==='confirmed'||status==='ready'?'bg-accent-quiet text-accent':'bg-well text-muted';
  const Icon=active?status==='queued'?Clock3:Loader2:status==='succeeded'?CheckCircle2:status==='failed'?TriangleAlert:status==='cancelled'?XCircle:CircleDashed;
  return <span title={task.latest_run_status?ui('最新运行状态'):ui('流程配置状态')} className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-micro font-medium ${tone}`}>
    <Icon aria-hidden="true" className={`size-3 ${status==='running'?'animate-spin':''}`}/>{stateText(status)}
  </span>;
}
