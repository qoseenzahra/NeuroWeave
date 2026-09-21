import { useState } from 'react';
import { useLanguageStore } from '../../stores/languageStore';
import { getTranslations } from '../../lib/i18n';

export function ServerPath({ path, label }: { path: string; label?: string }) {
  const language = useLanguageStore((s) => s.language);
  const t = getTranslations(language);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  return (
    <div className="flex min-w-0 items-center gap-1 text-xs">
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap py-1" title={path}>
        {label ?? path}
      </code>
      <button
        className="shrink-0 rounded border border-line px-1.5 py-1 hover:bg-hover "
        title={path}
        onClick={async () => {
          setCopyError(false);
          try {
            if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(path);
            else {
              const field = document.createElement('textarea');
              const focused = document.activeElement as HTMLElement | null;
              field.value = path;
              field.style.position = 'fixed';
              field.style.opacity = '0';
              document.body.appendChild(field);
              try {
                field.select();
                // HTTP has no modern clipboard alternative; retain this narrow fallback.
                if (!document.execCommand('copy')) throw new Error('copy denied');
              } finally {
                field.remove();
                focused?.focus();
              }
            }
            setCopied(true);
          } catch {
            setCopied(false);
            setCopyError(true);
          }
        }}
      >
        {copied ? t.workspaceCopied : copyError ? t.workspaceCopyFallback : t.workspaceCopyPath}
      </button>
    </div>
  );
}
