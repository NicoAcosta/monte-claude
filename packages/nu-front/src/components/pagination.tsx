import Link from "next/link"

interface PaginationProps {
  currentPage: number
  totalItems: number
  pageSize: number
  basePath: string
  paramName: string
  searchParams?: Record<string, string | string[]>
}

function buildHref(
  basePath: string,
  paramName: string,
  page: number,
  searchParams?: Record<string, string | string[]>,
): string {
  const params = new URLSearchParams()
  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      if (key === paramName) continue
      if (Array.isArray(value)) {
        for (const v of value) params.append(key, v)
      } else {
        params.set(key, value)
      }
    }
  }
  params.set(paramName, String(page))
  return `${basePath}?${params.toString()}`
}

export function Pagination({
  currentPage,
  totalItems,
  pageSize,
  basePath,
  paramName,
  searchParams,
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
          href={buildHref(basePath, paramName, currentPage - 1, searchParams)}
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
          href={buildHref(basePath, paramName, currentPage + 1, searchParams)}
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
