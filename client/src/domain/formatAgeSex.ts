/** "45 F" / "F" / "45" / "" — age.filter(Boolean) would silently drop a
 * genuine age of 0 (a newborn), since Boolean(0) is false; this checks for
 * null/undefined specifically instead. */
export function formatAgeSex(age: number | null, sex: string | null): string {
  return [age, sex].filter((v) => v !== null && v !== undefined).join(" ");
}
