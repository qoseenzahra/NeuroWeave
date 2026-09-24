import { useLanguageStore } from '../stores/languageStore';
import english from './library-en.json';

/** Static UI translations only. Never translate IDs, values or conversation text. */
export function ui(source: string, ...values: unknown[]): string {
  const text = useLanguageStore.getState().language === 'en'
    ? (english as Record<string, string>)[source] ?? source : source;
  return text.replace(/\{(\d+)\}/g, (_, index: string) => String(values[Number(index)] ?? ''));
}
