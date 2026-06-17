export function CardSkeleton() {
  return (
    <div className="card flex flex-col gap-4 p-5">
      <div className="flex justify-between">
        <div className="skeleton h-6 w-24 rounded-full" />
        <div className="skeleton h-6 w-16 rounded-full" />
      </div>
      <div className="skeleton h-5 w-3/4 rounded-md" />
      <div className="skeleton h-5 w-1/2 rounded-md" />
      <div className="flex items-end justify-between border-t border-ink-100 pt-4">
        <div className="skeleton h-7 w-28 rounded-md" />
        <div className="skeleton h-5 w-20 rounded-md" />
      </div>
    </div>
  );
}

export function CardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

export function OfferRowSkeleton() {
  return (
    <div className="card flex items-center justify-between gap-4 p-5">
      <div className="flex flex-col gap-2">
        <div className="skeleton h-5 w-44 rounded-md" />
        <div className="skeleton h-4 w-28 rounded-md" />
      </div>
      <div className="skeleton h-8 w-24 rounded-md" />
    </div>
  );
}
