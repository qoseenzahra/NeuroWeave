'use client';

import { ArrowDown, BookOpenText, Network, ShieldCheck } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { CapabilityRecommendation } from '@/lib/capability';

type Props = {
  recommendation: CapabilityRecommendation;
};

export function CapabilityRecommendationCard({ recommendation }: Props) {
  return (
    <Card className="mt-4 gap-0 overflow-hidden border-amber-200/80 bg-amber-50/35 py-0 shadow-none">
      <CardHeader className="border-b border-amber-100 bg-white/75 px-4 py-3.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-amber-100 text-amber-700">
              <Network className="size-4" />
            </span>
            <div className="min-w-0">
              <CardTitle className="truncate text-sm">{recommendation.title}</CardTitle>
              <p className="mt-0.5 text-[11px] text-slate-500">
                {recommendation.plan_kind === 'atomic' ? '单项能力建议' : '组合能力建议'}
              </p>
            </div>
          </div>
          <Badge className="bg-amber-100 text-amber-800 shadow-none hover:bg-amber-100">
            SKILL.md 指南
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 px-4 py-4">
        {recommendation.items.map((item, index) => (
          <div key={item.capability_id}>
            <div className="rounded-xl border border-slate-200 bg-white p-3.5">
              <div className="flex items-start gap-3">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-slate-900 text-[11px] font-semibold text-white">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-slate-900">{item.label}</p>
                    <Badge
                      className={
                        item.execution_level === 'structured'
                          ? 'bg-emerald-50 text-emerald-700 shadow-none hover:bg-emerald-50'
                          : item.execution_level === 'planning'
                            ? 'bg-amber-50 text-amber-700 shadow-none hover:bg-amber-50'
                          : 'bg-slate-100 text-slate-600 shadow-none hover:bg-slate-100'
                      }
                    >
                      {item.execution_level === 'structured'
                        ? 'Runner 结构化'
                        : item.execution_level === 'planning'
                          ? '规划型结构化'
                          : '待补 Manifest'}
                    </Badge>
                  </div>
                  <p className="mt-1.5 text-xs leading-5 text-slate-600">{item.description}</p>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {item.skill_ids.map((skillId) => (
                      <span
                        className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-1 font-mono text-[10px] text-blue-700"
                        key={skillId}
                      >
                        <BookOpenText className="size-3" />
                        {skillId}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            {index < recommendation.items.length - 1 && (
              <div className="grid h-7 place-items-center text-slate-400">
                <ArrowDown className="size-3.5" />
              </div>
            )}
          </div>
        ))}
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-[11px] leading-5 text-amber-900">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
          <p>{recommendation.notice}</p>
        </div>
      </CardContent>
    </Card>
  );
}
