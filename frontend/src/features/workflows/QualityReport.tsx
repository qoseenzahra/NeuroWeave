import { stateText } from '../../lib/stateText';
import type { DryRunReport } from './workflowTypes';
import { ui } from '../../lib/libraryText';
const labels:Record<string,string>={header_readable:'图像头可读取；未验证影像内容',reader_unavailable:'图像头读取环境不可用',format_not_checked:'此格式未接入通用图像头检查',reader_failed:'图像头检查未完成',invalid_header:'图像头损坏或几何信息无效',gradient_table_readable:'梯度表格式可读取',invalid_gradient_table:'梯度表无效',gradient_volume_mismatch:'梯度数量与 DWI 体积数不匹配',five_tt_channels:'5TT 必须有五个组织通道',label_dimensions:'脑区标签图维度不符合要求',spatial_alignment_requires_review:'需要核对输入影像的实际空间对齐；网格或头信息不能证明解剖对齐',voxel_values_and_anatomy_not_checked:'尚未验证组织概率、标签数值和解剖质量',upstream_check_deferred:'上游文件生成后才检查实际内容'};
export function QualityReport({report,checked,disabled,onCheck}:{report:DryRunReport;checked:boolean;disabled:boolean;onCheck:(value:boolean)=>void}){
 return <div className="my-2 rounded border border-line p-2 text-xs">
  <p>{ui('执行检查通过不代表科研质量合格。')}</p>
  {!!report.quality_checks?.length&&<details><summary>{ui('查看图像与跨文件检查')} · {Object.entries(report.quality_summary??{}).map(([key,count])=>`${stateText(key)}: ${count}`).join(' · ')}</summary>
   <div className="max-h-48 overflow-auto">{report.quality_checks.map((row,i)=><p key={i} className="my-1 break-words">{row.sample_id??row.step_id} / {row.slot_id} · {stateText(row.status)} · {ui(labels[row.code]??row.code)}</p>)}
    {Object.values(report.quality_summary??{}).reduce((a,b)=>a+b,0)>report.quality_checks.length&&<p>{ui('仅展示前 200 项；汇总包含全部样本。')}</p>}
   </div></details>}
  {report.quality_review_required&&<label className="mt-2 flex items-start gap-2"><input type="checkbox" checked={checked} disabled={disabled} onChange={e=>onCheck(e.target.checked)}/><span>{ui('我已审阅检查限制，并确认将核对空间对齐和结果质量。')}</span></label>}
 </div>;
}
