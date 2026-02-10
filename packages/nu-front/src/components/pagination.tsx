import Link from "next/link"

interface PaginationProps {
  currentPage: number
  totalItems: number
  pageSize: number
  basePath: string
  paramName: string
}

export function Pagination({
  currentPage,
  totalItems,
  pageSize,
  basePath,
  paramName,
}: PaginationProps) {
  const start = currentPage * pageSize + 1
  const end = Math.min((currentPage + 1) * pageSize, totalItems)
  const hasPrev = currentPage > 0
  const hasNext = end < totalItems

  if (totalItems === 0) return null

  return (
    <div className="flex items-center justify-center gap-4 pt-4 text-sm">
      {hasPrev ? (
        <Link
          href={`${basePath}?${paramName}=${currentPage - 1}`}
          className="rounded border border-white/10 bg-navy-light px-3 py-1.5 text-mc-white/60 transition-colors hover:border-white/20 hover:bg-white/5"
        >
          Prev
        </Link>
      ) : (
        <span className="cursor-default rounded border border-white/5 px-3 py-1.5 text-mc-white/20">
          Prev
        </span>
      )}

      <span className="text-mc-white/40">
        {start}&ndash;{end} of {totalItems}
      </span>

      {hasNext ? (
        <Link
          href={`${basePath}?${paramName}=${currentPage + 1}`}
          className="rounded border border-white/10 bg-navy-light px-3 py-1.5 text-mc-white/60 transition-colors hover:border-white/20 hover:bg-white/5"
        >
          Next
        </Link>
      ) : (
        <span className="cursor-default rounded border border-white/5 px-3 py-1.5 text-mc-white/20">
          Next
        </span>
      )}
    </div>
  )
}
