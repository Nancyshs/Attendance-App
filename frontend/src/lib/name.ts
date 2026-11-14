/** Three words: first name, father's name, grandfather's name. */
export function isTripleName(value: string): boolean {
  return value.trim().split(/\s+/).filter(Boolean).length === 3
}
