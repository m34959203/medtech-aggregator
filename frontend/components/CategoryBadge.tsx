export default function CategoryBadge({ category }: { category: string }) {
  return (
    <span className="badge bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-100">
      <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
      {category}
    </span>
  );
}
