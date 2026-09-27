import { useEffect, useRef, useState } from 'react';
import { ui } from '../../lib/libraryText';
import * as api from './libraryApi';
import type { Draft } from './libraryApi';

type Props = {
  draft: Draft;
  setDraft: (value: Draft | ((previous: Draft) => Draft)) => void;
  language: string;
  blocked: boolean;
};
/** Only an explicit button action starts a request; edits and saves never do. */
export function usePipelineDescription({
  draft,
  setDraft,
  language,
  blocked
}: Props) {
  const request = useRef<AbortController | null>(null);
  const [generating, setGenerating] = useState(false);
  const [descriptionStatus, setDescriptionStatus] = useState('');

  // An obsolete response must not replace a newer graph or a manual description.
  useEffect(() => () => request.current?.abort(), [draft, language, blocked]);

  const cancelGeneration = () => request.current?.abort();
  const generateDescription = async () => {
    if (request.current || blocked || !draft.steps.length) return false;
    const controller = new AbortController();
    const snapshot = JSON.stringify(draft);
    request.current = controller;
    setGenerating(true);
    setDescriptionStatus(ui('正在生成描述…'));
    try {
      const result = await api.describe(draft, language, controller.signal);
      if (controller.signal.aborted) return false;
      setDraft((previous) =>
        JSON.stringify(previous) === snapshot
          ? { ...previous, description: result.description }
          : previous
      );
      setDescriptionStatus(result.warning || ui('描述已根据实际编排生成'));
      return true;
    } catch (error) {
      if (!controller.signal.aborted)
        setDescriptionStatus(ui('描述暂未更新：{0}', String(error)));
      return false;
    } finally {
      if (request.current === controller) {
        request.current = null;
        setGenerating(false);
        if (controller.signal.aborted) setDescriptionStatus('');
      }
    }
  };
  return {
    generating,
    descriptionStatus,
    generateDescription,
    cancelGeneration
  };
}
