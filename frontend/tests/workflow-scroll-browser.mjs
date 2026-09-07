import assert from 'node:assert/strict';

export async function checkWorkflowScroll({ page, workflow, appUrl }) {
  let current = structuredClone(workflow);
  Object.assign(current, { status: 'awaiting_parameter_review', confirmed_at: null,
    parameters_reviewed_at: null, dry_run_report: null, can_unlock: true, can_review_parameters: true });
  const method = current.steps[0].method_options[0];
  method.parameters.find(p => p.id === 'enabled').label = '自动设置';
  method.parameters.find(p => p.id === 'mode').options.push({ value: 'b', label: '另一选项' });
  const conversation = { conversation_id: 'scroll-test', title: 'Workflow scroll regression', archived: false,
    message_count: 16, last_message_preview: 'Synthetic message', created_at: '2026-01-01', updated_at: '2026-01-01' };
  const messages = [
    { message_id: 'scroll-user', role: 'user', content: 'Configure the existing workflow', metadata: { interaction_mode: 'task' } },
    { message_id: 'scroll-workflow', role: 'assistant', content: 'Workflow to edit', metadata: { workflow_id: 'fixture' } },
    ...Array.from({ length: 14 }, (_, i) => ({ message_id: 'scroll-tail-' + i, role: 'assistant',
      content: ('Synthetic history message ' + i + '. ').repeat(35), metadata: {} })),
  ];
  let mutations = 0;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let data;
    if (path === '/api/conversations') data = { conversations: [conversation], has_more: false, next_cursor: null };
    else if (path === '/api/conversations/scroll-test') data = { conversation, messages };
    else if (path === '/api/workflows/fixture') data = current;
    else if (path === '/api/workflows/fixture/steps/step/parameters') {
      Object.assign(current.steps[0].selected_parameters, route.request().postDataJSON().parameters);
      current.revision += 1; mutations += 1; data = current;
    } else if (path === '/api/workflows/fixture/steps/step/inputs/fod') {
      current.steps[0].input_bindings.fod = { slot_id: 'fod', artifact_type: 'fod_image',
        source: 'existing_path', relative_path: 'wmfod.mif', absolute_path: '/synthetic/wmfod.mif',
        binding_mode: 'single', status: 'validated', messages: [] };
      current.revision += 1; mutations += 1; data = current;
    } else if (path === '/api/chat') data = { content: 'New reply remains reachable', conversation_id: 'scroll-test', mode: 'demo' };
    else return route.fallback();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
  });
  for (const viewport of [{ width: 1440, height: 900 }, { width: 780, height: 600 }]) {
    await page.setViewportSize(viewport);
    await page.goto(appUrl);
    const sidebar = page.getByRole('button', { name: '打开 Skill 面板', exact: true });
    if (await sidebar.isVisible()) await sidebar.click();
    await page.getByRole('button', { name: '对话', exact: true }).click();
    await page.getByText(conversation.title, { exact: true }).click();
    await page.getByText('Workflow to edit', { exact: true }).waitFor();
    await page.waitForTimeout(700); // Let the intentional history-opening scroll finish.
    const threadInput = page.getByRole('spinbutton', { name: '线程数量', exact: true });
    const scrollTop = () => threadInput.evaluate(element => element.closest('[data-slot="scroll-area-viewport"]').scrollTop);
    const keepPosition = async (control, action) => {
      await control.scrollIntoViewIfNeeded();
      const before = await scrollTop(), previous = mutations;
      const saved = page.waitForResponse(response => response.request().method() === 'PATCH'
        && response.url().includes('/api/workflows/fixture/steps/step/'));
      await action();
      await saved;
      await page.getByText('R' + current.revision, { exact: true }).waitFor();
      await page.waitForTimeout(700); // Detect an unwanted smooth scroll after the API response.
      assert.equal(mutations, previous + 1, 'The control must save its change');
      assert(Math.abs(await scrollTop() - before) < 80, 'Editing a workflow moved the chat viewport');
      const bounds = await control.boundingBox();
      assert(bounds && bounds.y >= 0 && bounds.y < viewport.height, 'The edited control should remain visible');
    };
    await keepPosition(threadInput, async () => {
      await threadInput.fill(current.steps[0].selected_parameters.threads === 4 ? '8' : '4');
      await threadInput.press('Enter');
    });
    const mode = page.getByLabel('方法选项', { exact: true });
    await keepPosition(mode, () => mode.selectOption({ index: current.steps[0].selected_parameters.mode === 'a' ? 1 : 0 }));
    const toggle = page.getByRole('switch', { name: '自动设置', exact: true });
    await keepPosition(toggle, () => toggle.click());
    const picker = page.getByRole('button', { name: '选择已有路径', exact: true }).first();
    await keepPosition(picker, async () => {
      await picker.click();
      await page.getByRole('button', { name: 'wmfod.mif', exact: true }).click();
      await page.getByRole('button', { name: '应用到 4 个样本', exact: true }).click();
    });
    // Appending a real chat turn should still reveal the newest response.
    await page.getByLabel('对话输入', { exact: true }).fill('Continue this conversation');
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const reply = page.getByText('New reply remains reachable', { exact: true });
    await reply.waitFor();
    await page.waitForFunction(() => {
      const reply = Array.from(document.querySelectorAll('p')).find(p => p.textContent === 'New reply remains reachable');
      const box = reply?.getBoundingClientRect();
      const viewport = reply?.closest('[data-slot="scroll-area-viewport"]')?.getBoundingClientRect();
      return box && viewport && box.y >= viewport.y && box.bottom <= viewport.bottom;
    }, null, { timeout: 4000 });
    const box = await reply.boundingBox();
    assert(box && box.y >= 0 && box.y < viewport.height,
      'A new reply should still scroll into view: ' + JSON.stringify({ viewport, box, scroll: await scrollTop() }));
  }
  console.log('Workflow number/select/switch/file edits preserve scroll; new chat replies still auto-scroll at desktop and narrow widths.');
}
