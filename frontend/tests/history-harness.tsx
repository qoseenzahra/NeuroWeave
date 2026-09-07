import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useConversationHistory } from '../lib/use-conversation-history';

function HistoryHarness() {
  const [enabled, setEnabled] = useState(false);
  const [query, setQuery] = useState('');
  const [archived, setArchived] = useState(false);
  const history = useConversationHistory('', query, archived, enabled);
  return <main>
    <button onClick={() => setEnabled(!enabled)}>{enabled ? 'Close' : 'Open'}</button>
    <button onClick={() => setArchived(!archived)}>Scope</button>
    <input aria-label="Search" value={query} onChange={(event) => setQuery(event.target.value)} />
    <button onClick={() => void history.loadConversations()}>Refresh</button>
    <button onClick={() => void history.loadMoreConversations()}>More</button>
    <button onClick={() => void history.retryConversations()}>Retry</button>
    <output id="rows">{history.conversations.map((item) => item.title).join('|')}</output>
    <output id="loading">{String(history.isHistoryLoading)}</output>
    <output id="error">{history.historyError}</output>
  </main>;
}
createRoot(document.getElementById('root')!).render(<HistoryHarness />);
