import assert from 'node:assert/strict';

// Runs against the real page and controls; all API responses use synthetic data.
export async function checkDatasetLock({ page, root, dataset, workflow, appUrl }) {
  const second = { ...dataset, dataset_id: 'replacement', display_name: 'Replacement dataset',
    relative_path: 'replacement', absolute_path: '/synthetic/replacement' };
  let current = { ...workflow, status: 'awaiting_parameter_review', confirmed_at: null,
    parameters_reviewed_at: null, dry_run_report: null, can_unlock: true };
  let conflict = false;
  const changes = [];
  const conversation = { conversation_id: 'lock-test', title: 'Dataset lock regression', archived: false,
    message_count: 2, last_message_preview: 'Synthetic workflow', created_at: '2026-01-01', updated_at: '2026-01-01' };
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url());
    let data, status = 200;
    if (url.pathname === '/api/conversations') data = { conversations: [conversation], has_more: false, next_cursor: null };
    else if (url.pathname === '/api/conversations/lock-test') data = { conversation, messages: [
      { message_id: '1', role: 'user', content: 'Use the selected data', metadata: { dataset_id: 'replacement', interaction_mode: 'task' } },
      { message_id: '2', role: 'assistant', content: 'Synthetic workflow', metadata: { workflow_id: 'fixture' } },
    ] };
    else if (url.pathname === '/api/workflows/fixture') data = current;
    else if (url.pathname === '/api/workflows/fixture/unlock') {
      current = { ...current, locked_at: null, can_unlock: false, can_lock: true, status: 'chain_ready', revision: current.revision + 1 };
      data = current;
    } else if (url.pathname === '/api/workflows/fixture/lock') {
      current = { ...current, locked_at: '2026-01-02', can_unlock: true, can_lock: false,
        status: 'awaiting_parameter_review', revision: current.revision + 1 };
      data = current;
    } else if (url.pathname === '/api/workflows/fixture/dataset') {
      const body = request.postDataJSON();
      changes.push(body);
      assert.equal(body.expected_revision, current.revision);
      if (conflict) {
        current = { ...current, locked_at: '2026-01-03', can_unlock: true, can_lock: false,
          status: 'awaiting_parameter_review', revision: current.revision + 1 };
        status = 409;
        data = { detail: { message: '流程已在其他页面锁定', current } };
      } else {
        current = { ...current, dataset: second, dataset_id: second.dataset_id, revision: current.revision + 1 };
        data = current;
      }
    } else if (url.pathname === '/api/datasets') data = { datasets: [dataset, second] };
    else if (url.pathname === '/api/datasets/replacement') data = second;
    else if (url.pathname === '/api/datasets/roots') data = { roots: [root] };
    else return route.fallback();
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  const openHistory = async () => {
    await page.goto(appUrl);
    await page.getByRole('button', { name: '对话', exact: true }).click();
    await page.getByText(conversation.title, { exact: true }).click();
    await page.getByText('Synthetic workflow', { exact: true }).last().waitFor();
  };
  const datasetButton = name => page.locator('header').getByRole('button', { name, exact: true });
  await openHistory();
  assert(await datasetButton(dataset.display_name).isDisabled(), 'History must use the workflow snapshot, not stale message metadata');
  assert.equal(changes.length, 0);
  await page.getByRole('button', { name: '解锁流程', exact: true }).click();
  await datasetButton(dataset.display_name).click();
  await page.getByRole('button', { name: /Replacement dataset/ }).click();
  await datasetButton(second.display_name).waitFor();
  assert.equal(changes.length, 1);
  assert.equal(changes[0].dataset_id, second.dataset_id);
  await page.getByRole('button', { name: '确定流程链', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('header button[title*="数据集已随流程锁定"]')?.disabled);
  assert(await datasetButton(second.display_name).isDisabled());
  await openHistory();
  assert(await datasetButton(second.display_name).isDisabled(), 'Reload must preserve the replacement snapshot');
  await page.getByRole('button', { name: '解锁流程', exact: true }).click();
  await datasetButton(second.display_name).click();
  conflict = true;
  await page.getByRole('button', { name: /Synthetic dataset/ }).click();
  await page.waitForFunction(() => document.querySelector('header button[title*="数据集已随流程锁定"]')?.disabled);
  assert(await datasetButton(second.display_name).isDisabled(), 'A concurrent lock must reject selection and restore current workflow');
  for (const status of ['awaiting_dry_run', 'ready', 'confirmed']) {
    current = { ...current, status, can_unlock: status !== 'confirmed' };
    await openHistory();
    assert(await datasetButton(second.display_name).isDisabled(), status + ' must freeze the dataset');
  }
  await page.locator('header').getByRole('button', { name: '新建对话', exact: true }).click();
  assert(await datasetButton(second.display_name).isEnabled(), 'A new conversation can choose its own data');
  console.log('Dataset lock, unlock/change/relock, persisted history, concurrent conflict and confirmed state passed.');
}
