/** 数据集和文件选择器共用 FastAPI 的错误格式；非 JSON 响应保留 HTTP 状态。 */
export async function responseError(response: Response, message?: string): Promise<string> {
  const fallback = message ?? `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { detail?: unknown };
    return typeof payload.detail === 'string' ? payload.detail : fallback;
  } catch {
    return fallback;
  }
}
