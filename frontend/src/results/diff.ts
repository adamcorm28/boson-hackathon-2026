export type DiffLineKind = "add" | "del" | "hunk" | "meta" | "context";

/** How to color one line of a unified diff. File headers (+++/---) are meta, not adds/removes. */
export function diffLineKind(line: string): DiffLineKind {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff ") || line.startsWith("index ")) return "meta";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  return "context";
}
