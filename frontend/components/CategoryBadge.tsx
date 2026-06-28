// Цвет бейджа по категории — как в дизайне «МедЦена»:
// лаборатория (зелёный), приём врача (золотой), диагностика (синий), процедура (фиолет.).
type Tone = { fg: string; bg: string; dot: string };

const LAB: Tone = { fg: "#0B6F66", bg: "#E3F1EE", dot: "#0F8A7E" };
const DOC: Tone = { fg: "#7A5A12", bg: "#F6EFDD", dot: "#C79321" };
const DIAG: Tone = { fg: "#1E4E7A", bg: "#E2EDF6", dot: "#2E78B8" };
const PROC: Tone = { fg: "#6A3A6E", bg: "#F1E6F2", dot: "#9A53A0" };

function toneFor(category: string): Tone {
  const c = (category || "").toLowerCase();
  if (/анализ|лаборат|кров|моч/.test(c)) return LAB;
  if (/приём|прием|врач|консультац/.test(c)) return DOC;
  if (/узи|мрт|кт|рентген|диагност|томограф|эндоск|флюор/.test(c)) return DIAG;
  return PROC; // процедуры / стоматология / прочее
}

export default function CategoryBadge({ category }: { category: string }) {
  const t = toneFor(category);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
      style={{ color: t.fg, background: t.bg }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: t.dot }} />
      {category}
    </span>
  );
}
