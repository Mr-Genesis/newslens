import { Badge } from "@/components/ui/Badge";

interface SourceCardProps {
  sourceName: string;
  url: string;
  snippet: string | null;
  isFree: boolean;
}

export function SourceCard({ sourceName, url, snippet, isFree }: SourceCardProps) {
  return (
    <div className={isFree ? "opacity-100" : "opacity-50"}>
      <div className="py-4 border-b border-[var(--border-subtle)]">
        {/* Header: source name + badge */}
        <div className="flex items-center gap-2">
          <span className="text-small font-semibold text-[var(--text-primary)]">
            {sourceName}
          </span>
          <Badge variant={isFree ? "free" : "paywall"}>
            {isFree ? "Free" : "Paywall"}
          </Badge>
        </div>

        {/* Excerpt */}
        {snippet && (
          <p className="text-small text-[var(--text-secondary)] mt-2 line-clamp-3">
            {snippet}
          </p>
        )}

        {/* Link */}
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-mono text-[var(--source-link-color)] mt-2 inline-block hover:underline"
        >
          Read full article &rarr;
        </a>
      </div>
    </div>
  );
}
