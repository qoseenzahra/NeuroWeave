import { Globe } from 'lucide-react';
import { getTranslations } from '../lib/i18n';
import { useLanguageStore } from '../stores/languageStore';

export function LanguageSelector() {
  const { language, setLanguage } = useLanguageStore();
  const t = getTranslations(language);

  return (
    <div className="focus-ring flex h-9 shrink-0 items-center gap-1.5 rounded-control border border-line bg-raised pl-2.5 transition-control">
      <Globe className="size-3.5 shrink-0 text-subtle" aria-hidden="true" />

      <select
        value={language}
        onChange={(event) => setLanguage(event.target.value as 'en' | 'zh')}
        aria-label={t.language}
        className="h-full cursor-pointer rounded-control bg-transparent pr-2 text-xs font-medium text-ink outline-none"
      >
        <option value="en">English</option>
        <option value="zh">中文</option>
      </select>
    </div>
  );
}
