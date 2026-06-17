import { sourceMeta } from "@/lib/format";
import type { SourceType } from "@/lib/types";

export default function SourceBadge({ source }: { source: SourceType }) {
  const meta = sourceMeta(source);
  return (
    <span className={`badge ${meta.className}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}
