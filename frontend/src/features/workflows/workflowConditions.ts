import type { InputSlotSpec, MethodOption, ParameterSpec, ParameterValue } from './workflowTypes';

export function optionKey(value: ParameterValue): string {
  return `${typeof value}:${String(value)}`;
}

export function decodeOption(spec: ParameterSpec, key: string): ParameterValue {
  return spec.options.find((option) => optionKey(option.value) === key)?.value ?? key;
}

export function conditionMatches(
  condition: Record<string, ParameterValue[]>,
  values: Record<string, ParameterValue>
): boolean {
  return Object.entries(condition).every(([parameterId, allowed]) => {
    const current = values[parameterId];
    return (
      current !== undefined &&
      current !== null &&
      allowed.some((item) => optionKey(item) === optionKey(current))
    );
  });
}

export function parameterValues(
  method: MethodOption,
  selected: Record<string, ParameterValue>
): Record<string, ParameterValue> {
  return Object.fromEntries(
    method.parameters
      .map((spec): [string, ParameterValue] => [spec.id, selected[spec.id] ?? spec.default])
      .filter((entry) => entry[1] !== null)
  );
}

export function inputRequired(
  slot: InputSlotSpec,
  values: Record<string, ParameterValue>
): boolean {
  return (
    slot.required ||
    (Object.keys(slot.required_when).length > 0 && conditionMatches(slot.required_when, values))
  );
}

export function visibleParameters(
  method: MethodOption,
  selected: Record<string, ParameterValue>
): ParameterSpec[] {
  const values = parameterValues(method, selected);
  return method.parameters.filter((spec) => conditionMatches(spec.visible_when ?? {}, values));
}
